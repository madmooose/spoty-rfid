"""Orchestrator — owns the asyncio loop and decides when to run vs. set up.

Startup decision tree (per owner's spec):

  1. No internet            -> AP + portal (Wi-Fi block enabled).
  2. Not configured         -> portal on LAN (need token/creds before anything).
  3. Configured -> start bot, send hello, wait `ack_timeout` for a tap.
       * tapped              -> run normally (portal down).
       * no tap / send fails -> portal on LAN (bot connection considered lost).

The portal is only up when the network is down OR the bot connection failed —
never during normal operation. When the network is fine but the bot link is the
problem, the portal binds the LAN only (no AP broadcast).

This module owns the loop directly (plain asyncio), rather than letting
python-telegram-bot own it, because the bot may be exactly the thing that's
broken — so it can't be the thing that bootstraps everything else.
"""
from __future__ import annotations

import asyncio
import logging

from . import wifi
from .bot import Bot
from .config import Config, K_SP_ID, K_SP_SECRET, K_TG_TOKEN
from .i18n import K_LANG, Translator, normalize_lang
from .rfid import RfidReader
from .spotify import SpotifyController
from .store import Store
from .web import WebServer

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
log = logging.getLogger("spotyrfid")

CONTROL_ACTIONS = {"play", "pause", "playpause", "next", "prev", "volup", "voldown"}


