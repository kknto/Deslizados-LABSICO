from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from slipform.db import create_colado, init_db
from slipform.http.support_handlers import (
    create_backup,
    get_backups,
    get_audit,
    get_health,
    get_schema,
    ingest_sensor_reading,
    reset_demo_data,
)


class SupportHandlersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "slipform.sqlite"
        self.static_root = Path(self.tmp.name) / "static"
        self.static_root.mkdir()
        (self.static_root / "sw.js").write_text('const CACHE_NAME = "test-cache";\n', encoding="utf-8")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute("INSERT INTO mezclas(id, nombre) VALUES (1, 'M1')")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_health_and_schema_handlers(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            create_colado(
                conn,
                {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
            )
        finally:
            conn.close()
        health = get_health(self.db_path, self.static_root)
        schema = get_schema(self.db_path)
        self.assertTrue(health["ok"])
        self.assertEqual(health["frontend"]["service_worker"], "test-cache")
        self.assertGreaterEqual(schema["schema"]["version"], 2)

    def test_backup_and_demo_reset_handlers(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            create_colado(
                conn,
                {
                    "silo_id": "DEMO",
                    "mezcla_id": 1,
                    "hora_colocacion_en_molde": "2026-07-24T09:00",
                    "es_demo": True,
                },
            )
        finally:
            conn.close()
        backup = create_backup(self.db_path, {"motivo": "handler_test"})
        reset = reset_demo_data(self.db_path, {"operador": "Test"})
        backups = get_backups(self.db_path)
        audit = get_audit(self.db_path, limit=10)
        self.assertTrue(Path(backup["backup"]["ruta"]).exists())
        self.assertEqual(reset["resultado"]["total"], 1)
        self.assertGreaterEqual(len(backups["backups"]), 2)
        self.assertTrue(any(row["accion"] == "DELETE_DEMO_DATA" for row in audit["auditoria"]))

    def test_sensor_ingest_handler_uses_sensor_origin(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            colado_id = create_colado(
                conn,
                {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
            )
        finally:
            conn.close()
        result = ingest_sensor_reading(
            self.db_path,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-24T09:05",
                "temperatura_concreto_c": 28.5,
            },
        )
        self.assertEqual(result["tipo"], "lectura_colado")


if __name__ == "__main__":
    unittest.main()
