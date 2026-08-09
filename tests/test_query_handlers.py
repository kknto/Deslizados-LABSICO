from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from slipform.db import create_colado, init_db
from slipform.http.query_handlers import handle_get


class QueryHandlersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "slipform.sqlite"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute("INSERT INTO mezclas(id, nombre) VALUES (1, 'M1')")
            create_colado(
                conn,
                {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bootstrap_and_project(self) -> None:
        status, bootstrap = handle_get("/api/bootstrap", "", self.db_path)
        self.assertEqual(status, 200)
        self.assertEqual(len(bootstrap["colados"]), 1)

        status, project = handle_get("/api/proyecto", "", self.db_path)
        self.assertEqual(status, 200)
        self.assertIn("proyecto", project)

    def test_bootstrap_reports_latest_sensor_status_without_group_by_laxness(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                INSERT INTO lecturas(
                    colado_id, sensor_id, fecha_hora, minuto_transcurrido,
                    temperatura_concreto_c, temperatura_ambiente_c,
                    humedad_relativa_pct, origen
                )
                VALUES
                    (1, NULL, '2026-07-24T09:05', 5, 28.0, 30.0, 70.0, 'sensor'),
                    (1, NULL, '2026-07-24T09:10', 10, 29.0, 31.0, 71.0, 'sensor'),
                    (1, 7, '2026-07-24T09:15', 15, 30.0, 32.0, 72.0, 'sensor')
                """
            )
            conn.commit()
        finally:
            conn.close()

        status, bootstrap = handle_get("/api/bootstrap", "", self.db_path)

        self.assertEqual(status, 200)
        self.assertEqual(len(bootstrap["sensores"]), 2)
        self.assertEqual(bootstrap["sensores"][0]["sensor"], "sin_id")
        self.assertEqual(bootstrap["sensores"][0]["ultima_fecha_hora"], "2026-07-24T09:10")
        self.assertEqual(bootstrap["sensores"][1]["sensor"], "7")

    def test_mold_state_endpoint_contract(self) -> None:
        status, state = handle_get("/api/molde/estado", "colado_id=1", self.db_path)
        self.assertEqual(status, 200)
        self.assertIn("estado_operativo", state)

    def test_data_quality_endpoint_reports_issues(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                INSERT INTO descargas_olla(colado_id, numero_olla, hora_salida_planta)
                VALUES (1, 1, '2099-07-24T09:00')
                """
            )
            conn.commit()
        finally:
            conn.close()

        status, body = handle_get("/api/calidad-datos", "colado_id=1", self.db_path)
        self.assertEqual(status, 200)
        quality = body["calidad_datos"]
        self.assertEqual(quality["status"], "critical")
        self.assertTrue(any(issue["code"] == "HORA_FUTURA" for issue in quality["issues"]))

    def test_unknown_get_returns_none(self) -> None:
        self.assertIsNone(handle_get("/api/no-existe", "", self.db_path))


if __name__ == "__main__":
    unittest.main()
