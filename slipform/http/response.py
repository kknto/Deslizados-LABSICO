"""Reusable HTTP response helpers."""

from __future__ import annotations

import csv
import io
import json
from typing import Any


class ListWriter:
    """Small file-like adapter used by csv.writer to return strings."""

    def write(self, value: str) -> str:
        return value


def json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


__all__ = ["ListWriter", "json_bytes", "rows_to_csv"]
