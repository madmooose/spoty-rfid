"""Telegram bot — the control plane for the box.

Commands:
  /start, /help          show usage
  /status                playback + auth + wifi status
  /auth                  begin Spotify linking (sends authorize URL)
  /list                  list bound tags
  /rebind <uid>          rebind an existing tag to a new URI
  /unbind <uid>          remove a binding
  /cancel                abort the current prompt

Conversational flows (no slash needed once prompted):
  * After scanning an UNKNOWN tag, the box DMs you asking for a URI; reply with
    a spotify: URI or an open.spotify.com link to bind it.
  * After /auth, reply with the full redirected URL (or just the code) to finish.

Only chat IDs in the allowlist may control the box. The first user to /start
when the allowlist is empty is adopted as owner (trust-on-first-use).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .spotify import SpotifyController
from .store import Store

ACK_CALLBACK = "spotybox_ack"

log = logging.getLogger(__name__)

_URI_RE = re.compile(r"(spotify:[a-zA-Z]+:[a-zA-Z0-9]+)")
_URL_RE = re.compile(r"open\.spotify\.com/(?:intl-[a-z]+/)?([a-z]+)/([a-zA-Z0-9]+)")

# per-chat pending intent stored in chat_data
PENDING_BIND = "pending_bind_uid"   # value: uid awaiting a URI
PENDING_AUTH = "pending_auth"       # value: True while awaiting redirect URL


def normalize_uri(text: str) -> Optional[str]:
    """Accept a spotify: URI or an open.spotify.com link; return a URI."""
    text = text.strip()
    m = _URI_RE.search(text)
    if m:
        return m.group(1)
    m = _URL_RE.search(text)
    if m:
        kind, ident = m.group(1), m.group(2)
        return f"spotify:{kind}:{ident}"
    return None


class Bot:
    def __init__(self, token: str, store: Store, spotify: SpotifyController):
        self.store = store
        self.spotify = spotify
        self.app = Application.builder().token(token).build()
        self._register()

    # ---- allowlist ------------------------------------------------------
    def _allowed(self) -> set[int]:
        raw = self.store.get_config("allowed_chats")
        return {int(x) for x in raw.split(",")} if raw else set()

    def _add_allowed(self, chat_id: int) -> None:
        allowed = self._allowed()
        allowed.add(chat_id)
        self.store.set_config("allowed_chats", ",".join(str(c) for c in allowed))

    def _is_allowed(self, chat_id: int) -> bool:
        allowed = self._allowed()
        if not allowed:  # trust-on-first-use: first /start adopts owner
            self._add_allowed(chat_id)
            return True
        return chat_id in allowed

    async def _guard(self, update: Update) -> bool:
        chat_id = update.effective_chat.id
        if not self._is_allowed(chat_id):
            await update.message.reply_text("Not authorized.")
            return False
        return True

    def has_owner(self) -> bool:
        return bool(self._allowed())

    # ---- startup health probe (hello + wait for ack) -------------------
    async def send_hello_and_wait(self, timeout: int) -> bool:
        """Greet the owner(s) on startup and wait for a tap.

        Returns True if Telegram delivery worked AND someone acknowledged
        within `timeout`. Returns False if the send failed (bot connection
        lost) or nobody tapped in time — both should drop the box into setup
        mode per the owner's design.
        """
        owners = self._allowed()
        if not owners:
            return False  # no one to greet -> not configured -> setup mode

        self._ack_event = asyncio.Event()
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ I'm here", callback_data=ACK_CALLBACK)]]
        )
        sent_any = False
        for chat_id in owners:
            try:
                await self.app.bot.send_message(
                    chat_id,
                    "👋 SpotyBox is up. Tap to confirm you can reach me — "
                    f"otherwise I'll open the setup portal in {timeout}s.",
                    reply_markup=kb,
                )
                sent_any = True
            except Exception as e:  # noqa: BLE001 — send failure == lost connection
                log.warning("hello send to %s failed: %s", chat_id, e)
        if not sent_any:
            return False  # could not reach Telegram at all
        try:
            await asyncio.wait_for(self._ack_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            log.warning("no ack within %ss — entering setup mode", timeout)
            return False

    async def on_ack(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer("Thanks!")
        try:
            await q.edit_message_text("✅ Connection confirmed. Running normally.")
        except Exception:  # noqa: BLE001
            pass
        ev = getattr(self, "_ack_event", None)
        if ev is not None:
            ev.set()

    # ---- notifications from the box (called by main) --------------------
    async def notify_unknown_tag(self, uid: str) -> None:
        for chat_id in self._allowed():
            await self.app.bot.send_message(
                chat_id,
                f"🆕 Unknown tag `{uid}`.\nReply with a Spotify URI or link to "
                f"bind it, or /cancel.",
                parse_mode=ParseMode.MARKDOWN,
            )
        # remember which uid we're waiting on, per allowed chat
        for chat_id in self._allowed():
            self.app.chat_data[chat_id][PENDING_BIND] = uid

    # ---- command handlers ----------------------------------------------
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        await update.message.reply_text(
            "🎵 SpotyBox ready.\n\n"
            "/status – show state\n"
            "/auth – link Spotify (control plane)\n"
            "/devices – list Spotify Connect devices\n"
            "/setdevice <id> – pin playback to a device\n"
            "/list – list tags\n"
            "/rebind <uid> – rebind a tag\n"
            "/unbind <uid> – remove a tag\n\n"
            "Scan an unknown tag and I'll ask you what to bind it to."
        )

    cmd_help = cmd_start

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        auth = "linked ✅" if self.spotify.is_authenticated() else "NOT linked ❌ (/auth)"
        n = len(self.store.list_tags())
        lines = [f"Spotify: {auth}", f"Tags bound: {n}"]
        if self.spotify.is_authenticated():
            try:
                devs = self.spotify.devices()
                if devs:
                    active = next((d for d in devs if d.get("is_active")), None)
                    lines.append(
                        "Active device: " + (active["name"] if active else "none")
                    )
            except Exception as e:  # noqa: BLE001
                lines.append(f"(device query failed: {e})")
        await update.message.reply_text("\n".join(lines))

    async def cmd_devices(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        if not self.spotify.is_authenticated():
            await update.message.reply_text("Spotify isn't linked yet. Use /auth.")
            return
        try:
            devs = self.spotify.devices()
        except Exception as e:  # noqa: BLE001
            await update.message.reply_text(f"Device query failed: {e}")
            return
        if not devs:
            await update.message.reply_text(
                "No devices found. Is the librespot/Raspotify speaker running and "
                "logged in? See the README on running librespot with --enable-oauth."
            )
            return
        lines = []
        for d in devs:
            mark = "▶️ " if d.get("is_active") else "   "
            star = " ⭐" if d.get("id") == self.spotify.device_id else ""
            lines.append(f"{mark}{d['name']} ({d['type']})\n     `{d['id']}`{star}")
        lines.append("\nUse /setdevice <id> to pin playback to one.")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def cmd_setdevice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        if not ctx.args:
            await update.message.reply_text("Usage: /setdevice <device_id>")
            return
        dev_id = ctx.args[0]
        self.store.set_config("preferred_device_id", dev_id)
        self.spotify.device_id = dev_id
        await update.message.reply_text(
            f"Pinned playback to device `{dev_id}` ✅", parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_auth(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        if self.spotify.is_authenticated():
            await update.message.reply_text(
                "Already linked. Re-linking anyway — open this URL:"
            )
        url = self.spotify.authorize_url()
        ctx.chat_data[PENDING_AUTH] = True
        await update.message.reply_text(
            "Open this URL, approve access, then paste the FULL URL you land on "
            "(it'll look like http://127.0.0.1:8080/callback?code=...):\n\n" + url
        )

    async def cmd_list(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        tags = self.store.list_tags()
        if not tags:
            await update.message.reply_text("No tags bound yet.")
            return
        lines = [
            f"`{t['uid']}` → {t['uri']}" + (f"  ({t['label']})" if t["label"] else "")
            for t in tags
        ]
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def cmd_rebind(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        if not ctx.args:
            await update.message.reply_text("Usage: /rebind <uid>")
            return
        uid = ctx.args[0]
        ctx.chat_data[PENDING_BIND] = uid
        await update.message.reply_text(
            f"OK, send me the new Spotify URI/link for tag `{uid}`.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_unbind(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        if not ctx.args:
            await update.message.reply_text("Usage: /unbind <uid>")
            return
        uid = ctx.args[0]
        ok = self.store.unbind_tag(uid)
        await update.message.reply_text("Removed." if ok else "No such tag.")

    async def cmd_cancel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        ctx.chat_data.pop(PENDING_BIND, None)
        ctx.chat_data.pop(PENDING_AUTH, None)
        await update.message.reply_text("Cancelled.")

    # ---- free-text handler (binding URIs, completing auth) --------------
    async def on_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        text = update.message.text.strip()

        # completing Spotify auth?
        if ctx.chat_data.get(PENDING_AUTH):
            try:
                self.spotify.complete_auth(text)
                ctx.chat_data.pop(PENDING_AUTH, None)
                await update.message.reply_text("Spotify linked ✅")
            except Exception as e:  # noqa: BLE001
                await update.message.reply_text(f"Auth failed: {e}\nTry /auth again.")
            return

        # binding a tag?
        uid = ctx.chat_data.get(PENDING_BIND)
        if uid:
            uri = normalize_uri(text)
            if not uri:
                await update.message.reply_text(
                    "That doesn't look like a Spotify URI or link. Try again or /cancel."
                )
                return
            self.store.bind_tag(uid, uri)
            ctx.chat_data.pop(PENDING_BIND, None)
            await update.message.reply_text(
                f"Bound `{uid}` → {uri} ✅", parse_mode=ParseMode.MARKDOWN
            )
            return

        await update.message.reply_text("Nothing pending. /help for commands.")

    def _register(self) -> None:
        a = self.app
        a.add_handler(CommandHandler("start", self.cmd_start))
        a.add_handler(CommandHandler("help", self.cmd_help))
        a.add_handler(CommandHandler("status", self.cmd_status))
        a.add_handler(CommandHandler("devices", self.cmd_devices))
        a.add_handler(CommandHandler("setdevice", self.cmd_setdevice))
        a.add_handler(CommandHandler("auth", self.cmd_auth))
        a.add_handler(CommandHandler("list", self.cmd_list))
        a.add_handler(CommandHandler("rebind", self.cmd_rebind))
        a.add_handler(CommandHandler("unbind", self.cmd_unbind))
        a.add_handler(CommandHandler("cancel", self.cmd_cancel))
        a.add_handler(CallbackQueryHandler(self.on_ack, pattern=f"^{ACK_CALLBACK}$"))
        a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
