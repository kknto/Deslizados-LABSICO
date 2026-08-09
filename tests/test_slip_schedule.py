from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from slipform.domain.slip_schedule import calculate_slipform_schedule, resolve_cylinder_scenario
from slipform.http.operation_handlers import handle_post
from slipform.http.query_handlers import handle_get
from slipform.repositories.schema import init_db


class SlipScheduleTests(unittest.TestCase):
    def test_four_hour_scenario_matches_board_times(self) -> None:
        result = calculate_slipform_schedule("2026-07-24T18:00", "SCENARIO_4H")
        self.assertEqual([item["hora_programada"][11:16] for item in result["capas"]], [
            "18:00",
            "19:20",
            "20:40",
            "22:00",
            "23:20",
            "00:40",
            "02:00",
        ])
        self.assertEqual(result["layer_interval_minutes"], 80)
        self.assertEqual(result["receta_sugerida"]["intervalo_objetivo_min"], 8)

    def test_five_hour_scenario_uses_formula_interval(self) -> None:
        result = calculate_slipform_schedule("2026-07-24T18:00", "SCENARIO_5H")
        self.assertEqual([item["hora_programada"][11:16] for item in result["capas"]], [
            "18:00",
            "19:40",
            "21:20",
            "23:00",
            "00:40",
            "02:20",
            "04:00",
        ])
        self.assertEqual(result["layer_interval_minutes"], 100)
        self.assertEqual(result["speed_cm_min"], 0.3)

    def test_six_hour_scenario_rolls_over_midnight(self) -> None:
        result = calculate_slipform_schedule("2026-07-24T18:00", "SCENARIO_6H")
        self.assertEqual([item["hora_programada"][11:16] for item in result["capas"]], [
            "18:00",
            "20:00",
            "22:00",
            "00:00",
            "02:00",
            "04:00",
            "06:00",
        ])
        self.assertEqual(result["capas"][3]["hora_programada"][:10], "2026-07-25")

    def test_cylinder_results_resolve_automatically(self) -> None:
        self.assertEqual(resolve_cylinder_scenario({"resultado_4h": "PASA"})["escenario_activo"], "SCENARIO_4H")
        self.assertEqual(
            resolve_cylinder_scenario({"resultado_4h": "FALLA", "resultado_5h": "PASA"})["escenario_activo"],
            "SCENARIO_5H",
        )
        self.assertEqual(
            resolve_cylinder_scenario({"resultado_4h": "FALLA", "resultado_5h": "FALLA", "resultado_6h": "PASA"})[
                "escenario_activo"
            ],
            "SCENARIO_6H",
        )
        self.assertEqual(
            resolve_cylinder_scenario({"resultado_4h": "FALLA", "resultado_5h": "FALLA", "resultado_6h": "FALLA"})[
                "estado"
            ],
            "REQUIERE_SUPERVISOR",
        )

    def test_cylinder_results_require_sequential_capture(self) -> None:
        with self.assertRaises(ValueError):
            resolve_cylinder_scenario({"resultado_4h": "PENDIENTE", "resultado_5h": "PASA"})
        with self.assertRaises(ValueError):
            resolve_cylinder_scenario({"resultado_4h": "FALLA", "resultado_5h": "PENDIENTE", "resultado_6h": "PASA"})

    def test_schedule_from_zone_uses_total_layers_as_final_zone(self) -> None:
        result = calculate_slipform_schedule("2026-07-24T11:00", "SCENARIO_6H", start_zone=3, total_layers=7)
        self.assertEqual([item["zona_numero"] for item in result["capas"]], [3, 4, 5, 6, 7])
        self.assertEqual([item["hora_programada"][11:16] for item in result["capas"]], [
            "11:00",
            "13:00",
            "15:00",
            "17:00",
            "19:00",
        ])


class SlipScheduleEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "slipform.sqlite"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute("INSERT INTO mezclas(id, nombre) VALUES (1, 'M1')")
            conn.execute(
                """
                INSERT INTO colados(id, silo_id, mezcla_id, fecha_hora_inicio)
                VALUES (1, 'S1', 1, '2026-07-24T18:00')
                """
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_post_cylinder_test_creates_active_schedule(self) -> None:
        status, body = handle_post(
            "/api/programa-deslizado/ensayo",
            self.db_path,
            {
                "colado_id": 1,
                "t_fabricacion": "2026-07-24T18:00",
                "resultado_4h": "FALLA",
                "resultado_5h": "PASA",
                "layer_thickness_cm": 30,
                "total_layers": 7,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["ensayo"]["escenario_activo"], "SCENARIO_5H")
        self.assertEqual(body["programa"]["speed_cm_h"], 18)
        self.assertEqual(len(body["capas"]), 7)

        status, queried = handle_get("/api/programa-deslizado", "colado_id=1", self.db_path)
        self.assertEqual(status, 200)
        self.assertEqual(queried["capas"][1]["hora_programada"], "2026-07-24T19:40")
        self.assertEqual(queried["siguiente_zona_programa"], 1)
        self.assertFalse(queried["puede_evaluar"])

    def test_new_revision_recalculates_from_start_zone_only(self) -> None:
        status, first = handle_post(
            "/api/programa-deslizado/ensayo",
            self.db_path,
            {
                "colado_id": 1,
                "t_fabricacion": "2026-07-24T09:00",
                "resultado_4h": "PASA",
                "layer_thickness_cm": 30,
                "total_layers": 7,
                "start_zone": 1,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(first["capas"][0]["hora_programada"], "2026-07-24T09:00")
        self.assertEqual(first["capas"][2]["hora_programada"], "2026-07-24T11:40")

        status, second = handle_post(
            "/api/programa-deslizado/ensayo",
            self.db_path,
            {
                "colado_id": 1,
                "t_fabricacion": "2026-07-24T11:00",
                "resultado_4h": "FALLA",
                "resultado_5h": "FALLA",
                "resultado_6h": "PASA",
                "layer_thickness_cm": 30,
                "total_layers": 7,
                "start_zone": 3,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual([item["zona_numero"] for item in second["capas"]], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(second["capas"][0]["hora_programada"], "2026-07-24T09:00")
        self.assertEqual(second["capas"][1]["hora_programada"], "2026-07-24T10:20")
        self.assertEqual(second["capas"][2]["hora_programada"], "2026-07-24T11:00")
        self.assertEqual(second["capas"][3]["hora_programada"], "2026-07-24T13:00")
        self.assertEqual(second["capas"][2]["escenario"], "SCENARIO_6H")
        self.assertEqual(len(second["historial"]), 2)

    def test_simple_context_suggests_first_unprogrammed_registered_zone(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute(
                """
                INSERT INTO descargas_olla(colado_id, numero_olla, hora_salida_planta)
                VALUES (1, 1, '2026-07-24T09:00'), (1, 2, '2026-07-24T10:00')
                """
            )
            conn.execute(
                """
                INSERT INTO zonas_colado(
                    colado_id, descarga_olla_id, zona_numero, elevacion_inferior_cm,
                    elevacion_superior_cm, hora_inicio_llenado, hora_referencia_madurez, hora_salida_planta, mezcla_id
                )
                VALUES
                    (1, 1, 1, 0, 30, '2026-07-24T09:00', '2026-07-24T09:00', '2026-07-24T09:00', 1),
                    (1, 2, 2, 30, 60, '2026-07-24T10:00', '2026-07-24T10:00', '2026-07-24T10:00', 1)
                """
            )
            conn.commit()
        finally:
            conn.close()

        status, body = handle_get("/api/programa-deslizado", "colado_id=1", self.db_path)
        self.assertEqual(status, 200)
        self.assertEqual(body["siguiente_zona_programa"], 1)
        self.assertEqual(body["salida_planta_sugerida"], "2026-07-24T09:00")
        self.assertTrue(body["puede_evaluar"])
        self.assertEqual(body["zona_evaluacion_cilindro"], 1)
        self.assertEqual(body["salida_planta_evaluacion"], "2026-07-24T09:00")
        self.assertTrue(body["puede_evaluar_cilindro"])

    def test_simple_context_keeps_cylinder_evaluation_on_registered_zone(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute(
                """
                INSERT INTO zonas_colado(
                    colado_id, zona_numero, elevacion_inferior_cm, elevacion_superior_cm,
                    hora_inicio_llenado, hora_referencia_madurez, mezcla_id,
                    origen_generacion, estado
                )
                VALUES (1, 1, 0, 30, '2026-07-24T08:00', '2026-07-24T08:00', 1,
                        'existente_previo', 'EXISTENTE_PREVIO')
                """
            )
            conn.execute(
                """
                INSERT INTO descargas_olla(colado_id, numero_olla, hora_salida_planta)
                VALUES
                    (1, 2, '2026-07-24T09:00'),
                    (1, 3, '2026-07-24T10:00'),
                    (1, 4, '2026-07-24T11:00')
                """
            )
            conn.execute(
                """
                INSERT INTO zonas_colado(
                    colado_id, descarga_olla_id, zona_numero, elevacion_inferior_cm,
                    elevacion_superior_cm, hora_inicio_llenado, hora_referencia_madurez,
                    hora_salida_planta, mezcla_id
                )
                VALUES
                    (1, 1, 2, 30, 60, '2026-07-24T09:00', '2026-07-24T09:00', '2026-07-24T09:00', 1),
                    (1, 2, 3, 60, 90, '2026-07-24T10:00', '2026-07-24T10:00', '2026-07-24T10:00', 1),
                    (1, 3, 4, 90, 120, '2026-07-24T11:00', '2026-07-24T11:00', '2026-07-24T11:00', 1)
                """
            )
            conn.commit()
        finally:
            conn.close()

        status, body = handle_post(
            "/api/programa-deslizado/ensayo",
            self.db_path,
            {
                "colado_id": 1,
                "t_fabricacion": "2026-07-24T09:00",
                "resultado_4h": "PASA",
                "layer_thickness_cm": 30,
                "total_layers": 7,
                "start_zone": 2,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["siguiente_zona_programa"], 5)
        self.assertFalse(body["puede_evaluar"])
        self.assertEqual(body["zona_evaluacion_cilindro"], 3)
        self.assertEqual(body["salida_planta_evaluacion"], "2026-07-24T10:00")
        self.assertTrue(body["puede_evaluar_cilindro"])

    def test_simple_context_skips_inherited_previous_zone(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute(
                """
                INSERT INTO zonas_colado(
                    colado_id, zona_numero, elevacion_inferior_cm, elevacion_superior_cm,
                    hora_inicio_llenado, hora_referencia_madurez, mezcla_id,
                    origen_generacion, estado
                )
                VALUES (1, 1, 0, 30, '2026-07-24T08:00', '2026-07-24T08:00', 1,
                        'existente_previo', 'EXISTENTE_PREVIO')
                """
            )
            conn.commit()
        finally:
            conn.close()

        status, missing = handle_get("/api/programa-deslizado", "colado_id=1", self.db_path)
        self.assertEqual(status, 200)
        self.assertEqual(missing["siguiente_zona_programa"], 2)
        self.assertIsNone(missing["salida_planta_sugerida"])
        self.assertFalse(missing["puede_evaluar"])
        self.assertIn("Zona 2", missing["motivo_bloqueo"])

        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                INSERT INTO descargas_olla(colado_id, numero_olla, hora_salida_planta)
                VALUES (1, 2, '2026-07-24T09:00')
                """
            )
            conn.execute(
                """
                INSERT INTO zonas_colado(
                    colado_id, descarga_olla_id, zona_numero, elevacion_inferior_cm,
                    elevacion_superior_cm, hora_inicio_llenado, hora_referencia_madurez,
                    hora_salida_planta, mezcla_id
                )
                VALUES (1, 1, 2, 30, 60, '2026-07-24T09:00',
                        '2026-07-24T09:00', '2026-07-24T09:00', 1)
                """
            )
            conn.commit()
        finally:
            conn.close()

        status, ready = handle_get("/api/programa-deslizado", "colado_id=1", self.db_path)
        self.assertEqual(status, 200)
        self.assertEqual(ready["siguiente_zona_programa"], 2)
        self.assertEqual(ready["salida_planta_sugerida"], "2026-07-24T09:00")
        self.assertTrue(ready["puede_evaluar"])


if __name__ == "__main__":
    unittest.main()
