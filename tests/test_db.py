from __future__ import annotations

import sqlite3
import unittest

from slipform.db import (
    create_colado,
    delete_colado,
    get_active_advance_recipe,
    get_active_project,
    get_sensor_health,
    get_colado,
    init_db,
    insert_model_adjustment,
    insert_operator_decision,
    insert_photo_evidence,
    insert_plumb_reading,
    insert_reading,
    insert_shift_detail,
    insert_slide_event,
    insert_mold_advance,
    register_truck_zone,
    list_model_adjustments,
    list_operator_decisions,
    list_photo_evidence,
    list_plumb_readings,
    list_shift_details,
    upsert_advance_recipe,
    upsert_project,
    update_colado,
)


class DbTests(unittest.TestCase):
    def memory_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    def test_colados_has_operational_time_fields(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(colados)").fetchall()}
        self.assertIn("hora_salida_planta", columns)
        self.assertIn("hora_llegada_obra", columns)
        self.assertIn("hora_inicio_descarga", columns)
        self.assertIn("hora_colocacion_en_molde", columns)
        self.assertIn("hora_fin_descarga", columns)
        self.assertIn("fecha_cierre", columns)

    def test_eventos_has_checklist_fields(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(eventos_deslizamiento)").fetchall()}
        self.assertIn("checklist_no_desmorona", columns)
        self.assertIn("checklist_no_se_pega", columns)
        self.assertIn("checklist_acabado_aceptable", columns)
        self.assertIn("checklist_sin_arrastre", columns)

    def test_scada_tables_exist(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        self.assertIn("alarmas_operativas", tables)
        self.assertIn("decisiones_operador", tables)
        self.assertIn("liberaciones_campo", tables)
        self.assertIn("turnos_operacion", tables)
        self.assertIn("proyectos", tables)
        self.assertIn("fotografias_evidencia", tables)
        self.assertIn("lecturas_desplome", tables)
        self.assertIn("ajustes_modelo", tables)

    def test_reading_minute_can_be_calculated_from_colado_base_time(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(
            conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T08:00",
            },
        )
        insert_reading(
            conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-23T08:15",
                "temperatura_concreto_c": 30,
                "origen": "manual",
            },
        )
        minute = conn.execute("SELECT minuto_transcurrido FROM lecturas").fetchone()[0]
        self.assertEqual(minute, 15)

    def test_reading_minute_prefers_first_truck_zone_departure(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(
            conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "fecha_hora_inicio": "2026-07-23T05:00",
            },
        )
        register_truck_zone(
            conn,
            {
                "colado_id": colado_id,
                "numero_olla": 1,
                "hora_salida_planta": "2026-07-23T06:00",
                "temperatura_llegada_c": 30,
            },
        )
        insert_reading(
            conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-23T06:30",
                "temperatura_concreto_c": 31,
                "origen": "manual",
            },
        )

        minute = conn.execute("SELECT minuto_transcurrido FROM lecturas").fetchone()[0]
        self.assertEqual(minute, 30)

    def test_slide_event_requires_checklist(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(conn, {"silo_id": "S1", "mezcla_id": 1})
        with self.assertRaises(ValueError):
            insert_slide_event(
                conn,
                {
                    "colado_id": colado_id,
                    "minuto_transcurrido": 90,
                    "decision_tomada": "DESLIZAR",
                    "resultado_fisico": "correcto",
                },
            )

    def test_colado_can_be_updated(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(conn, {"silo_id": "S1", "mezcla_id": 1})

        updated = update_colado(
            conn,
            colado_id,
            {
                "silo_id": "S2",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T09:30",
                "fecha_cierre": "2026-07-23T18:00",
                "operador": "Operador 2",
                "estado": "CERRADO",
                "observaciones": "Ajuste de prueba",
            },
        )

        self.assertEqual(updated["silo_id"], "S2")
        self.assertEqual(updated["hora_colocacion_en_molde"], "2026-07-23T09:30")
        self.assertEqual(updated["estado"], "CERRADO")
        self.assertEqual(updated["fecha_cierre"], "2026-07-23T18:00")
        self.assertEqual(updated["observaciones"], "Ajuste de prueba")

    def test_colado_requires_closing_date_when_closed(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(
            conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "fecha_hora_inicio": "2026-07-23T09:30",
            },
        )

        with self.assertRaisesRegex(ValueError, "fecha de cierre"):
            update_colado(
                conn,
                colado_id,
                {
                    "silo_id": "S1",
                    "mezcla_id": 1,
                    "estado": "CERRADO",
                },
            )

    def test_colado_update_preserves_omitted_legacy_operational_times(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(
            conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_salida_planta": "2026-07-23T06:00",
                "hora_llegada_obra": "2026-07-23T06:45",
                "hora_inicio_descarga": "2026-07-23T07:00",
                "hora_colocacion_en_molde": "2026-07-23T07:10",
                "hora_fin_descarga": "2026-07-23T07:45",
            },
        )

        updated = update_colado(
            conn,
            colado_id,
            {
                "silo_id": "S2",
                "mezcla_id": 1,
                "operador": "Operador 2",
                "estado": "ACTIVO",
            },
        )

        self.assertEqual(updated["hora_salida_planta"], "2026-07-23T06:00")
        self.assertEqual(updated["hora_llegada_obra"], "2026-07-23T06:45")
        self.assertEqual(updated["hora_inicio_descarga"], "2026-07-23T07:00")
        self.assertEqual(updated["hora_colocacion_en_molde"], "2026-07-23T07:10")
        self.assertEqual(updated["hora_fin_descarga"], "2026-07-23T07:45")

    def test_delete_colado_removes_related_readings(self) -> None:
        conn = self.memory_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(conn, {"silo_id": "S1", "mezcla_id": 1})
        insert_reading(
            conn,
            {
                "colado_id": colado_id,
                "minuto_transcurrido": 5,
                "temperatura_concreto_c": 30,
                "origen": "manual",
            },
        )

        delete_colado(conn, colado_id)

        self.assertIsNone(get_colado(conn, colado_id))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM lecturas").fetchone()[0], 0)

    def test_operator_decision_is_saved_with_checklist(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(conn, {"silo_id": "S1", "mezcla_id": 1})

        decision_id = insert_operator_decision(
            conn,
            {
                "colado_id": colado_id,
                "recomendacion_sistema": "CONTINUAR",
                "decision_operador": "AVANZAR",
                "operador": "Op 1",
                "checklist": {"inspeccion_fisica": True},
            },
        )

        rows = list_operator_decisions(conn, colado_id)
        self.assertEqual(rows[0]["id"], decision_id)
        self.assertEqual(rows[0]["decision_operador"], "AVANZAR")
        self.assertTrue(rows[0]["checklist"]["inspeccion_fisica"])

    def test_advance_recipe_calculates_target_speed(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(conn, {"silo_id": "S1", "mezcla_id": 1})

        recipe_id = upsert_advance_recipe(
            conn,
            {
                "colado_id": colado_id,
                "avance_objetivo_cm": 3,
                "intervalo_objetivo_min": 6,
                "tolerancia_velocidad_min_cm_h": 25,
                "tolerancia_velocidad_max_cm_h": 35,
            },
        )
        recipe = get_active_advance_recipe(conn, colado_id)

        self.assertEqual(recipe["id"], recipe_id)
        self.assertEqual(recipe["velocidad_objetivo_cm_h"], 30)

    def test_advance_recipe_preserves_manual_values(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(conn, {"silo_id": "S1", "mezcla_id": 1})

        upsert_advance_recipe(
            conn,
            {
                "colado_id": colado_id,
                "avance_objetivo_cm": 5,
                "intervalo_objetivo_min": 5,
                "tolerancia_velocidad_min_cm_h": 10,
                "tolerancia_velocidad_max_cm_h": 90,
                "motivo": "Intento de ajuste manual",
            },
        )
        recipe = get_active_advance_recipe(conn, colado_id)

        self.assertEqual(recipe["avance_objetivo_cm"], 5)
        self.assertEqual(recipe["intervalo_objetivo_min"], 5)
        self.assertEqual(recipe["velocidad_objetivo_cm_h"], 60)
        self.assertEqual(recipe["tolerancia_velocidad_min_cm_h"], 10)
        self.assertEqual(recipe["tolerancia_velocidad_max_cm_h"], 90)

    def test_mold_advance_speed_uses_interval_when_provided(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(
            conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-23T06:00"},
        )

        insert_mold_advance(
            conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-23T10:00",
                "avance_cm": 4,
                "intervalo_minutos": 8,
            },
        )
        row = conn.execute("SELECT velocidad_real_cm_h, intervalo_minutos FROM avances_molde").fetchone()
        self.assertEqual(row["velocidad_real_cm_h"], 30)
        self.assertEqual(row["intervalo_minutos"], 8)

    def test_project_evidence_plumb_and_adjustment_are_saved(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        project_id = upsert_project(conn, {"nombre": "P1", "cliente": "Cliente", "ubicacion": "Seybaplaya"})
        colado_id = create_colado(conn, {"silo_id": "S1", "mezcla_id": 1, "proyecto_id": project_id, "es_demo": True})

        insert_shift_detail(conn, {"colado_id": colado_id, "turno": "1ro", "inicio_turno": "2026-07-23T07:00"})
        insert_photo_evidence(conn, {"colado_id": colado_id, "descripcion": "Frente norte"})
        insert_plumb_reading(
            conn,
            {"colado_id": colado_id, "punto": "Columna 1", "direccion": "N", "lectura_mm": 30, "tolerancia_mm": 25},
        )
        insert_model_adjustment(
            conn,
            {"colado_id": colado_id, "mezcla_id": 1, "umbral_deslizar": 0.92, "justificacion": "Prueba de campo"},
        )

        self.assertEqual(get_active_project(conn)["nombre"], "P1")
        self.assertEqual(get_colado(conn, colado_id)["es_demo"], 1)
        self.assertEqual(len(list_shift_details(conn, colado_id)), 1)
        self.assertEqual(len(list_photo_evidence(conn, colado_id)), 1)
        self.assertEqual(list_plumb_readings(conn, colado_id)[0]["estado"], "FUERA_TOLERANCIA")
        self.assertEqual(len(list_model_adjustments(conn, colado_id)), 1)

    def test_sensor_health_marks_stale_sensor(self) -> None:
        conn = self.memory_conn()
        init_db(conn)
        conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        colado_id = create_colado(conn, {"silo_id": "S1", "mezcla_id": 1})
        insert_reading(
            conn,
            {
                "colado_id": colado_id,
                "sensor_id": 7,
                "fecha_hora": "2026-07-23T08:00",
                "minuto_transcurrido": 0,
                "temperatura_concreto_c": 30,
                "origen": "sensor",
            },
        )

        health = get_sensor_health(conn, colado_id, now_iso="2026-07-23T08:12")

        self.assertEqual(health[0]["estado_salud"], "VENCIDO")


if __name__ == "__main__":
    unittest.main()
