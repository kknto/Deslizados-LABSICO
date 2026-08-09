"""Experimental OCR helpers for handwritten slipform logs."""

from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from slipform.services.written_log_import import (
    EVENTOS_COLUMNS,
    OLLAS_COLUMNS,
    ensure_written_log_templates,
    preview_written_log_import,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:;.hH]([0-5]\d)\b")
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def automatic_written_log_preview(conn, payload: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(payload.get("_project_root") or Path.cwd())
    templates = ensure_written_log_templates(project_root)
    analysis = analyze_written_log_images(project_root)
    csv_payload = {
        **payload,
        "ollas_csv": analysis["csv"]["ollas"],
        "eventos_csv": analysis["csv"]["eventos"],
    }
    preview = preview_written_log_import(conn, csv_payload)
    rows_found = preview["resumen"]["ollas_total"] + preview["resumen"]["eventos_total"]
    preview["puede_importar"] = bool(analysis["motor_disponible"] and rows_found and preview["puede_importar"])
    return {
        "motor": analysis["motor"],
        "motor_disponible": analysis["motor_disponible"],
        "mensaje": analysis["mensaje"],
        "imagenes": analysis["imagenes"],
        "textos": analysis["textos"],
        "csv": analysis["csv"],
        "plantillas": templates,
        "preview": preview,
    }


def analyze_written_log_images(project_root: Path) -> dict[str, Any]:
    root = Path(project_root)
    written_root = root / "Bitacora_escrita"
    output_dir = written_root / "transcripcion"
    raw_dir = output_dir / "ocr_texto"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    engine = _find_tesseract(project_root)
    images = _collect_images(written_root)
    if not engine:
        csv_result = _empty_csv_result()
        _write_generated_csv(output_dir, csv_result)
        return {
            "motor": "tesseract",
            "motor_disponible": False,
            "mensaje": "OCR automatico no disponible: instala Tesseract y vuelve a intentar, o usa transcripcion manual.",
            "imagenes": images,
            "textos": [],
            "csv": csv_result,
        }

    texts: list[dict[str, Any]] = []
    for image in images:
        text, error = _run_tesseract(Path(image["ruta"]), engine)
        raw_path = raw_dir / f"{Path(image['nombre']).stem}.txt"
        raw_path.write_text(text or error or "", encoding="utf-8")
        texts.append({"imagen": image["nombre"], "ruta_texto": str(raw_path), "texto": text, "error": error})

    csv_result = _csv_from_texts(texts)
    _write_generated_csv(output_dir, csv_result)
    return {
        "motor": engine,
        "motor_disponible": True,
        "mensaje": "OCR automatico ejecutado. Revisa los candidatos antes de importar.",
        "imagenes": images,
        "textos": texts,
        "csv": csv_result,
    }


def _find_tesseract(project_root: Path) -> str | None:
    candidates = [
        shutil.which("tesseract"),
        str(Path(project_root) / "runtime" / "tesseract" / "tesseract.exe"),
        str(Path(project_root) / "tools" / "tesseract" / "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _collect_images(written_root: Path) -> list[dict[str, Any]]:
    images = []
    for folder_name, kind in (
        ("Ollas_deslizado", "ollas"),
        ("Bitacora_eventos_deslizado", "eventos"),
    ):
        folder = written_root / folder_name
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                images.append({"tipo": kind, "nombre": path.name, "ruta": str(path), "bytes": path.stat().st_size})
    return images


def _run_tesseract(image_path: Path, engine: str) -> tuple[str, str]:
    command = [engine, str(image_path), "stdout", "-l", "spa+eng", "--psm", "6"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except Exception as exc:
        return "", str(exc)
    text = completed.stdout.strip()
    error = completed.stderr.strip() if completed.returncode else ""
    return text, error


def _csv_from_texts(texts: list[dict[str, Any]]) -> dict[str, str]:
    ollas_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    for item in texts:
        image = item["imagen"]
        text = item.get("texto") or ""
        if image.lower().startswith("ollas"):
            ollas_rows.extend(_parse_ollas_lines(text, image))
        else:
            event_rows.extend(_parse_event_lines(text, image))
    return {"ollas": _rows_to_csv(OLLAS_COLUMNS, ollas_rows), "eventos": _rows_to_csv(EVENTOS_COLUMNS, event_rows)}


def _parse_ollas_lines(text: str, image: str) -> list[dict[str, Any]]:
    rows = []
    for line in _useful_lines(text):
        times = _times(line)
        numbers = _numbers(line)
        if len(times) < 1 or not numbers:
            continue
        number = int(float(numbers[0].replace(",", ".")))
        temperature = _number_near_range(numbers, 10, 60)
        slump = _number_near_range(numbers, 5, 35, after=temperature)
        rows.append(
            {
                "numero_olla": number,
                "hora_salida_planta": times[0] if len(times) > 0 else "",
                "hora_llegada_obra": times[1] if len(times) > 1 else "",
                "hora_inicio_descarga": times[2] if len(times) > 2 else "",
                "hora_fin_descarga": times[3] if len(times) > 3 else "",
                "temperatura_llegada_c": temperature or "",
                "revenimiento_cm": slump or "",
                "zona_numero": number,
                "altura_capa_cm": 30,
                "hora_4h": times[4] if len(times) > 4 else "",
                "hora_5h": times[5] if len(times) > 5 else "",
                "hora_6h": times[6] if len(times) > 6 else "",
                "fuente_imagen": image,
                "observaciones": f"OCR experimental: {line}",
            }
        )
    return rows


def _parse_event_lines(text: str, image: str) -> list[dict[str, Any]]:
    rows = []
    for index, line in enumerate(_useful_lines(text), start=1):
        times = _times(line)
        if not times:
            continue
        cleaned = TIME_RE.sub("", line).strip(" -:;")
        rows.append(
            {
                "fecha_hora": "",
                "hora_original": times[0],
                "tipo_evento": "OBSERVACION",
                "descripcion_original": cleaned or line,
                "decision_tomada": "REGISTRO_BITACORA",
                "resultado_fisico": "ocr_pendiente_revision",
                "supervisor": "",
                "fuente_imagen": image,
                "linea_fuente": index,
            }
        )
    return rows


def _useful_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if len(line.strip()) >= 4]


def _times(text: str) -> list[str]:
    return [f"{int(match.group(1)):02d}:{match.group(2)}" for match in TIME_RE.finditer(text)]


def _numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(text)


def _number_near_range(numbers: list[str], low: float, high: float, after: str | None = None) -> str | None:
    passed_after = after is None
    for raw in numbers:
        value = float(raw.replace(",", "."))
        if not passed_after:
            passed_after = raw == after
            continue
        if low <= value <= high:
            return raw.replace(",", ".")
    return None


def _empty_csv_result() -> dict[str, str]:
    return {"ollas": _rows_to_csv(OLLAS_COLUMNS, []), "eventos": _rows_to_csv(EVENTOS_COLUMNS, [])}


def _rows_to_csv(columns: list[str], rows: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return output.getvalue()


def _write_generated_csv(output_dir: Path, csv_result: dict[str, str]) -> None:
    (output_dir / "ocr_ollas_deslizado.csv").write_text(csv_result["ollas"], encoding="utf-8")
    (output_dir / "ocr_eventos_deslizado.csv").write_text(csv_result["eventos"], encoding="utf-8")


__all__ = ["analyze_written_log_images", "automatic_written_log_preview"]
