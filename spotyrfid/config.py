"""Configuration: SQLite config table is the source of truth; env vars seed it.

Rationale: this is a standalone box configured in the field through the setup
portal, which writes secrets into the SQLite `config` table. Those portal-saved
values are authoritative. Environment variables (systemd EnvironmentFile) are an
optional first-boot *seed* only — read when SQLite has no value yet — so a box
can be pre-provisioned, but anything saved via the portal always wins.

(Precedence was deliberately chosen this way: an env value that outranks the
portal would let a stale/placeholder .env trap the box in setup mode forever,
shadowing the token the user just saved.)

Missing secrets do NOT abort the process. We need to boot far enough to bring up
the setup portal so the user can supply them. `is_complete()` tells the
orchestrator whether the bot can start at all.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .store import Store

# keys used in the SQLite config table for portal-written secrets
K_TG_TOKEN = "telegram_token"
K_SP_ID = "spotify_client_id"
K_SP_SECRET = "spotify_client_secret"

# Dummy values shipped in spoty-rfid.env.example. If an install copied the
# example verbatim, these end up as real (non-empty) env vars and would shadow
# anything the portal saves to SQLite — trapping the box in setup mode. Treat
# them as "unset" so the portal-saved value can take over.
_PLACEHOLDERS = {
    "123456:abc-your-bot-token",
    "xxxxxxxxxxxxxxxx",
}


def _is_placeholder(v: Optional[str]) -> bool:
    return v is not None and v.strip().lower() in _PLACEHOLDERS


@dataclass
class Config:
    telegram_token: Optional[str]
    spotify_client_id: Optional[str]
    spotify_client_secret: Optional[str]
    spotify_redirect_uri: str = "http://127.0.0.1:8080/callback"
    spotify_device_id: Optional[str] = None
    rfid_device: str = "/dev/hidraw0"
    web_port: int = 8080
    ap_ssid: str = "SpotyBox"
    ap_password: str = "changeme123"
    wifi_iface: str = "wlan0"
    ack_timeout: int = 60  # seconds to wait for the startup "I'm here" tap

    @classmethod
    def load(cls, store: Store) -> "Config":
        def val(env_key: str, store_key: Optional[str] = None) -> Optional[str]:
            # SQLite (portal-saved) is the source of truth; env is only a seed
            # used when SQLite has no value. Placeholder seeds count as unset.
            if store_key:
                v = store.get_config(store_key)
                if v and not _is_placeholder(v):
                    return v
            v = os.environ.get(env_key)
            if v and not _is_placeholder(v):
                return v
            return None

        return cls(
            telegram_token=val("TELEGRAM_TOKEN", K_TG_TOKEN),
            spotify_client_id=val("SPOTIFY_CLIENT_ID", K_SP_ID),
            spotify_client_secret=val("SPOTIFY_CLIENT_SECRET", K_SP_SECRET),
            spotify_redirect_uri=os.environ.get(
                "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8080/callback"
            ),
            spotify_device_id=os.environ.get("SPOTIFY_DEVICE_ID") or None,
            rfid_device=os.environ.get("RFID_DEVICE", "/dev/hidraw0"),
            web_port=int(os.environ.get("WEB_PORT", "8080")),
            ap_ssid=os.environ.get("AP_SSID", "SpotyBox"),
            ap_password=os.environ.get("AP_PASSWORD", "changeme123"),
            wifi_iface=os.environ.get("WIFI_IFACE", "wlan0"),
            ack_timeout=int(os.environ.get("ACK_TIMEOUT", "60")),
        )

    def has_bot_token(self) -> bool:
        return bool(self.telegram_token)

    def has_spotify_creds(self) -> bool:
        return bool(self.spotify_client_id and self.spotify_client_secret)

    def is_complete(self) -> bool:
        """Enough to start the bot. (Owner-chat check is separate, in Store.)"""
        return self.has_bot_token() and self.has_spotify_creds()
