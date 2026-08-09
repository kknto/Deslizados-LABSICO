from __future__ import annotations

import json
import mimetypes
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from slipform.core import calculate_state
from slipform.cloud_init import initialize_database
from slipform.domain.data_quality import DataQualityWarningError
from slipform.db import (
    connect,
    get_events,
    get_colado,
    get_readings,
    get_reference_points,
    init_db,
    insert_prediction,
)
from slipform.http.support_handlers import (
    create_backup as support_create_backup,
    get_backups as support_get_backups,
    get_audit as support_get_audit,
    get_health as support_get_health,
    get_schema as support_get_schema,
    ingest_sensor_reading as support_ingest_sensor_reading,
    reset_demo_data as support_reset_demo_data,
)
from slipform.http.operation_handlers import handle_delete, handle_post, handle_put
from slipform.http.query_handlers import handle_get
from slipform.http.report_handlers import handle_report_get

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
DB_PATH = Path(os.environ.get("SLIPFORM_DB_PATH") or ROOT / "data" / "slipform.sqlite")


def resolve_runtime_config(host: str | None = None, port: int | None = None) -> tuple[str, int]:
    bind_host = host or os.environ.get("SLIPFORM_HOST") or os.environ.get("HOST") or "127.0.0.1"
    raw_port = port or os.environ.get("PORT") or os.environ.get("SLIPFORM_PORT") or 8010
    return bind_host, int(raw_port)


class SlipformHandler(BaseHTTPRequestHandler):
    server_version = "SlipformMVP/1.0"

    def do_GET(self) -> None:
        try:
            self._handle_get()
        except (KeyError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _handle_get(self) -> None:
        parsed = urlparse(self.path)
        handled = handle_get(parsed.path, parsed.query, DB_PATH)
        if handled is not None:
            status, body = handled
            self._json(status, body)
            return
        if parsed.path == "/api/health":
            self._json(200, support_get_health(DB_PATH, STATIC))
            return
        if parsed.path == "/api/schema/version":
            self._json(200, support_get_schema(DB_PATH))
            return
        if parsed.path == "/api/backups":
            self._json(200, support_get_backups(DB_PATH))
            return
        if parsed.path == "/api/auditoria":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["100"])[0])
            self._json(200, support_get_audit(DB_PATH, limit=limit))
            return
        if parsed.path == "/api/prediccion":
            query = parse_qs(parsed.query)
            colado_id = int(query.get("colado_id", ["0"])[0])
            self._prediction(colado_id)
            return
        report_response = handle_report_get(parsed.path, parsed.query, DB_PATH)
        if report_response is not None:
            self._bytes(*report_response)
            return
        self._static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()
        try:
            if parsed.path == "/api/sensores/ingesta":
                self._json(201, support_ingest_sensor_reading(DB_PATH, payload))
                return
            if parsed.path == "/api/backups":
                self._json(201, support_create_backup(DB_PATH, payload))
                return
            if parsed.path == "/api/demo/reset":
                self._json(200, support_reset_demo_data(DB_PATH, payload))
                return
            handled = handle_post(parsed.path, DB_PATH, payload)
            if handled is not None:
                status, body = handled
                self._json(status, body)
                return
            self._json(404, {"error": "Ruta no encontrada."})
        except DataQualityWarningError as exc:
            self._json(409, {"error": str(exc), "requiere_confirmacion": True, "advertencias": exc.warnings})
        except (KeyError, ValueError) as exc:
            self._json(400, {"error": str(exc)})

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()
        try:
            handled = handle_put(parsed.path, DB_PATH, payload, _path_id)
            if handled is not None:
                status, body = handled
                self._json(status, body)
                return
            self._json(404, {"error": "Ruta no encontrada."})
        except DataQualityWarningError as exc:
            self._json(409, {"error": str(exc), "requiere_confirmacion": True, "advertencias": exc.warnings})
        except (KeyError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            handled = handle_delete(parsed.path, DB_PATH, _path_id)
            if handled is not None:
                status, body = handled
                self._json(status, body)
                return
            self._json(404, {"error": "Ruta no encontrada."})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _prediction(self, colado_id: int) -> None:
        with connect(DB_PATH) as conn:
            init_db(conn)
            colado = get_colado(conn, colado_id)
            if not colado:
                self._json(404, {"error": "Colado no encontrado."})
                return
            params = colado.get("parametros")
            readings = get_readings(conn, colado_id)
            events = get_events(conn, colado_id)
            reference = get_reference_points(conn, colado.get("curva_id"))
            prediction = calculate_state(
                readings,
                params,
                reference,
                now_iso=datetime.now().isoformat(timespec="seconds"),
            )
            insert_prediction(conn, colado_id, prediction)
            self._json(
                200,
                prediction
                | {
                    "colado": colado,
                    "lecturas": readings,
                    "eventos": events,
                    "referencia": reference[:: max(1, len(reference) // 300)] if reference else [],
                },
            )

    def _static(self, path: str) -> None:
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        target = STATIC / ("index.html" if path in ("", "/") else path.lstrip("/"))
        if not target.exists() or not target.resolve().is_relative_to(STATIC.resolve()):
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(target.read_bytes())

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def _path_id(path: str, prefix: str) -> int:
    raw = path.removeprefix(prefix).strip("/")
    if not raw or "/" in raw:
        raise ValueError("Identificador invalido.")
    return int(raw)


def run(host: str | None = None, port: int | None = None) -> None:
    host, port = resolve_runtime_config(host, port)
    initialize_database(DB_PATH)
    server = ThreadingHTTPServer((host, port), SlipformHandler)
    print(f"Servidor iniciado en http://{host}:{port}")
    print(f"Base local SQLite: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    run()
