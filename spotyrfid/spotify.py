"""Spotify playback control with a SQLite-backed token cache.

This module is the heart of the reauth fix. spotipy's default CacheFileHandler
writes a `.cache` file that is easy to lose (rebuilds, moves, permission
changes) — and losing it forces a full re-auth. Instead we persist the whole
token_info dict (including the non-expiring refresh_token) into SQLite.

Auth flow: Authorization Code (confidential client — the Pi can hold the
secret). Redirect URI MUST be a loopback literal, e.g. http://127.0.0.1:8080,
because Spotify deprecated http://localhost and non-loopback HTTP redirects.

Once authorised, spotipy refreshes the access token automatically from the
stored refresh token. You should never need to re-auth unless the grant is
revoked.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import parse_qs, urlparse

import spotipy
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth

from .store import Store

log = logging.getLogger(__name__)

SCOPES = "user-read-playback-state user-modify-playback-state"
TOKEN_KEY = "spotify_token_info"


class AuthCodeError(ValueError):
    """The pasted text contains no usable Spotify authorization code.

    Distinct from a genuine exchange failure: this means the user almost
    certainly pasted the wrong URL (e.g. the authorize link itself), so the
    bot can tell them exactly what to do instead of showing a raw error.
    """


class SQLiteCacheHandler(CacheHandler):
    """Persist spotipy's token_info dict in the Store instead of a file."""

    def __init__(self, store: Store):
        self.store = store

    def get_cached_token(self):
        return self.store.get_json(TOKEN_KEY)

    def save_token_to_cache(self, token_info):
        self.store.set_json(TOKEN_KEY, token_info)


class SpotifyController:
    def __init__(
        self,
        store: Store,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        device_id: Optional[str] = None,
    ):
        self.store = store
        self.device_id = device_id or store.get_config("preferred_device_id")
        self.auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPES,
            cache_handler=SQLiteCacheHandler(store),
            open_browser=False,  # headless box
        )
        self._sp: Optional[spotipy.Spotify] = None

    # ---- auth -----------------------------------------------------------
    def is_authenticated(self) -> bool:
        return self.auth.cache_handler.get_cached_token() is not None

    def authorize_url(self) -> str:
        """URL the user opens in a browser to grant access."""
        return self.auth.get_authorize_url()

    def complete_auth(self, redirect_response: str) -> None:
        """Exchange the code from the pasted redirect URL for tokens."""
        code = self._extract_code(redirect_response)
        # get_access_token persists via the cache handler (SQLite)
        self.auth.get_access_token(code, as_dict=False, check_cache=False)
        self._sp = None  # force rebuild with fresh creds

    @staticmethod
    def _extract_code(text: str) -> str:
        """Pull the auth code out of a pasted redirect URL (or accept a bare code).

        spotipy's parse_response_code returns the whole string when there's no
        '?code=', so a wrong paste (e.g. the authorize URL, which carries
        response_type=code but no code param) would be sent to Spotify as a
        bogus code and fail with a cryptic invalid_grant. We validate up front.
        """
        text = (text or "").strip()
        if not text:
            raise AuthCodeError("empty input")
        # Looks like a URL or query string -> parse params explicitly.
        if "://" in text or "=" in text or "?" in text:
            query = urlparse(text).query or text.lstrip("?")
            params = parse_qs(query)
            if "error" in params:
                # User denied access (or Spotify returned an error) -> real failure.
                raise ValueError(f"Spotify returned error: {params['error'][0]}")
            codes = params.get("code")
            if codes and codes[0]:
                return codes[0]
            raise AuthCodeError("no 'code' parameter in the pasted URL")
        # No URL punctuation -> assume the user pasted the bare code.
        return text

    @property
    def sp(self) -> spotipy.Spotify:
        if self._sp is None:
            # auth_manager handles transparent refresh from the stored token
            self._sp = spotipy.Spotify(auth_manager=self.auth)
        return self._sp

    # ---- playback -------------------------------------------------------
    def _target_device(self) -> Optional[str]:
        if self.device_id:
            return self.device_id
        # fall back to whatever's active
        state = self.sp.current_playback()
        return state["device"]["id"] if state and state.get("device") else None

    def play_uri(self, uri: str) -> None:
        """Start playback of a context (playlist/album/artist) or track."""
        dev = self._target_device()
        if uri.startswith(("spotify:track:", "spotify:episode:")):
            self.sp.start_playback(device_id=dev, uris=[uri])
        else:  # playlist, album, artist -> context_uri
            self.sp.start_playback(device_id=dev, context_uri=uri)

    def pause(self) -> None:
        self.sp.pause_playback(device_id=self._target_device())

    def playpause(self) -> None:
        state = self.sp.current_playback()
        if state and state.get("is_playing"):
            self.pause()
        else:
            self.sp.start_playback(device_id=self._target_device())

    def next(self) -> None:
        self.sp.next_track(device_id=self._target_device())

    def prev(self) -> None:
        self.sp.previous_track(device_id=self._target_device())

    def set_volume(self, pct: int) -> None:
        pct = max(0, min(100, pct))
        self.sp.volume(pct, device_id=self._target_device())

    def volume_step(self, delta: int) -> None:
        state = self.sp.current_playback()
        cur = state["device"]["volume_percent"] if state else 50
        self.set_volume((cur or 50) + delta)

    def devices(self) -> list[dict]:
        return self.sp.devices().get("devices", [])