class App:
    def __init__(self) -> None:
        self.store = Store()
        self.cfg = Config.load(self.store)
        self.t = Translator(self.store)
        self.spotify: SpotifyController | None = None
        self.bot: Bot | None = None
        self.reader: RfidReader | None = None
        self.web: WebServer | None = None
        self._restart = asyncio.Event()  # set when portal saves a secret

    # ---- tag handling ---------------------------------------------------
    async def handle_tag(self, uid: str) -> None:
        assert self.bot and self.spotify
        tag = self.store.get_tag(uid)
        if tag is None:
            await self.bot.notify_unknown_tag(uid)
            return
        if not self.spotify.is_authenticated():
            for chat_id in self.bot._allowed():
                await self.bot.app.bot.send_message(
                    chat_id, self.t("tag_not_linked")
                )
            return
        try:
            await asyncio.to_thread(self._apply_tag, tag["uri"])
        except Exception as e:  # noqa: BLE001
            log.exception("playback failed")
            for chat_id in self.bot._allowed():
                await self.bot.app.bot.send_message(
                    chat_id, self.t("playback_failed", e=e)
                )

    def _apply_tag(self, value: str) -> None:
        assert self.spotify
        action = value.lower()
        if action in CONTROL_ACTIONS:
            {
                "play": self.spotify.playpause,
                "pause": self.spotify.pause,
                "playpause": self.spotify.playpause,
                "next": self.spotify.next,
                "prev": self.spotify.prev,
                "volup": lambda: self.spotify.volume_step(+10),
                "voldown": lambda: self.spotify.volume_step(-10),
            }[action]()
        else:
            self.spotify.play_uri(value)

    async def _rfid_consumer(self) -> None:
        assert self.reader
        while True:
            uid = await self.reader.queue.get()
            await self.handle_tag(uid)

    # ---- portal callbacks ----------------------------------------------
    async def _save_telegram_token(self, token: str) -> None:
        self.store.set_config(K_TG_TOKEN, token)
        log.info("telegram token saved via portal")
        self._restart.set()

    async def _save_spotify_creds(self, cid: str, secret: str) -> None:
        self.store.set_config(K_SP_ID, cid)
        self.store.set_config(K_SP_SECRET, secret)
        log.info("spotify creds saved via portal")
        self._restart.set()

    async def _save_language(self, lang: str) -> None:
        # No restart needed: the portal re-renders in the new language right away
        # and the bot's Translator reads this value fresh on every message.
        self.store.set_config(K_LANG, normalize_lang(lang))
        log.info("language set to %s via portal", lang)

    async def _on_wifi(self, ssid: str, pwd: str) -> bool:
        ok = await wifi.connect(ssid, pwd, self.cfg.wifi_iface)
        if ok:
            await wifi.stop_ap()
            self._restart.set()  # re-evaluate now that we may have internet
        return ok

    # ---- portal lifecycle ----------------------------------------------
    async def start_portal(self, *, wifi_block: bool, status_key: str) -> None:
        if self.web and self.web.running:
            return
        self.web = WebServer(
            on_wifi=self._on_wifi,
            t=self.t,
            on_oauth_code=(
                (lambda url: asyncio.to_thread(self.spotify.complete_auth, url))
                if self.spotify else None
            ),
            scan_ssids=lambda: wifi.scan(),
            on_telegram_token=self._save_telegram_token,
            on_spotify_creds=self._save_spotify_creds,
            on_language=self._save_language,
            redirect_uri=self.cfg.spotify_redirect_uri,
            port=self.cfg.web_port,
            enable_wifi=wifi_block,
            enable_setup=True,
            status_key=status_key,
        )
        await self.web.start()

    async def stop_portal(self) -> None:
        if self.web and self.web.running:
            await self.web.stop()

    # ---- bot lifecycle (manual init, not run_polling) ------------------
    async def _start_bot(self) -> None:
        self.spotify = SpotifyController(
            self.store,
            self.cfg.spotify_client_id or "",
            self.cfg.spotify_client_secret or "",
            self.cfg.spotify_redirect_uri,
            self.cfg.spotify_device_id,
        )
        self.bot = Bot(self.cfg.telegram_token or "", self.store, self.spotify)
        await self.bot.app.initialize()
        await self.bot.app.start()
        await self.bot.app.updater.start_polling()

    async def _stop_bot(self) -> None:
        if self.bot:
            try:
                await self.bot.app.updater.stop()
                await self.bot.app.stop()
                await self.bot.app.shutdown()
            except Exception:  # noqa: BLE001
                log.exception("error stopping bot")
            self.bot = None

    # ---- RFID lifecycle -------------------------------------------------
    def _start_rfid(self, loop: asyncio.AbstractEventLoop) -> None:
        if self.reader is not None:
            return  # already running
        self.reader = RfidReader(loop, self.cfg.rfid_device)
        self.reader.start()
        self._rfid_task = loop.create_task(self._rfid_consumer())

    # ---- main supervision loop -----------------------------------------
    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            self._restart.clear()
            self.cfg = Config.load(self.store)  # re-read after any portal save

            online = await wifi.has_internet()
            if not online:
                online = await wifi.wait_for_internet(timeout=20)

            if not online:
                log.warning("no internet — AP + portal")
                await wifi.start_ap(
                    self.cfg.ap_ssid, self.cfg.ap_password, self.cfg.wifi_iface
                )
                await self.start_portal(
                    wifi_block=True,
                    status_key="status_no_internet",
                )
                await self._wait_for_restart()
                continue

            if not (self.cfg.is_complete()):
                log.warning("not configured — setup portal on LAN")
                await self.start_portal(
                    wifi_block=False,
                    status_key="status_finish_setup",
                )
                await self._wait_for_restart()
                continue

            # Configured + online: start bot, run health probe.
            await self._start_bot()
            assert self.bot
            self._start_rfid(loop)

            if not self.bot.has_owner():
                log.info("no owner yet — portal up, waiting for /start claim")
                await self.start_portal(
                    wifi_block=False,
                    status_key="status_claim_ownership",
                )
                # owner claim happens via Telegram; poll until present
                ok = await self._wait_for_owner_or_restart()
                if not ok:
                    await self._teardown_runtime()
                    continue
                await self.stop_portal()

            healthy = await self.bot.send_hello_and_wait(self.cfg.ack_timeout)
            if healthy:
                log.info("ack received — running normally")
                await self.stop_portal()
                await self._wait_for_restart()  # blocks until a secret changes
                await self._teardown_runtime()
                continue
            else:
                log.warning("bot connection unconfirmed — portal on LAN")
                await self.start_portal(
                    wifi_block=False,
                    status_key="status_lost_contact",
                )
                await self._wait_for_restart()
                await self._teardown_runtime()
                continue

    async def _wait_for_restart(self) -> None:
        await self._restart.wait()
        self._restart.clear()

    async def _wait_for_owner_or_restart(self) -> bool:
        """Return True if an owner appeared, False if a portal save fired."""
        assert self.bot
        while True:
            if self.bot.has_owner():
                return True
            try:
                await asyncio.wait_for(self._restart.wait(), timeout=3)
                return False
            except asyncio.TimeoutError:
                continue

    async def _teardown_runtime(self) -> None:
        task = getattr(self, "_rfid_task", None)
        if task:
            task.cancel()
            self._rfid_task = None
        if self.reader:
            self.reader.stop()
            self.reader = None
        await self._stop_bot()


def main() -> None:
    app = App()
    try:
        asyncio.run(app.run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
