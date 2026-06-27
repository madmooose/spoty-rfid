"""Setup/recovery portal + Wi-Fi captive page + OAuth callback (aiohttp).

The web server has three roles, all on the same port:

  1. Wi-Fi captive page (AP mode) — submit home SSID/password.
  2. Setup portal — enter Telegram token and Spotify credentials when the box
     is unconfigured or has lost its bot connection. Secrets are written to the
     SQLite `config` table (env vars still take priority on next load).
  3. OAuth callback catcher on the loopback for Spotify linking.

Design note (per owner's spec): the portal is only meant to be up when the
network is down OR the Telegram bot connection has failed. main.py decides when
to start/stop this server; web.py just serves whatever pages are enabled.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from aiohttp import web

log = logging.getLogger(__name__)

_PAGE = """<!doctype html><html><head><meta name=viewport
content="width=device-width,initial-scale=1"><title>SpotyBox setup</title>
<style>
body{{font-family:system-ui;max-width:26rem;margin:2rem auto;padding:1rem;color:#191414}}
h2{{color:#1db954}} fieldset{{border:1px solid #ddd;border-radius:.6rem;margin:1rem 0;padding:1rem}}
legend{{font-weight:600;padding:0 .4rem}}
input,button{{font-size:1rem;padding:.6rem;width:100%;margin:.3rem 0;box-sizing:border-box}}
button{{background:#1db954;color:#fff;border:0;border-radius:.4rem;cursor:pointer}}
small{{color:#666}} .ok{{color:#1db954}} .err{{color:#c0392b}}
</style></head><body>
<h2>🎵 SpotyBox setup</h2>
{status}
{wifi}
{telegram}
{spotify}
</body></html>"""

_WIFI_BLOCK = """<fieldset><legend>Wi-Fi</legend>
<form method=post action=/wifi>
<input name=ssid placeholder="Wi-Fi name (SSID)" list=ssids required>
<datalist id=ssids>{options}</datalist>
<input name=password type=password placeholder="Password">
<button type=submit>Connect</button></form></fieldset>"""

_TG_BLOCK = """<fieldset><legend>Telegram bot</legend>
<form method=post action=/telegram>
<input name=token placeholder="Bot token from @BotFather" required>
<button type=submit>Save token</button></form>
<small>Create a bot with @BotFather, paste the token here. After saving,
message your bot and send /start to claim ownership.</small></fieldset>"""

_SP_BLOCK = """<fieldset><legend>Spotify app credentials</legend>
<form method=post action=/spotify>
<input name=client_id placeholder="Client ID" required>
<input name=client_secret placeholder="Client secret" required>
<button type=submit>Save credentials</button></form>
<small>From developer.spotify.com/dashboard. Set the redirect URI to
exactly <code>{redirect}</code>.</small></fieldset>"""


class WebServer:
    def __init__(
        self,
        on_wifi: Callable[[str, str], Awaitable[bool]],
        on_oauth_code: Optional[Callable[[str], Awaitable[None]]] = None,
        scan_ssids: Optional[Callable[[], Awaitable[list[str]]]] = None,
        on_telegram_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_spotify_creds: Optional[Callable[[str, str], Awaitable[None]]] = None,
        redirect_uri: str = "http://127.0.0.1:8080/callback",
        host: str = "0.0.0.0",
        port: int = 8080,
        enable_wifi: bool = True,
        enable_setup: bool = True,
        status_message: str = "",
    ):
        self.on_wifi = on_wifi
        self.on_oauth_code = on_oauth_code
        self.scan_ssids = scan_ssids
        self.on_telegram_token = on_telegram_token
        self.on_spotify_creds = on_spotify_creds
        self.redirect_uri = redirect_uri
        self.host = host
        self.port = port
        self.enable_wifi = enable_wifi
        self.enable_setup = enable_setup
        self.status_message = status_message
        self._runner: Optional[web.AppRunner] = None

    async def _render(self, status: str = "") -> str:
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
            wifi_html = _WIFI_BLOCK.format(options=opts)
        tg_html = _TG_BLOCK if self.enable_setup else ""
        sp_html = _SP_BLOCK.format(redirect=self.redirect_uri) if self.enable_setup else ""
        banner = self.status_message
        if status:
            banner = f"{banner}<p>{status}</p>" if banner else f"<p>{status}</p>"
        return _PAGE.format(
            status=banner, wifi=wifi_html, telegram=tg_html, spotify=sp_html
        )

    async def _index(self, request: web.Request) -> web.Response:
        return web.Response(text=await self._render(), content_type="text/html")

    async def _wifi_post(self, request: web.Request) -> web.Response:
        data = await request.post()
        ok = await self.on_wifi(str(data.get("ssid", "")), str(data.get("password", "")))
        cls = "ok" if ok else "err"
        msg = "Connected — you can close this page." if ok else "Connection failed."
        return web.Response(
            text=await self._render(f"<span class={cls}>{msg}</span>"),
            content_type="text/html",
        )

    async def _telegram_post(self, request: web.Request) -> web.Response:
        data = await request.post()
        token = str(data.get("token", "")).strip()
        if token and self.on_telegram_token:
            await self.on_telegram_token(token)
            msg = "<span class=ok>Token saved. The box will restart the bot.</span>"
        else:
            msg = "<span class=err>No token provided.</span>"
        return web.Response(text=await self._render(msg), content_type="text/html")

    async def _spotify_post(self, request: web.Request) -> web.Response:
        data = await request.post()
        cid = str(data.get("client_id", "")).strip()
        secret = str(data.get("client_secret", "")).strip()
        if cid and secret and self.on_spotify_creds:
            await self.on_spotify_creds(cid, secret)
            msg = "<span class=ok>Spotify credentials saved.</span>"
        else:
            msg = "<span class=err>Both fields are required.</span>"
        return web.Response(text=await self._render(msg), content_type="text/html")

    async def _oauth_cb(self, request: web.Request) -> web.Response:
        code = request.query.get("code")
        if code and self.on_oauth_code:
            await self.on_oauth_code(str(request.url))
            return web.Response(text="Spotify linked. You can close this page.")
        return web.Response(text="Missing code.", status=400)

    async def start(self) -> None:
        app = web.Application()
        app.add_routes([
            web.get("/", self._index),
            web.get("/wifi", self._index),
            web.post("/wifi", self._wifi_post),
            web.post("/telegram", self._telegram_post),
            web.post("/spotify", self._spotify_post),
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
