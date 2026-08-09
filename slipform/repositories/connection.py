"""Database connection helpers for local SQLite and cloud PostgreSQL."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DB_PATH = Path("data/slipform.sqlite")


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()
        return False


class CompatRow:
    def __init__(self, columns: list[str], values: tuple[Any, ...]) -> None:
        self._columns = columns
        self._values = values
        self._index = {name: index for index, name in enumerate(columns)}

    def __getitem__(self, key: int | str) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._index[key]]

    def __iter__(self):
        return iter(self._columns)

    def keys(self) -> list[str]:
        return list(self._columns)


class PostgresCursor:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return CompatRow(self._columns(), tuple(row))

    def fetchall(self) -> list[CompatRow]:
        columns = self._columns()
        return [CompatRow(columns, tuple(row)) for row in self._cursor.fetchall()]

    def _columns(self) -> list[str]:
        if not self._cursor.description:
            return []
        return [column.name for column in self._cursor.description]


class PostgresConnection:
    engine = "postgres"

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Falta instalar psycopg[binary] para usar PostgreSQL.") from exc
        self._conn = psycopg.connect(dsn)

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> PostgresCursor:
        cursor = self._conn.cursor()
        cursor.execute(_qmark_to_psycopg(sql), tuple(params or ()))
        return PostgresCursor(cursor)

    def executemany(self, sql: str, params_seq: Iterable[Iterable[Any]]) -> PostgresCursor:
        cursor = self._conn.cursor()
        cursor.executemany(_qmark_to_psycopg(sql), [tuple(params) for params in params_seq])
        return PostgresCursor(cursor)

    def executescript(self, script: str) -> None:
        for statement in _split_sql_script(script):
            self.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or None


def database_engine(conn: Any | None = None) -> str:
    if conn is not None and getattr(conn, "engine", None) == "postgres":
        return "postgres"
    return "postgres" if database_url() else "sqlite"


def connect(path: Path | str = DEFAULT_DB_PATH):
    dsn = database_url()
    if dsn:
        return PostgresConnection(dsn)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _qmark_to_psycopg(sql: str) -> str:
    return sql.replace("?", "%s")


def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    for char in script:
        if char == "'":
            in_single_quote = not in_single_quote
        if char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


__all__ = [
    "ClosingConnection",
    "CompatRow",
    "DEFAULT_DB_PATH",
    "PostgresConnection",
    "connect",
    "database_engine",
    "database_url",
]
