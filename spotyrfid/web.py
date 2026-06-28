"""Setup/recovery portal + Wi-Fi captive page + OAuth callback (aiohttp).

The web server has three roles, all on the same port:

  1. Wi-Fi captive page (AP mode) — submit home SSID/password.
  2. Setup portal — enter Telegram token and Spotify credentials when the box
     is unconfigured or has lost its bot connection. Secrets are written to the
     SQLite `config` table, which is the source of truth (env vars only seed a
     fresh box; saved values win on next load). Both are validated before saving.
  3. OAuth callback catcher on the loopback for Spotify linking.

All page text is localised via a `Translator` (see i18n.py); the portal also
carries a language selector that writes the chosen language to the SQLite
`config` table, so both the portal and the Telegram bot follow it.

Design note (per owner's spec): the portal is only meant to be up when the
network is down OR the Telegram bot connection has failed. main.py decides when
to start/stop this server; web.py just serves whatever pages are enabled.
"""
from __future__ import annotations

import html
import logging
from typing import Awaitable, Callable, Optional

from aiohttp import web

from .i18n import LANGUAGES, Translator, normalize_lang

log = logging.getLogger(__name__)

_PAGE = """<!doctype html><html><head><meta name=viewport
content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
body{{font-family:system-ui;max-width:26rem;margin:2rem auto;padding:1rem;color:#191414}}
h2{{color:#1db954}} fieldset{{border:1px solid #ddd;border-radius:.6rem;margin:1rem 0;padding:1rem}}
legend{{font-weight:600;padding:0 .4rem}}
input,button,select{{font-size:1rem;padding:.6rem;width:100%;margin:.3rem 0;box-sizing:border-box}}
button{{background:#1db954;color:#fff;border:0;border-radius:.4rem;cursor:pointer}}
small{{color:#666}} .ok{{color:#1db954}} .err{{color:#c0392b}}
</style></head><body>
<h2>{heading}</h2>
{status}
{language}
{wifi}
{telegram}
{spotify}
</body></html>"""

_LANG_BLOCK = """<fieldset><legend>{legend}</legend>
<form method=post action=/language>
<select name=language onchange="this.form.submit()">{options}</select>
<noscript><button type=submit>OK</button></noscript></form></fieldset>"""

_WIFI_BLOCK = """<fieldset><legend>{legend}</legend>
<form method=post action=/wifi>
<input name=ssid placeholder="{ssid}" list=ssids required>
<datalist id=ssids>{options}</datalist>
<input name=password type=password placeholder="{password}">
<button type=submit>{connect}</button></form></fieldset>"""

_TG_BLOCK = """<fieldset><legend>{legend}</legend>
<form method=post action=/telegram>
<input name=token placeholder="{token_ph}" value="{token_val}" required>
<button type=submit>{save}</button></form>
<small>{help}</small></fieldset>"""

_SP_BLOCK = """<fieldset><legend>{legend}</legend>
<form method=post action=/spotify>
<input name=client_id placeholder="{id_ph}" value="{id_val}" required>
<input name=client_secret placeholder="{secret_ph}" value="{secret_val}" required>
<button type=submit>{save}</button></form>
<small>{help}</small></fieldset>"""


