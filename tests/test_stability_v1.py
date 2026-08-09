from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from slipform.db import (
    create_colado,
    delete_demo_data,
    get_readings,
    get_schema_version,
    init_db,
    insert_reading,
)
from slipform.services.backups import create_sqlite_backup, list_sqlite_backups


class StabilityV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.conn.execute("INSERT INTO mezclas(id, nombre) VALUES (1, 'M1')")

    def tearDown(self) -> None:
        self.conn.close()

    def test_schema_version_is_recorded(self) -> None:
        schema = get_schema_version(self.conn)
        self.assertGreaterEqual(schema["version"], 9)
        self.assertEqual(schema["description"], "preserve_active_advance_recipes")

    def test_reading_validation_accepts_estimated_origin(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        insert_reading(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-24T09:05",
                "temperatura_concreto_c": 28.5,
                "origen": "estimado",
            },
        )
        readings = get_readings(self.conn, colado_id)
        self.assertEqual(readings[0]["origen"], "estimado")

    def test_reading_validation_blocks_out_of_range_humidity(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        with self.assertRaises(ValueError):
            insert_reading(
                self.conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": "2026-07-24T09:05",
                    "temperatura_concreto_c": 28.5,
                    "humedad_relativa_pct": 130,
                },
            )

    def test_delete_demo_data_keeps_real_colados(self) -> None:
        real_id = create_colado(
            self.conn,
            {"silo_id": "REAL", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        demo_id = create_colado(
            self.conn,
            {
                "silo_id": "DEMO",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-24T09:00",
                "es_demo": True,
            },
        )
        result = delete_demo_data(self.conn, operator="Test")
        remaining = self.conn.execute("SELECT id FROM colados ORDER BY id").fetchall()
        self.assertEqual(result["colados_eliminados"], [demo_id])
        self.assertEqual([row["id"] for row in remaining], [real_id])

    def test_create_sqlite_backup_lists_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "slipform.sqlite"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO sample(id) VALUES (1)")
                conn.commit()
            finally:
                conn.close()
            backup = create_sqlite_backup(db_path, "unit_test")
            backups = list_sqlite_backups(db_path)
            self.assertTrue(Path(backup["ruta"]).exists())
            self.assertEqual(backups[0]["nombre"], backup["nombre"])


if __name__ == "__main__":
    unittest.main()
