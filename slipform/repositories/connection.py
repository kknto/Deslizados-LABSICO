"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("data/slipform.sqlite")


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()
        return False


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


__all__ = ["ClosingConnection", "DEFAULT_DB_PATH", "connect"]