class WebServer:
    def __init__(
        self,
        on_wifi: Callable[[str, str], Awaitable[bool]],
        t: Translator,
        on_oauth_code: Optional[Callable[[str], Awaitable[None]]] = None,
        scan_ssids: Optional[Callable[[], Awaitable[list[str]]]] = None,
        on_telegram_token: Optional[
            Callable[[str], Awaitable[Optional[str]]]
        ] = None,
        on_spotify_creds: Optional[
            Callable[[str, str], Awaitable[Optional[str]]]
        ] = None,
        on_language: Optional[Callable[[str], Awaitable[None]]] = None,
        current_values: Optional[Callable[[], dict]] = None,
        redirect_uri: str = "http://127.0.0.1:8080/callback",
        host: str = "0.0.0.0",
        port: int = 8080,
        enable_wifi: bool = True,
        enable_setup: bool = True,
        status_key: str = "",
    ):
        self.on_wifi = on_wifi
        self.t = t
        self.on_oauth_code = on_oauth_code
        self.scan_ssids = scan_ssids
        self.on_telegram_token = on_telegram_token
        self.on_spotify_creds = on_spotify_creds
        self.on_language = on_language
        # Returns the currently-saved {token, client_id, client_secret} so the
        # form can prefill them — read fresh on each render (values change as
        # the user submits). Missing/None entries render as empty fields.
        self.current_values = current_values
        self.redirect_uri = redirect_uri
        self.host = host
        self.port = port
        self.enable_wifi = enable_wifi
        self.enable_setup = enable_setup
        self.status_key = status_key
        self._runner: Optional[web.AppRunner] = None

    def _language_block(self) -> str:
        current = self.t.lang
        options = "".join(
            f"<option value='{code}'{' selected' if code == current else ''}>"
            f"{name}</option>"
            for code, name in LANGUAGES.items()
        )
        return _LANG_BLOCK.format(
            legend=self.t("portal_lang_legend"), options=options
        )

    async def _render(self, status: str = "") -> str:
        t = self.t
        wifi_html = ""
        if self.enable_wifi:
            opts = ""
            if self.scan_ssids:
                try:
                    opts = "".join(
                        f"<option value='{s}'>" for s in await self.scan_ssids()
                    )
                except Exception:  # noqa: BLE001
                    pass
            wifi_html = _WIFI_BLOCK.format(
                legend=t("portal_wifi_legend"),
                ssid=t("portal_wifi_ssid"),
                password=t("portal_wifi_password"),
                connect=t("portal_wifi_connect"),
                options=opts,
            )
        tg_html = ""
        sp_html = ""
        if self.enable_setup:
            cur = self.current_values() if self.current_values else {}

            def esc(key: str) -> str:
                return html.escape(cur.get(key) or "", quote=True)

            tg_html = _TG_BLOCK.format(
                legend=t("portal_tg_legend"),
                token_ph=t("portal_tg_token_ph"),
                token_val=esc("token"),
                save=t("portal_tg_save"),
                help=t("portal_tg_help"),
            )
            sp_html = _SP_BLOCK.format(
                legend=t("portal_sp_legend"),
                id_ph=t("portal_sp_id_ph"),
                secret_ph=t("portal_sp_secret_ph"),
                id_val=esc("client_id"),
                secret_val=esc("client_secret"),
                save=t("portal_sp_save"),
                help=t("portal_sp_help", redirect=f"<code>{self.redirect_uri}</code>"),
            )
        banner = t(self.status_key) if self.status_key else ""
        if status:
            banner = f"{banner}<p>{status}</p>" if banner else f"<p>{status}</p>"
        return _PAGE.format(
            title=t("portal_title"),
            heading=t("portal_heading"),
            status=banner,
            language=self._language_block(),
            wifi=wifi_html,
            telegram=tg_html,
            spotify=sp_html,
        )

    async def _index(self, request: web.Request) -> web.Response:
        return web.Response(text=await self._render(), content_type="text/html")

    async def _wifi_post(self, request: web.Request) -> web.Response:
        data = await request.post()
        ok = await self.on_wifi(str(data.get("ssid", "")), str(data.get("password", "")))
        cls = "ok" if ok else "err"
        msg = self.t("portal_wifi_connected" if ok else "portal_wifi_failed")
        return web.Response(
            text=await self._render(f"<span class={cls}>{msg}</span>"),
            content_type="text/html",
        )

    async def _telegram_post(self, request: web.Request) -> web.Response:
        data = await request.post()
        token = str(data.get("token", "")).strip()
        if token and self.on_telegram_token:
            err = await self.on_telegram_token(token)
            if err:
                msg = f"<span class=err>{err}</span>"
            else:
                msg = f"<span class=ok>{self.t('portal_tg_saved')}</span>"
        else:
            msg = f"<span class=err>{self.t('portal_tg_none')}</span>"
        return web.Response(text=await self._render(msg), content_type="text/html")

    async def _spotify_post(self, request: web.Request) -> web.Response:
        data = await request.post()
        cid = str(data.get("client_id", "")).strip()
        secret = str(data.get("client_secret", "")).strip()
        if cid and secret and self.on_spotify_creds:
            err = await self.on_spotify_creds(cid, secret)
            if err:
                msg = f"<span class=err>{err}</span>"
            else:
                msg = f"<span class=ok>{self.t('portal_sp_saved')}</span>"
        else:
            msg = f"<span class=err>{self.t('portal_sp_required')}</span>"
        return web.Response(text=await self._render(msg), content_type="text/html")

    async def _language_post(self, request: web.Request) -> web.Response:
        data = await request.post()
        lang = normalize_lang(str(data.get("language", "")).strip())
        if self.on_language:
            await self.on_language(lang)
        return web.Response(text=await self._render(), content_type="text/html")

    async def _oauth_cb(self, request: web.Request) -> web.Response:
        code = request.query.get("code")
        if code and self.on_oauth_code:
            await self.on_oauth_code(str(request.url))
            return web.Response(text=self.t("portal_oauth_ok"))
        return web.Response(text=self.t("portal_oauth_missing"), status=400)

    async def start(self) -> None:
        app = web.Application()
        app.add_routes([
            web.get("/", self._index),
            web.get("/wifi", self._index),
            web.post("/wifi", self._wifi_post),
            web.post("/telegram", self._telegram_post),
            web.post("/spotify", self._spotify_post),
            web.post("/language", self._language_post),
            web.get("/callback", self._oauth_cb),
        ])
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        log.info("portal/web server on %s:%s (wifi=%s setup=%s)",
                 self.host, self.port, self.enable_wifi, self.enable_setup)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    @property
    def running(self) -> bool:
        return self._runner is not None
