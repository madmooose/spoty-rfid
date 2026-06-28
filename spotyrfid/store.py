"""SQLite-backed persistence: tag bindings, Spotify token, key/value config.

Everything the box needs to survive a reboot lives here, in one file, so it can
be backed up trivially. The Spotify refresh token in particular MUST persist —
losing it is what forces re-authentication.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

DEFAULT_DB = Path.home() / ".local" / "share" / "spoty-rfid" / "store.db"


class Store:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because the hidraw reader runs in its own
        # thread; we serialise all access with a lock instead.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tags (
                    uid     TEXT PRIMARY KEY,
                    uri     TEXT NOT NULL,
                    label   TEXT,
                    created TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS config (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    # ---- config / kv (also used by the Spotify cache handler) -----------
    def get_config(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_config(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO config(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_json(self, key: str) -> Optional[dict]:
        raw = self.get_config(key)
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: dict) -> None:
        self.set_config(key, json.dumps(value))

    # ---- tag bindings ---------------------------------------------------
    def get_tag(self, uid: str) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM tags WHERE uid = ?", (uid,)
            ).fetchone()

    def bind_tag(self, uid: str, uri: str, label: str | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO tags(uid, uri, label) VALUES(?, ?, ?) "
                "ON CONFLICT(uid) DO UPDATE SET uri = excluded.uri, "
                "label = excluded.label",
                (uid, uri, label),
            )

    def unbind_tag(self, uid: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM tags WHERE uid = ?", (uid,))
        return cur.rowcount > 0

    def list_tags(self) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM tags ORDER BY created"
            ).fetchall()
