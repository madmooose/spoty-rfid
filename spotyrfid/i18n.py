"""Tiny translation layer for all user-facing text (bot + portal).

The chosen language is a normal config value (`language` key in the SQLite
`config` table), set via the setup portal — so it persists across reboots like
every other setting. `Translator` reads that key fresh on each lookup, so a
language change in the portal takes effect immediately, without a restart.

To add a language: add its code to `LANGUAGES` and a full block to
`TRANSLATIONS`. Missing keys fall back to English, so a partial translation is
safe.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import Store

# config key holding the selected language code
K_LANG = "language"
DEFAULT_LANG = "en"

# code -> native display name (shown in the portal selector)
LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # ---- bot: auth/guard ----
        "not_authorized": "Not authorized.",
        # ---- bot: startup health probe ----
        "hello": (
            "👋 SpotyBox is up. Tap to confirm you can reach me — otherwise "
            "I'll open the setup portal in {timeout}s."
        ),
        "btn_im_here": "✅ I'm here",
        "ack_thanks": "Thanks!",
        "ack_confirmed": "✅ Connection confirmed. Running normally.",
        # ---- bot: unknown tag ----
        "unknown_tag": (
            "🆕 Unknown tag `{uid}`.\nReply with a Spotify URI or link to bind "
            "it, or /cancel."
        ),
        # ---- bot: help / start ----
        "start_help": (
            "🎵 SpotyBox ready.\n\n"
            "/status – show state\n"
            "/auth – link Spotify (control plane)\n"
            "/devices – list Spotify Connect devices\n"
            "/setdevice <id> – pin playback to a device\n"
            "/list – list tags\n"
            "/rebind <uid> – rebind a tag\n"
            "/unbind <uid> – remove a tag\n\n"
            "Scan an unknown tag and I'll ask you what to bind it to."
        ),
        # ---- bot: status ----
        "spotify_linked_short": "linked ✅",
        "spotify_not_linked_short": "NOT linked ❌ (/auth)",
        "status_spotify": "Spotify: {auth}",
        "status_tags": "Tags bound: {n}",
        "status_active_device": "Active device: {name}",
        "device_none": "none",
        "status_device_failed": "(device query failed: {e})",
        # ---- bot: devices ----
        "devices_not_linked": "Spotify isn't linked yet. Use /auth.",
        "devices_query_failed": "Device query failed: {e}",
        "devices_none": (
            "No devices found. Is the librespot/Raspotify speaker running and "
            "logged in? See the README on running librespot with --enable-oauth."
        ),
        "devices_hint": "\nUse /setdevice <id> to pin playback to one.",
        # ---- bot: setdevice ----
        "setdevice_usage": "Usage: /setdevice <device_id>",
        "setdevice_ok": "Pinned playback to device `{dev_id}` ✅",
        # ---- bot: auth ----
        "auth_already": "Already linked. Re-linking anyway — open this URL:",
        "auth_prompt": (
            "Open this URL, approve access, then paste the FULL URL you land on "
            "(it'll look like http://127.0.0.1:8080/callback?code=...):\n\n{url}"
        ),
        "auth_done": "Spotify linked ✅",
        "auth_failed": "Auth failed: {e}\nTry /auth again.",
        "auth_no_code": (
            "That link has no authorization code in it — it looks like you "
            "pasted the link I sent you. Open it, click Agree, then paste the "
            "URL you get redirected to (it contains `?code=`)."
        ),
        # ---- bot: list ----
        "list_empty": "No tags bound yet.",
        # ---- bot: rebind / unbind ----
        "rebind_usage": "Usage: /rebind <uid>",
        "rebind_prompt": "OK, send me the new Spotify URI/link for tag `{uid}`.",
        "unbind_usage": "Usage: /unbind <uid>",
        "unbind_removed": "Removed.",
        "unbind_missing": "No such tag.",
        # ---- bot: cancel / text ----
        "cancelled": "Cancelled.",
        "bind_invalid": (
            "That doesn't look like a Spotify URI or link. Try again or /cancel."
        ),
        "bind_ok": "Bound `{uid}` → {uri} ✅",
        "nothing_pending": "Nothing pending. /help for commands.",
        # ---- main: playback ----
        "tag_not_linked": "Tag scanned but Spotify isn't linked. Use /auth.",
        "playback_failed": "Playback failed: {e}",
        # ---- portal: status banners ----
        "status_no_internet": "No internet connection. Join Wi-Fi to continue.",
        "status_finish_setup": (
            "Finish setup: add your Telegram token and Spotify credentials."
        ),
        "status_claim_ownership": (
            "Message your bot and send /start to claim ownership."
        ),
        "status_lost_contact": (
            "Lost contact via Telegram. Re-check the bot token below, or fix "
            "connectivity."
        ),
        # ---- portal: chrome ----
        "portal_title": "SpotyBox setup",
        "portal_heading": "🎵 SpotyBox setup",
        "portal_lang_legend": "Language",
        # ---- portal: wifi ----
        "portal_wifi_legend": "Wi-Fi",
        "portal_wifi_ssid": "Wi-Fi name (SSID)",
        "portal_wifi_password": "Password",
        "portal_wifi_connect": "Connect",
        "portal_wifi_connected": "Connected — you can close this page.",
        "portal_wifi_failed": "Connection failed.",
        # ---- portal: telegram ----
        "portal_tg_legend": "Telegram bot",
        "portal_tg_token_ph": "Bot token from @BotFather",
        "portal_tg_save": "Save token",
        "portal_tg_help": (
            "Create a bot with @BotFather, paste the token here. After saving, "
            "message your bot and send /start to claim ownership."
        ),
        "portal_tg_saved": "Token saved. The box will restart the bot.",
        "portal_tg_none": "No token provided.",
        # ---- portal: spotify ----
        "portal_sp_legend": "Spotify app credentials",
        "portal_sp_id_ph": "Client ID",
        "portal_sp_secret_ph": "Client secret",
        "portal_sp_save": "Save credentials",
        "portal_sp_help": (
            "From developer.spotify.com/dashboard. Set the redirect URI to "
            "exactly {redirect}."
        ),
        "portal_sp_saved": "Spotify credentials saved.",
        "portal_sp_required": "Both fields are required.",
        "portal_sp_invalid": (
            "Spotify rejected these credentials. Double-check the Client ID "
            "and Client Secret from your app at developer.spotify.com."
        ),
        # ---- portal: oauth callback ----
        "portal_oauth_ok": "Spotify linked. You can close this page.",
        "portal_oauth_missing": "Missing code.",
    },
    "de": {
        # ---- bot: auth/guard ----
        "not_authorized": "Nicht autorisiert.",
        # ---- bot: startup health probe ----
        "hello": (
            "👋 SpotyBox ist online. Tippe zur Bestätigung, dass du mich "
            "erreichst — sonst öffne ich in {timeout}s das Einrichtungsportal."
        ),
        "btn_im_here": "✅ Ich bin da",
        "ack_thanks": "Danke!",
        "ack_confirmed": "✅ Verbindung bestätigt. Läuft normal.",
        # ---- bot: unknown tag ----
        "unknown_tag": (
            "🆕 Unbekannter Tag `{uid}`.\nAntworte mit einer Spotify-URI oder "
            "einem Link, um ihn zu verknüpfen, oder /cancel."
        ),
        # ---- bot: help / start ----
        "start_help": (
            "🎵 SpotyBox bereit.\n\n"
            "/status – Status anzeigen\n"
            "/auth – Spotify verknüpfen (Steuerung)\n"
            "/devices – Spotify-Connect-Geräte auflisten\n"
            "/setdevice <id> – Wiedergabe auf ein Gerät festlegen\n"
            "/list – Tags auflisten\n"
            "/rebind <uid> – Tag neu verknüpfen\n"
            "/unbind <uid> – Tag entfernen\n\n"
            "Scanne einen unbekannten Tag und ich frage dich, womit ich ihn "
            "verknüpfen soll."
        ),
        # ---- bot: status ----
        "spotify_linked_short": "verknüpft ✅",
        "spotify_not_linked_short": "NICHT verknüpft ❌ (/auth)",
        "status_spotify": "Spotify: {auth}",
        "status_tags": "Verknüpfte Tags: {n}",
        "status_active_device": "Aktives Gerät: {name}",
        "device_none": "keins",
        "status_device_failed": "(Geräteabfrage fehlgeschlagen: {e})",
        # ---- bot: devices ----
        "devices_not_linked": "Spotify ist noch nicht verknüpft. Nutze /auth.",
        "devices_query_failed": "Geräteabfrage fehlgeschlagen: {e}",
        "devices_none": (
            "Keine Geräte gefunden. Läuft der librespot-/Raspotify-Lautsprecher "
            "und ist er angemeldet? Siehe die README zum Starten von librespot "
            "mit --enable-oauth."
        ),
        "devices_hint": (
            "\nNutze /setdevice <id>, um die Wiedergabe auf ein Gerät "
            "festzulegen."
        ),
        # ---- bot: setdevice ----
        "setdevice_usage": "Verwendung: /setdevice <device_id>",
        "setdevice_ok": "Wiedergabe auf Gerät `{dev_id}` festgelegt ✅",
        # ---- bot: auth ----
        "auth_already": (
            "Bereits verknüpft. Verknüpfe trotzdem neu — öffne diese URL:"
        ),
        "auth_prompt": (
            "Öffne diese URL, erlaube den Zugriff und füge dann die "
            "VOLLSTÄNDIGE URL ein, auf der du landest (sie sieht aus wie "
            "http://127.0.0.1:8080/callback?code=...):\n\n{url}"
        ),
        "auth_done": "Spotify verknüpft ✅",
        "auth_failed": (
            "Authentifizierung fehlgeschlagen: {e}\nVersuche /auth erneut."
        ),
        "auth_no_code": (
            "Dieser Link enthält keinen Autorisierungs-Code — es sieht aus, "
            "als hättest du die URL eingefügt, die ich dir geschickt habe. "
            "Öffne sie, klicke auf „Zustimmen“, und füge dann die URL ein, "
            "auf der du landest (sie enthält `?code=`)."
        ),
        # ---- bot: list ----
        "list_empty": "Noch keine Tags verknüpft.",
        # ---- bot: rebind / unbind ----
        "rebind_usage": "Verwendung: /rebind <uid>",
        "rebind_prompt": (
            "OK, sende mir die neue Spotify-URI/den Link für Tag `{uid}`."
        ),
        "unbind_usage": "Verwendung: /unbind <uid>",
        "unbind_removed": "Entfernt.",
        "unbind_missing": "Kein solcher Tag.",
        # ---- bot: cancel / text ----
        "cancelled": "Abgebrochen.",
        "bind_invalid": (
            "Das sieht nicht nach einer Spotify-URI oder einem Link aus. "
            "Versuche es erneut oder /cancel."
        ),
        "bind_ok": "Verknüpft `{uid}` → {uri} ✅",
        "nothing_pending": "Nichts ausstehend. /help für Befehle.",
        # ---- main: playback ----
        "tag_not_linked": (
            "Tag gescannt, aber Spotify ist nicht verknüpft. Nutze /auth."
        ),
        "playback_failed": "Wiedergabe fehlgeschlagen: {e}",
        # ---- portal: status banners ----
        "status_no_internet": (
            "Keine Internetverbindung. Mit WLAN verbinden, um fortzufahren."
        ),
        "status_finish_setup": (
            "Einrichtung abschließen: Telegram-Token und Spotify-Zugangsdaten "
            "hinzufügen."
        ),
        "status_claim_ownership": (
            "Schreibe deinem Bot und sende /start, um die Inhaberschaft zu "
            "übernehmen."
        ),
        "status_lost_contact": (
            "Kontakt über Telegram verloren. Überprüfe unten den Bot-Token oder "
            "behebe die Verbindung."
        ),
        # ---- portal: chrome ----
        "portal_title": "SpotyBox Einrichtung",
        "portal_heading": "🎵 SpotyBox Einrichtung",
        "portal_lang_legend": "Sprache",
        # ---- portal: wifi ----
        "portal_wifi_legend": "WLAN",
        "portal_wifi_ssid": "WLAN-Name (SSID)",
        "portal_wifi_password": "Passwort",
        "portal_wifi_connect": "Verbinden",
        "portal_wifi_connected": "Verbunden — du kannst diese Seite schließen.",
        "portal_wifi_failed": "Verbindung fehlgeschlagen.",
        # ---- portal: telegram ----
        "portal_tg_legend": "Telegram-Bot",
        "portal_tg_token_ph": "Bot-Token von @BotFather",
        "portal_tg_save": "Token speichern",
        "portal_tg_help": (
            "Erstelle einen Bot mit @BotFather und füge den Token hier ein. "
            "Nach dem Speichern schreibe deinem Bot und sende /start, um die "
            "Inhaberschaft zu übernehmen."
        ),
        "portal_tg_saved": "Token gespeichert. Die Box startet den Bot neu.",
        "portal_tg_none": "Kein Token angegeben.",
        # ---- portal: spotify ----
        "portal_sp_legend": "Spotify-App-Zugangsdaten",
        "portal_sp_id_ph": "Client ID",
        "portal_sp_secret_ph": "Client Secret",
        "portal_sp_save": "Zugangsdaten speichern",
        "portal_sp_help": (
            "Von developer.spotify.com/dashboard. Setze die Redirect-URI exakt "
            "auf {redirect}."
        ),
        "portal_sp_saved": "Spotify-Zugangsdaten gespeichert.",
        "portal_sp_required": "Beide Felder sind erforderlich.",
        "portal_sp_invalid": (
            "Spotify hat diese Zugangsdaten abgelehnt. Prüfe die Client-ID "
            "und das Client-Secret deiner App auf developer.spotify.com."
        ),
        # ---- portal: oauth callback ----
        "portal_oauth_ok": "Spotify verknüpft. Du kannst diese Seite schließen.",
        "portal_oauth_missing": "Code fehlt.",
    },
}


def normalize_lang(code: str | None) -> str:
    """Return a supported language code, falling back to the default."""
    if code and code in TRANSLATIONS:
        return code
    return DEFAULT_LANG


def translate(lang: str, key: str, **kwargs) -> str:
    """Look up `key` in `lang`, falling back to English, then to the key."""
    table = TRANSLATIONS.get(lang) or TRANSLATIONS[DEFAULT_LANG]
    template = table.get(key)
    if template is None:
        template = TRANSLATIONS[DEFAULT_LANG].get(key, key)
    return template.format(**kwargs) if kwargs else template


class Translator:
    """Callable bound to a Store; resolves the language fresh on every lookup."""

    def __init__(self, store: "Store"):
        self.store = store

    @property
    def lang(self) -> str:
        return normalize_lang(self.store.get_config(K_LANG))

    def __call__(self, key: str, **kwargs) -> str:
        return translate(self.lang, key, **kwargs)
