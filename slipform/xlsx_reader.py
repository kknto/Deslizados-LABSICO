from __future__ import annotations

import re
import statistics
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

SHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def read_workbook(path: str | Path) -> dict[str, list[list[Any]]]:
    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            rel.attrib["Id"]: _normalize_target(rel.attrib["Target"])
            for rel in rels.findall("rel:Relationship", REL_NS)
        }
        sheets: dict[str, list[list[Any]]] = {}
        for sheet in workbook.findall(".//a:sheet", SHEET_NS):
            name = sheet.attrib["name"]
            root = ET.fromstring(archive.read(targets[sheet.attrib[RID]]))
            rows: dict[int, dict[int, Any]] = {}
            for cell in root.findall(".//a:sheetData/a:row/a:c", SHEET_NS):
                ref = cell.attrib.get("r", "")
                row, column = _cell_ref(ref)
                value = _cell_value(cell, shared)
                if value is not None:
                    rows.setdefault(row, {})[column] = value
            width = max((max(row.keys()) for row in rows.values()), default=0)
            result = []
            for row_index in range(1, max(rows.keys(), default=0) + 1):
                result.append([rows.get(row_index, {}).get(col) for col in range(1, width + 1)])
            sheets[name] = result
        return sheets


def normalize_temperature_curves(path: str | Path) -> list[dict[str, Any]]:
    curves: list[dict[str, Any]] = []
    for sheet_name, rows in read_workbook(path).items():
        if len(rows) < 3:
            continue
        headers = rows[1]
        if not headers or str(headers[0]).lower() != "num":
            continue
        raw_times = [_to_float(row[0]) for row in rows[2:] if row and _to_float(row[0]) is not None]
        if len(raw_times) < 2:
            continue
        minutes = _excel_time_to_elapsed_minutes(raw_times)
        for column_index, header in enumerate(headers[1:], start=1):
            if not header:
                continue
            points = []
            for offset, row in enumerate(rows[2:]):
                if offset >= len(minutes):
                    break
                if column_index >= len(row):
                    continue
                temp = _to_float(row[column_index])
                if temp is None:
                    continue
                points.append(
                    {
                        "minuto": round(minutes[offset], 6),
                        "temperatura_concreto_c": temp,
                    }
                )
            if len(points) >= 10:
                curves.append(
                    {
                        "sheet_name": sheet_name,
                        "nombre_curva": str(header),
                        "points": points,
                    }
                )
    return curves


def _excel_time_to_elapsed_minutes(values: list[float]) -> list[float]:
    diffs = [b - a for a, b in zip(values, values[1:]) if b > a]
    step = statistics.median(diffs) if diffs else 0.0
    first = values[0]
    if first > 0.1:
        return [(value - first + step) * 1440.0 for value in values]
    return [value * 1440.0 for value in values]


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(text.text or "" for text in item.findall(".//a:t", SHEET_NS))
        for item in root.findall("a:si", SHEET_NS)
    ]


def _cell_value(cell: ET.Element, shared: list[str]) -> Any:
    value = cell.find("a:v", SHEET_NS)
    if value is None:
        if cell.attrib.get("t") == "inlineStr":
            return "".join(text.text or "" for text in cell.findall(".//a:t", SHEET_NS))
        return None
    raw = value.text
    if cell.attrib.get("t") == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def _cell_ref(ref: str) -> tuple[int, int]:
    match = re.match(r"([A-Z]+)(\d+)", ref)
    if not match:
        raise ValueError(f"Referencia de celda inválida: {ref}")
    column = 0
    for char in match.group(1):
        column = column * 26 + ord(char) - 64
    return int(match.group(2)), column


def _normalize_target(target: str) -> str:
    target = target.lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

