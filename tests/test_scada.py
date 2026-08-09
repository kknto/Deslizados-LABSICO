from __future__ import annotations

import sqlite3
import unittest

from slipform.db import (
    create_colado,
    generate_zones,
    get_advances,
    init_db,
    insert_curve,
    insert_reading,
    insert_zone_reading,
    simulate_operational_advances,
    upsert_advance_recipe,
)
from slipform.scada import confirm_scada_advance, get_scada_state, get_trends, release_zone_by_field_criteria


class ScadaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.conn.execute("INSERT INTO mezclas(id, nombre) VALUES (1, 'M1')")

    def tearDown(self) -> None:
        self.conn.close()

    def test_scada_generates_alarm_when_next_zone_is_immature(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 23,
            },
        )

        state = get_scada_state(self.conn, colado_id, as_of_iso="2026-07-23T06:30")

        self.assertEqual(state["estado_scada"], "NO AVANZAR")
        self.assertEqual(state["alarmas_activas"][0]["tipo"], "ZONA_MENOR_90")

    def test_field_release_marks_zone_ready_and_records_decision(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 23,
            },
        )

        result = release_zone_by_field_criteria(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-23T06:30",
                "temperatura_concreto_c": 29,
                "condicion_observada": "correcto",
                "motivo": "Se observa estable al descimbrar.",
                "operador": "Operador 1",
                "supervisor": "Supervisor 1",
                "checklist": {
                    "no_desmorona": True,
                    "no_se_pega": True,
                    "acabado_aceptable": True,
                    "sin_arrastre": True,
                },
            },
        )

        self.assertIsNotNone(result["liberacion_id"])
        self.assertEqual(result["scada"]["estado_molde"]["estado_operativo"], "CONTINUAR")
        zone = result["scada"]["estado_molde"]["zona_en_liberacion"]
        self.assertEqual(zone["avance_madurez"], 0.9)
        self.assertLess(zone["avance_madurez_calculada"], 0.9)
        decision = self.conn.execute(
            "SELECT decision_operador, conforme_recomendacion, requiere_supervisor FROM decisiones_operador WHERE id = ?",
            (result["decision_id"],),
        ).fetchone()
        self.assertEqual(decision["decision_operador"], "LIBERAR_POR_CRITERIO_CAMPO")
        self.assertEqual(decision["conforme_recomendacion"], 0)
        self.assertEqual(decision["requiere_supervisor"], 1)
        trends = get_trends(self.conn, colado_id, as_of_iso="2026-07-23T07:00")
        self.assertEqual(trends["zona_prediccion"]["confianza"], "criterio_campo")
        self.assertEqual(trends["zona_prediccion"]["hora_liberacion_campo"], "2026-07-23T06:30")
        self.assertEqual(trends["zona_prediccion"]["hora_estimada_deslizar"], "2026-07-23T06:30")
        self.assertEqual(trends["resumen_zonas"][0]["confianza"], "criterio_campo")
        self.assertEqual(trends["resumen_zonas"][0]["hora_liberacion_campo"], "2026-07-23T06:30")
        self.assertEqual(trends["resumen_zonas"][0]["madurez_fuente"], "criterio_campo")

    def test_field_release_projects_adjusted_prediction_to_later_zones(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T09:00",
            },
        )
        generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T09:00",
                "intervalo_minutos": 60,
                "temperatura_inicial_c": 20,
            },
        )

        result = release_zone_by_field_criteria(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-23T12:00",
                "temperatura_concreto_c": 28,
                "condicion_observada": "correcto",
                "motivo": "Zona estable por incremento de calor.",
                "operador": "Operador 1",
                "supervisor": "Supervisor 1",
                "checklist": {
                    "no_desmorona": True,
                    "no_se_pega": True,
                    "acabado_aceptable": True,
                    "sin_arrastre": True,
                },
            },
        )
        self.assertIsNotNone(result["ajuste_prediccion_id"])
        zone_2_id = self.conn.execute(
            "SELECT id FROM zonas_colado WHERE colado_id = ? AND zona_numero = 2",
            (colado_id,),
        ).fetchone()["id"]

        trends = get_trends(self.conn, colado_id, zona_id=zone_2_id, as_of_iso="2026-07-23T12:00")
        self.assertEqual(trends["prediccion_ajustada_campo"]["zona_base_numero"], 1)
        self.assertEqual(trends["zona_prediccion"]["hora_estimada_deslizar_ajustada"], "2026-07-23T13:00")
        self.assertEqual(trends["zona_prediccion"]["minutos_restantes_deslizar_ajustado"], 60.0)
        zone_3 = next(item for item in trends["resumen_zonas"] if item["zona_numero"] == 3)
        self.assertEqual(zone_3["hora_estimada_deslizar_ajustada"], "2026-07-23T14:00")

    def test_field_release_requires_supervisor_reason_temperature_and_checklist(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 23,
            },
        )
        payload = {
            "colado_id": colado_id,
            "fecha_hora": "2026-07-23T06:30",
            "temperatura_concreto_c": 29,
            "condicion_observada": "correcto",
            "motivo": "Se observa estable.",
            "supervisor": "Supervisor 1",
            "checklist": {
                "no_desmorona": True,
                "no_se_pega": True,
                "acabado_aceptable": True,
                "sin_arrastre": True,
            },
        }

        with self.assertRaises(ValueError):
            release_zone_by_field_criteria(self.conn, {**payload, "supervisor": ""})
        with self.assertRaises(ValueError):
            release_zone_by_field_criteria(self.conn, {**payload, "motivo": ""})
        with self.assertRaises(ValueError):
            release_zone_by_field_criteria(self.conn, {**payload, "temperatura_concreto_c": ""})
        with self.assertRaises(ValueError):
            release_zone_by_field_criteria(
                self.conn,
                {
                    **payload,
                    "checklist": {
                        "no_desmorona": True,
                        "no_se_pega": False,
                        "acabado_aceptable": True,
                        "sin_arrastre": True,
                    },
                },
            )

    def test_critical_advance_requires_supervisor(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 23,
            },
        )

        with self.assertRaises(ValueError):
            confirm_scada_advance(
                self.conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": "2026-07-23T06:30",
                    "decision_operador": "AVANZAR",
                },
            )

        with self.assertRaises(ValueError):
            confirm_scada_advance(
                self.conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": "2026-07-23T06:30",
                    "decision_operador": "AVANZAR",
                    "supervisor": "Supervisor 1",
                },
            )

        with self.assertRaises(ValueError):
            confirm_scada_advance(
                self.conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": "2026-07-23T06:30",
                    "decision_operador": "AVANZAR_BAJO_AUTORIZACION",
                    "autorizar_avance_inmaduro": True,
                    "supervisor": "Supervisor 1",
                    "observacion": "Prueba sin checklist",
                },
            )

        result = confirm_scada_advance(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-23T06:30",
                "decision_operador": "AVANZAR_BAJO_AUTORIZACION",
                "autorizar_avance_inmaduro": True,
                "supervisor": "Supervisor 1",
                "observacion": "Autorizacion de prueba por criterio de campo.",
                "checklist": {
                    "no_desmorona": True,
                    "no_se_pega": True,
                    "acabado_aceptable": True,
                    "sin_arrastre": True,
                },
            },
        )
        self.assertIsNotNone(result["decision_id"])
        self.assertIsNotNone(result["avance_molde_id"])
        row = self.conn.execute(
            "SELECT decision_operador, conforme_recomendacion, requiere_supervisor, supervisor, observacion "
            "FROM decisiones_operador WHERE id = ?",
            (result["decision_id"],),
        ).fetchone()
        self.assertEqual(row["decision_operador"], "AVANZAR_BAJO_AUTORIZACION")
        self.assertEqual(row["conforme_recomendacion"], 0)
        self.assertEqual(row["requiere_supervisor"], 1)
        self.assertEqual(row["supervisor"], "Supervisor 1")
        self.assertIn("AVANCE BAJO AUTORIZACION", row["observacion"])

    def test_early_authorized_advance_requires_supervisor_and_reason(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 23,
            },
        )
        payload = {
            "colado_id": colado_id,
            "fecha_hora": "2026-07-23T06:30",
            "decision_operador": "AVANZAR_BAJO_AUTORIZACION",
            "autorizar_avance_inmaduro": True,
            "checklist": {
                "no_desmorona": True,
                "no_se_pega": True,
                "acabado_aceptable": True,
                "sin_arrastre": True,
            },
        }

        with self.assertRaises(ValueError):
            confirm_scada_advance(self.conn, {**payload, "observacion": "Motivo sin supervisor"})
        with self.assertRaises(ValueError):
            confirm_scada_advance(self.conn, {**payload, "supervisor": "Supervisor 1"})

    def test_scada_advance_uses_recipe_interval_for_speed(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 32,
            },
        )
        upsert_advance_recipe(
            self.conn,
            {
                "colado_id": colado_id,
                "avance_objetivo_cm": 3,
                "intervalo_objetivo_min": 6,
                "tolerancia_velocidad_min_cm_h": 25,
                "tolerancia_velocidad_max_cm_h": 35,
            },
        )

        result = confirm_scada_advance(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-23T10:30",
                "decision_operador": "AVANZAR",
            },
        )
        advance = get_advances(self.conn, colado_id)[-1]
        self.assertIsNotNone(result["avance_molde_id"])
        self.assertEqual(advance["avance_cm"], 3)
        self.assertEqual(advance["intervalo_minutos"], 6)
        self.assertEqual(advance["velocidad_real_cm_h"], 30)

    def test_operational_simulator_uses_active_recipe(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 32,
            },
        )
        upsert_advance_recipe(
            self.conn,
            {
                "colado_id": colado_id,
                "avance_objetivo_cm": 4,
                "intervalo_objetivo_min": 8,
            },
        )

        count = simulate_operational_advances(self.conn, colado_id, "2026-07-23T10:00", steps=3)
        advances = get_advances(self.conn, colado_id)

        self.assertEqual(count, 3)
        self.assertEqual(advances[-1]["avance_acumulado_cm"], 12)
        self.assertEqual(advances[-1]["velocidad_real_cm_h"], 30)

    def test_trends_return_real_and_expected_temperature(self) -> None:
        curve_id = insert_curve(
            self.conn,
            1,
            "test.xlsx",
            "Curva M1",
            [
                {"minuto": 0, "temperatura_concreto_c": 25, "madurez_arrhenius_h_eq": 0},
                {"minuto": 30, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 0.8},
                {"minuto": 60, "temperatura_concreto_c": 35, "madurez_arrhenius_h_eq": 1.8},
            ],
        )
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "curva_id": curve_id,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        zone_id = generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 25,
            },
        )[0]
        insert_zone_reading(
            self.conn,
            {
                "zona_colado_id": zone_id,
                "fecha_hora": "2026-07-23T06:30",
                "temperatura_concreto_c": 31,
                "origen": "manual",
            },
        )

        trends = get_trends(self.conn, colado_id, zona_id=zone_id, rango="todo", as_of_iso="2026-07-23T07:00")

        self.assertEqual(trends["zona"]["id"], zone_id)
        self.assertEqual(trends["temperatura"]["real"][0]["temperatura_concreto_c"], 31)
        self.assertEqual(trends["temperatura"]["real_extendida"][-1]["minuto"], 60.0)
        self.assertEqual(trends["temperatura"]["real_extendida"][-1]["temperatura_concreto_c"], 31)
        self.assertEqual(trends["temperatura"]["actual"]["origen"], "manual_mantenida")
        self.assertAlmostEqual(trends["temperatura"]["diferencia_vs_esperada_c"], -4.0, places=2)
        self.assertGreaterEqual(len(trends["temperatura"]["esperada"]), 2)
        self.assertGreaterEqual(len(trends["madurez"]["esperada"]), 2)
        self.assertIn("zona_prediccion", trends)
        self.assertIn("prediccion_deslizamiento", trends)
        self.assertIn("resumen_zonas", trends)
        self.assertIsNotNone(trends["zona_prediccion"]["hora_estimada_deslizar"])
        self.assertIn("velocidad_recomendada_cm_h", trends["prediccion_deslizamiento"])
        self.assertIn("receta_sugerida", trends["prediccion_deslizamiento"])
        self.assertGreater(trends["zona_prediccion"]["minuto_umbral_deslizar"], 60)
        self.assertEqual(trends["zona_prediccion"]["confianza"], "mixta")
        self.assertEqual(trends["resumen_zonas"][0]["id"], zone_id)

    def test_trends_without_curve_extend_real_temperature_without_expected_line(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        zone_id = generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 28,
            },
        )[0]

        trends = get_trends(self.conn, colado_id, zona_id=zone_id, rango="todo", as_of_iso="2026-07-23T07:15")

        self.assertEqual(trends["temperatura"]["esperada"], [])
        self.assertEqual(trends["temperatura"]["actual"]["minuto"], 75.0)
        self.assertEqual(trends["temperatura"]["actual"]["temperatura_concreto_c"], 28)
        self.assertIsNone(trends["temperatura"]["diferencia_vs_esperada_c"])
        self.assertIsNotNone(trends["zona_prediccion"]["hora_estimada_deslizar"])
        self.assertEqual(trends["zona_prediccion"]["confianza"], "referencia")

    def test_imported_general_readings_keep_imported_minutes_for_zone_trend(self) -> None:
        colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )
        zone_id = generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 25,
            },
        )[0]
        for minute, temperature in [(0, 27.4), (30, 30.1), (60, 32.0)]:
            insert_reading(
                self.conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": "2026-07-23T09:00",
                    "minuto_transcurrido": minute,
                    "temperatura_concreto_c": temperature,
                    "origen": "importacion",
                },
            )

        trends = get_trends(self.conn, colado_id, zona_id=zone_id, rango="todo", as_of_iso="2026-07-23T07:00")

        self.assertEqual([point["minuto"] for point in trends["temperatura"]["real"]], [0.0, 30.0, 60.0])
        self.assertEqual(trends["temperatura"]["real"][-1]["temperatura_concreto_c"], 32.0)

    def test_trends_normalize_shifted_reference_curve_to_zone_start(self) -> None:
        curve_id = insert_curve(
            self.conn,
            1,
            "test.xlsx",
            "Curva desplazada",
            [
                {"minuto": 1200, "temperatura_concreto_c": 28, "madurez_arrhenius_h_eq": 10},
                {"minuto": 1230, "temperatura_concreto_c": 31, "madurez_arrhenius_h_eq": 11},
                {"minuto": 1260, "temperatura_concreto_c": 34, "madurez_arrhenius_h_eq": 12},
            ],
        )
        colado_id = create_colado(self.conn, {"silo_id": "S1", "mezcla_id": 1, "curva_id": curve_id})
        zone_id = generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T10:00",
                "temperatura_inicial_c": 28,
            },
        )[0]

        trends = get_trends(self.conn, colado_id, zona_id=zone_id, rango="todo", as_of_iso="2026-07-23T10:30")

        self.assertEqual(trends["temperatura"]["esperada"][0]["minuto"], 0.0)
        self.assertEqual(trends["temperatura"]["esperada"][1]["minuto"], 30.0)
        self.assertEqual(trends["madurez"]["esperada"][0]["madurez_arrhenius_h_eq"], 0.0)

    def test_trends_range_starts_at_zone_departure_not_reference_curve_end(self) -> None:
        curve_id = insert_curve(
            self.conn,
            1,
            "test.xlsx",
            "Curva larga",
            [
                {"minuto": 1200, "temperatura_concreto_c": 28, "madurez_arrhenius_h_eq": 10},
                {"minuto": 1230, "temperatura_concreto_c": 31, "madurez_arrhenius_h_eq": 11},
                {"minuto": 1260, "temperatura_concreto_c": 34, "madurez_arrhenius_h_eq": 18},
                {"minuto": 1500, "temperatura_concreto_c": 33, "madurez_arrhenius_h_eq": 30},
            ],
        )
        colado_id = create_colado(self.conn, {"silo_id": "S1", "mezcla_id": 1, "curva_id": curve_id})
        zone_id = generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T08:20",
                "temperatura_inicial_c": 28,
            },
        )[0]

        trends = get_trends(self.conn, colado_id, zona_id=zone_id, rango="4h", as_of_iso="2026-07-23T09:20")

        expected_minutes = [point["minuto"] for point in trends["temperatura"]["esperada"]]
        self.assertEqual(expected_minutes[0], 0.0)
        self.assertIn(30.0, expected_minutes)
        self.assertNotIn(300.0, expected_minutes)

    def test_trends_calculate_prediction_from_each_zone_departure(self) -> None:
        curve_id = insert_curve(
            self.conn,
            1,
            "test.xlsx",
            "Curva M1",
            [
                {"minuto": 0, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 0},
                {"minuto": 60, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 2},
                {"minuto": 120, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 8},
            ],
        )
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "curva_id": curve_id},
        )
        zone_ids = generate_zones(
            self.conn,
            {
                "colado_id": colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "intervalo_minutos": 60,
                "temperatura_inicial_c": 30,
            },
        )

        zone_1 = get_trends(self.conn, colado_id, zona_id=zone_ids[0], rango="todo", as_of_iso="2026-07-23T08:00")
        zone_2 = get_trends(self.conn, colado_id, zona_id=zone_ids[1], rango="todo", as_of_iso="2026-07-23T08:00")

        self.assertEqual(zone_1["zona_prediccion"]["hora_estimada_deslizar"], "2026-07-23T07:51")
        self.assertEqual(zone_2["zona_prediccion"]["hora_estimada_deslizar"], "2026-07-23T08:51")
        self.assertNotEqual(
            zone_1["zona_prediccion"]["minutos_restantes_deslizar"],
            zone_2["zona_prediccion"]["minutos_restantes_deslizar"],
        )


if __name__ == "__main__":
    unittest.main()
