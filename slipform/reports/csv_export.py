"""CSV export helpers shared by HTTP exports and report packages."""

from __future__ import annotations

import csv
from typing import Any


class ListWriter:
    def __init__(self, target: list[str]) -> None:
        self.target = target

    def write(self, text: str) -> None:
        self.target.append(text)


def rows_to_csv(rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> str:
    if fieldnames is None:
        if not rows:
            return ""
        fieldnames = list(rows[0].keys())
    output: list[str] = []
    writer = csv.DictWriter(ListWriter(output), fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return "".join(output)


__all__ = ["ListWriter", "rows_to_csv"]
