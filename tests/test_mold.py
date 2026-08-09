from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta

from slipform.db import (
    create_colado,
    generate_zones,
    get_descargas,
    get_zones,
    initialize_colado_start_offset,
    init_db,
    insert_field_release,
    insert_mold_advance,
    insert_zone_reading,
    register_truck_zone,
    upsert_advance_recipe,
)
from slipform.repositories.catalog_repo import insert_curve
from slipform.mold import _with_suggested_recipe, calculate_mold_state


class MoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.conn.execute("INSERT INTO mezclas(nombre) VALUES ('M1')")
        self.colado_id = create_colado(
            self.conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-23T06:00",
            },
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_generate_four_30cm_zones_hourly(self) -> None:
        ids = generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "intervalo_minutos": 60,
                "temperatura_inicial_c": 32,
            },
        )
        rows = self.conn.execute(
            "SELECT zona_numero, elevacion_inferior_cm, elevacion_superior_cm, hora_salida_planta, hora_referencia_madurez FROM zonas_colado ORDER BY zona_numero"
        ).fetchall()
        descargas = get_descargas(self.conn, self.colado_id)
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(descargas), 4)
        self.assertEqual(descargas[0]["numero_olla"], "1")
        self.assertEqual(descargas[0]["volumen_m3"], 5.0)
        self.assertEqual(descargas[0]["hora_salida_planta"], "2026-07-23T06:00")
        self.assertEqual(descargas[1]["hora_salida_planta"], "2026-07-23T07:00")
        self.assertEqual(rows[0]["hora_salida_planta"], "2026-07-23T06:00")
        self.assertEqual(rows[0]["hora_referencia_madurez"], "2026-07-23T06:00")
        self.assertEqual(rows[1]["hora_referencia_madurez"], "2026-07-23T07:00")
        self.assertEqual(rows[3]["elevacion_superior_cm"], 120)

    def test_zone_age_uses_truck_plant_departure_per_layer(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T10:00",
                "intervalo_minutos": 60,
                "temperatura_inicial_c": 30,
            },
        )

        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T14:00")
        by_zone = {zone["zona_numero"]: zone for zone in state["zonas_activas"]}

        self.assertEqual(by_zone[1]["numero_olla"], "1")
        self.assertEqual(by_zone[1]["hora_salida_planta"], "2026-07-23T10:00")
        self.assertEqual(by_zone[1]["edad_real_h"], 4.0)
        self.assertEqual(by_zone[2]["hora_salida_planta"], "2026-07-23T11:00")
        self.assertEqual(by_zone[2]["edad_real_h"], 3.0)
        self.assertEqual(by_zone[3]["edad_real_h"], 2.0)
        self.assertEqual(by_zone[4]["edad_real_h"], 1.0)

    def test_register_truck_creates_matching_30cm_zone(self) -> None:
        result = register_truck_zone(
            self.conn,
            {
                "colado_id": self.colado_id,
                "numero_olla": 1,
                "hora_salida_planta": "2026-07-23T06:00",
                "hora_llegada_obra": "2026-07-23T06:45",
                "hora_inicio_descarga": "2026-07-23T06:50",
                "volumen_m3": 5,
                "temperatura_llegada_c": 31,
            },
        )

        zones = get_zones(self.conn, self.colado_id)
        descargas = get_descargas(self.conn, self.colado_id)

        self.assertTrue(result["zona_creada"])
        self.assertEqual(len(zones), 1)
        self.assertEqual(len(descargas), 1)
        self.assertEqual(zones[0]["zona_numero"], 1)
        self.assertEqual(zones[0]["elevacion_inferior_cm"], 0)
        self.assertEqual(zones[0]["elevacion_superior_cm"], 30)
        self.assertEqual(zones[0]["hora_referencia_madurez"], "2026-07-23T06:00")
        self.assertEqual(zones[0]["numero_olla"], "1")

    def test_register_truck_requires_temperature_when_no_reference_curve(self) -> None:
        with self.assertRaisesRegex(ValueError, "temperatura"):
            register_truck_zone(
                self.conn,
                {
                    "colado_id": self.colado_id,
                    "numero_olla": 1,
                    "hora_salida_planta": "2026-07-23T06:00",
                    "volumen_m3": 5,
                },
            )

    def test_mold_incomplete_blocks_until_four_trucks_are_registered(self) -> None:
        for number in range(1, 4):
            register_truck_zone(
                self.conn,
                {
                    "colado_id": self.colado_id,
                    "numero_olla": number,
                    "hora_salida_planta": f"2026-07-23T0{5 + number}:00",
                    "volumen_m3": 5,
                    "temperatura_llegada_c": 32,
                },
            )

        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T10:30")

        self.assertEqual(state["estado_operativo"], "MOLDE_INCOMPLETO")
        self.assertFalse(state["siguiente_avance_5min"]["permitido"])
        self.assertEqual(len(state["zonas_pendientes_molde"]), 1)
        self.assertEqual(state["zonas_pendientes_molde"][0]["zona_numero"], 4)

        register_truck_zone(
            self.conn,
            {
                "colado_id": self.colado_id,
                "numero_olla": 4,
                "hora_salida_planta": "2026-07-23T09:00",
                "volumen_m3": 5,
                "temperatura_llegada_c": 32,
            },
        )
        complete = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T10:30")

        self.assertNotEqual(complete["estado_operativo"], "MOLDE_INCOMPLETO")
        self.assertEqual(complete["zonas_confirmadas_iniciales"], 4)
        self.assertEqual(complete["zonas_pendientes_molde"], [])

    def test_start_offset_creates_inherited_zone_and_uses_physical_base_offset(self) -> None:
        result = initialize_colado_start_offset(
            self.conn,
            {
                "colado_id": self.colado_id,
                "primera_zona_nueva": 2,
                "hora_inicio_operativo": "2026-07-23T08:00",
                "motivo": "Zona 1 viene de colado anterior",
                "operador": "Operador",
                "supervisor": "Supervisor",
            },
        )

        self.assertEqual(result["siguiente_olla_sugerida"], 2)
        self.assertEqual(len(result["zonas_heredadas"]), 1)

        initial_state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T08:00")
        initial_by_zone = {zone["zona_numero"]: zone for zone in initial_state["zonas_activas"]}
        self.assertEqual(initial_state["estado_operativo"], "MOLDE_INCOMPLETO")
        self.assertEqual(initial_state["ventana_molde"]["base_cm"], 0)
        self.assertEqual(initial_state["ventana_molde"]["corona_cm"], 120)
        self.assertEqual(initial_state["progreso_operativo"]["avance_total_cm"], 30)
        self.assertEqual(initial_state["progreso_operativo"]["zona_liberacion_numero"], 2)
        self.assertEqual(initial_state["zonas_requeridas_molde"], [1, 2, 3, 4])
        self.assertEqual(initial_state["zona_en_liberacion"]["zona_numero"], 2)
        self.assertTrue(initial_state["zona_en_liberacion"]["pendiente_olla"])
        self.assertEqual(initial_by_zone[1]["estado_zona"], "EXISTENTE_PREVIO")

        for number, hour in [(2, "09:00"), (3, "10:00"), (4, "11:00")]:
            register_truck_zone(
                self.conn,
                {
                    "colado_id": self.colado_id,
                    "numero_olla": number,
                    "hora_salida_planta": f"2026-07-23T{hour}",
                    "volumen_m3": 5,
                    "temperatura_llegada_c": 32,
                },
            )

        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T12:00")
        by_zone = {zone["zona_numero"]: zone for zone in state["zonas_activas"]}

        self.assertNotEqual(state["estado_operativo"], "MOLDE_INCOMPLETO")
        self.assertEqual(state["zona_en_liberacion"]["zona_numero"], 2)
        self.assertEqual(state["zonas_confirmadas_iniciales"], 4)
        self.assertTrue(by_zone[1]["es_zona_heredada"])
        self.assertIsNone(by_zone[1]["hora_salida_planta"])
        self.assertEqual(by_zone[1]["avance_madurez_calculada"], 0)
        self.assertEqual(by_zone[1]["avance_madurez"], 0.9)
        self.assertEqual(by_zone[1]["estado_zona"], "EXISTENTE_PREVIO")
        self.assertEqual(by_zone[2]["hora_salida_planta"], "2026-07-23T09:00")
        self.assertEqual(by_zone[2]["edad_real_h"], 3.0)

        insert_mold_advance(
            self.conn,
            {
                "colado_id": self.colado_id,
                "fecha_hora": "2026-07-23T12:06",
                "avance_cm": 3.0,
            },
        )
        advanced = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T12:06")
        self.assertEqual(advanced["avance_acumulado_cm"], 3)
        self.assertEqual(advanced["progreso_operativo"]["avance_total_cm"], 33)
        self.assertEqual(advanced["progreso_operativo"]["tramo_inicio_cm"], 30)
        self.assertEqual(advanced["progreso_operativo"]["tramo_fin_cm"], 60)
        self.assertEqual(advanced["progreso_operativo"]["zona_liberacion_numero"], 2)

        base_dt = datetime.fromisoformat("2026-07-23T12:12")
        for index in range(10):
            insert_mold_advance(
                self.conn,
                {
                    "colado_id": self.colado_id,
                    "fecha_hora": (base_dt + timedelta(minutes=index * 6)).isoformat(timespec="minutes"),
                    "avance_cm": 3.0,
                },
            )
        boundary = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T13:12")
        self.assertEqual(boundary["avance_acumulado_cm"], 33)
        self.assertEqual(boundary["progreso_operativo"]["avance_total_cm"], 63)
        self.assertEqual(boundary["progreso_operativo"]["zona_liberacion_numero"], 3)
        self.assertEqual(boundary["zona_en_liberacion"]["zona_numero"], 3)

    def test_zone_generator_after_start_offset_creates_only_missing_initial_zones(self) -> None:
        initialize_colado_start_offset(
            self.conn,
            {
                "colado_id": self.colado_id,
                "primera_zona_nueva": 2,
                "hora_inicio_operativo": "2026-07-23T08:00",
                "motivo": "Zona 1 viene de colado anterior",
                "operador": "Operador",
                "supervisor": "Supervisor",
            },
        )

        ids = generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T09:00",
                "zona_inicial": 2,
                "zonas": 3,
                "intervalo_minutos": 60,
                "temperatura_inicial_c": 32,
                "volumen_por_olla_m3": 5,
            },
        )
        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T12:00")
        zones = get_zones(self.conn, self.colado_id)

        self.assertEqual(len(ids), 3)
        self.assertEqual([zone["zona_numero"] for zone in zones], [1, 2, 3, 4])
        self.assertNotEqual(state["estado_operativo"], "MOLDE_INCOMPLETO")
        self.assertEqual(state["zonas_confirmadas_iniciales"], 4)
        self.assertEqual(state["zonas_pendientes_molde"], [])

    def test_start_offset_at_zone_7_uses_only_window_previous_zones(self) -> None:
        result = initialize_colado_start_offset(
            self.conn,
            {
                "colado_id": self.colado_id,
                "primera_zona_nueva": 7,
                "hora_inicio_operativo": "2026-07-23T08:00",
                "motivo": "Arranque desde tramo existente",
                "operador": "Operador",
                "supervisor": "Supervisor",
            },
        )

        self.assertEqual(result["base_inicial_cm"], 90)
        self.assertEqual(result["corona_inicial_cm"], 210)
        self.assertEqual(result["zonas_previas_numeros"], [4, 5, 6])
        self.assertEqual(result["siguiente_olla_sugerida"], 7)

        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T08:00")
        self.assertEqual(state["ventana_molde"]["base_cm"], 90)
        self.assertEqual(state["ventana_molde"]["corona_cm"], 210)
        self.assertEqual(state["zonas_requeridas_molde"], [4, 5, 6, 7])
        self.assertEqual([zone["zona_numero"] for zone in state["zonas_activas"]], [4, 5, 6])
        self.assertEqual([zone["zona_numero"] for zone in state["zonas_pendientes_molde"]], [7])
        self.assertEqual(state["estado_operativo"], "MOLDE_INCOMPLETO")

        register_truck_zone(
            self.conn,
            {
                "colado_id": self.colado_id,
                "numero_olla": 7,
                "hora_salida_planta": "2026-07-23T08:05",
                "volumen_m3": 5,
                "temperatura_llegada_c": 31,
            },
        )
        complete = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T08:10")
        self.assertNotEqual(complete["estado_operativo"], "MOLDE_INCOMPLETO")
        self.assertEqual(complete["zonas_confirmadas_iniciales"], 4)

    def test_advance_2_5cm_every_5min_accumulates_30cm_per_hour(self) -> None:
        for index in range(12):
            insert_mold_advance(
                self.conn,
                {
                    "colado_id": self.colado_id,
                    "fecha_hora": f"2026-07-23T10:{index * 5:02d}",
                    "avance_cm": 2.5,
                },
            )
        value = self.conn.execute("SELECT MAX(avance_acumulado_cm) FROM avances_molde").fetchone()[0]
        self.assertEqual(value, 30)

    def test_mold_blocks_immature_zone(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 23,
            },
        )
        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T06:30")
        self.assertEqual(state["estado_operativo"], "NO_LIBERAR")
        self.assertEqual(state["hora_evaluacion"], "2026-07-23T06:30")
        self.assertEqual(state["prediccion_deslizamiento"]["accion_recomendada"], "pausar")
        self.assertEqual(state["prediccion_deslizamiento"]["velocidad_recomendada_cm_h"], 0.0)

    def test_field_release_uses_operational_maturity_without_changing_calculated_maturity(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 23,
            },
        )
        before = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T06:30")
        zone = before["zona_en_liberacion"]
        self.assertEqual(before["estado_operativo"], "NO_LIBERAR")
        self.assertLess(zone["avance_madurez_calculada"], 0.9)

        insert_field_release(
            self.conn,
            {
                "colado_id": self.colado_id,
                "zona_colado_id": zone["id"],
                "fecha_hora": "2026-07-23T06:30",
                "madurez_calculada_pct": zone["avance_madurez_calculada"] * 100,
                "madurez_operativa_pct": 90,
                "temperatura_concreto_c": 29,
                "condicion_observada": "correcto",
                "motivo": "Inspeccion fisica valida para iniciar.",
                "supervisor": "Supervisor 1",
                "checklist": {
                    "no_desmorona": True,
                    "no_se_pega": True,
                    "acabado_aceptable": True,
                    "sin_arrastre": True,
                },
            },
        )

        after = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T06:30")
        updated_zone = after["zona_en_liberacion"]
        self.assertEqual(after["estado_operativo"], "CONTINUAR")
        self.assertLess(updated_zone["avance_madurez_calculada"], 0.9)
        self.assertEqual(updated_zone["avance_madurez"], 0.9)
        self.assertEqual(updated_zone["madurez_fuente"], "criterio_campo")
        self.assertTrue(updated_zone["madurez_override_activa"])

    def test_field_release_allows_start_even_if_fill_time_was_captured_future(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 23,
            },
        )
        before = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T06:30")
        zone = before["zona_en_liberacion"]
        self.conn.execute(
            "UPDATE zonas_colado SET hora_inicio_llenado = ? WHERE id = ?",
            ("2026-07-23T20:00", zone["id"]),
        )
        insert_field_release(
            self.conn,
            {
                "colado_id": self.colado_id,
                "zona_colado_id": zone["id"],
                "fecha_hora": "2026-07-23T06:30",
                "madurez_calculada_pct": zone["avance_madurez_calculada"] * 100,
                "madurez_operativa_pct": 90,
                "temperatura_concreto_c": 29,
                "condicion_observada": "correcto",
                "motivo": "Inspeccion fisica valida para iniciar.",
                "supervisor": "Supervisor 1",
                "checklist": {
                    "no_desmorona": True,
                    "no_se_pega": True,
                    "acabado_aceptable": True,
                    "sin_arrastre": True,
                },
            },
        )

        after = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T06:30")

        self.assertEqual(after["estado_operativo"], "CONTINUAR")
        self.assertEqual(after["zona_en_liberacion"]["estado_zona"], "LIBERABLE")
        self.assertEqual(after["zona_en_liberacion"]["madurez_fuente"], "criterio_campo")

    def test_mold_continues_mature_zone(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 32,
            },
        )
        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T10:30")
        self.assertIn(state["estado_operativo"], {"CONTINUAR", "RIESGO_AGARROTAMIENTO"})
        prediction = state["prediccion_deslizamiento"]
        self.assertIn(prediction["accion_recomendada"], {"mantener", "acelerar", "acelerar_con_riesgo", "acelerar_con_supervision"})
        self.assertIsNotNone(prediction["velocidad_recomendada_cm_h"])
        self.assertIn("zona_control_nombre", prediction)

    def test_speed_prediction_recommends_recipe_in_safe_maturity_window(self) -> None:
        curve_id = insert_curve(
            self.conn,
            1,
            "test",
            "ventana_segura",
            [
                {"minuto": 0, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 0},
                {"minuto": 60, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 7.5},
                {"minuto": 180, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 8.0},
                {"minuto": 300, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 8.5},
            ],
        )
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "curva_id": curve_id,
            },
        )

        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T07:15")

        self.assertEqual(state["estado_operativo"], "CONTINUAR")
        self.assertEqual(state["prediccion_deslizamiento"]["accion_recomendada"], "mantener")
        self.assertEqual(state["prediccion_deslizamiento"]["velocidad_recomendada_cm_h"], 30.0)
        self.assertEqual(state["prediccion_deslizamiento"]["receta_sugerida"]["avance_objetivo_cm"], 3.0)
        self.assertEqual(state["prediccion_deslizamiento"]["receta_sugerida"]["intervalo_objetivo_min"], 6.0)

    def test_speed_prediction_translates_recommended_speed_to_recipe_suggestion(self) -> None:
        recipe = {
            "avance_objetivo_cm": 2.5,
            "intervalo_objetivo_min": 5,
            "velocidad_objetivo_cm_h": 30,
            "tolerancia_velocidad_min_cm_h": 25,
            "tolerancia_velocidad_max_cm_h": 35,
        }

        faster = _with_suggested_recipe(
            {
                "accion_recomendada": "acelerar",
                "velocidad_recomendada_cm_h": 35,
                "motivo_recomendacion": "Prueba",
            },
            recipe,
        )
        slower = _with_suggested_recipe(
            {
                "accion_recomendada": "reducir",
                "velocidad_recomendada_cm_h": 20,
                "motivo_recomendacion": "Prueba",
            },
            recipe,
        )
        paused = _with_suggested_recipe(
            {
                "accion_recomendada": "pausar",
                "velocidad_recomendada_cm_h": 0,
                "motivo_recomendacion": "Prueba",
            },
            recipe,
        )

        self.assertEqual(faster["receta_sugerida"]["avance_objetivo_cm"], 2.9)
        self.assertEqual(faster["receta_sugerida"]["intervalo_objetivo_min"], 5.0)
        self.assertEqual(faster["receta_sugerida"]["intervalo_alternativo_min"], 4.3)
        self.assertEqual(slower["receta_sugerida"]["avance_objetivo_cm"], 1.7)
        self.assertIsNone(paused["receta_sugerida"])

    def test_first_advance_creates_fifth_zone_above_mold(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 32,
            },
        )
        insert_mold_advance(
            self.conn,
            {
                "colado_id": self.colado_id,
                "fecha_hora": "2026-07-23T10:05",
                "avance_cm": 2.5,
            },
        )

        zones = get_zones(self.conn, self.colado_id)
        self.assertEqual(len(zones), 5)
        self.assertEqual(zones[-1]["zona_numero"], 5)
        self.assertEqual(zones[-1]["elevacion_inferior_cm"], 120)
        self.assertEqual(zones[-1]["elevacion_superior_cm"], 150)
        self.assertEqual(zones[-1]["origen_generacion"], "automatico_avance")
        self.assertEqual(zones[-1]["hora_inicio_llenado"], "2026-07-23T10:00")

    def test_utc_advance_creates_continuous_zone_in_local_time(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 32,
            },
        )
        insert_mold_advance(
            self.conn,
            {
                "colado_id": self.colado_id,
                "fecha_hora": "2026-07-23T15:05:00Z",
                "avance_cm": 2.5,
            },
        )

        zones = get_zones(self.conn, self.colado_id)

        self.assertEqual(zones[-1]["zona_numero"], 5)
        self.assertEqual(zones[-1]["hora_inicio_llenado"], "2026-07-23T10:00")

    def test_after_passing_30cm_advance_creates_sixth_zone(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 32,
            },
        )
        start = datetime.fromisoformat("2026-07-23T10:05")
        for index in range(13):
            insert_mold_advance(
                self.conn,
                {
                    "colado_id": self.colado_id,
                    "fecha_hora": (start + timedelta(minutes=index * 5)).isoformat(timespec="minutes"),
                    "avance_cm": 2.5,
                },
            )

        zones = get_zones(self.conn, self.colado_id)
        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T11:05")
        self.assertEqual(len(zones), 6)
        self.assertEqual(zones[-1]["zona_numero"], 6)
        self.assertEqual(zones[-1]["elevacion_inferior_cm"], 150)
        self.assertEqual(zones[-1]["elevacion_superior_cm"], 180)
        self.assertEqual(state["ventana_molde"]["base_cm"], 32.5)
        self.assertEqual(state["ventana_molde"]["corona_cm"], 152.5)

    def test_large_manual_advance_creates_all_missing_upper_zones(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 32,
            },
        )
        insert_mold_advance(
            self.conn,
            {
                "colado_id": self.colado_id,
                "fecha_hora": "2026-07-23T12:00",
                "avance_cm": 60,
            },
        )

        zones = get_zones(self.conn, self.colado_id)
        self.assertEqual(len(zones), 6)
        self.assertEqual(zones[-2]["hora_inicio_llenado"], "2026-07-23T10:00")
        self.assertEqual(zones[-1]["hora_inicio_llenado"], "2026-07-23T11:00")

    def test_mold_state_uses_active_advance_recipe(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 32,
            },
        )
        upsert_advance_recipe(
            self.conn,
            {
                "colado_id": self.colado_id,
                "avance_objetivo_cm": 3,
                "intervalo_objetivo_min": 6,
                "tolerancia_velocidad_min_cm_h": 25,
                "tolerancia_velocidad_max_cm_h": 35,
            },
        )

        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T10:30")

        self.assertEqual(state["siguiente_avance_5min"]["avance_cm"], 3)
        self.assertEqual(state["siguiente_avance_5min"]["intervalo_minutos"], 6)
        self.assertEqual(state["receta_avance"]["velocidad_objetivo_cm_h"], 30)

    def test_zone_maturity_continues_after_latest_zone_reading(self) -> None:
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "temperatura_inicial_c": 30,
            },
        )
        zone_4 = get_zones(self.conn, self.colado_id)[3]
        insert_zone_reading(
            self.conn,
            {
                "zona_colado_id": zone_4["id"],
                "fecha_hora": "2026-07-23T09:00",
                "temperatura_concreto_c": 30,
                "origen": "manual",
            },
        )

        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T11:00")
        zone_4_state = next(zone for zone in state["zonas_activas"] if zone["zona_numero"] == 4)

        self.assertEqual(zone_4_state["edad_real_h"], 2.0)
        self.assertGreater(zone_4_state["madurez_h_eq"], 0)
        self.assertEqual(zone_4_state["temperatura_actual_c"], 30)
        self.assertEqual(zone_4_state["fuente_temperatura"], "manual_mantenida")

    def test_reference_curve_maturity_interpolates_between_points(self) -> None:
        curve_id = insert_curve(
            self.conn,
            1,
            "test",
            "curve",
            [
                {"minuto": 0, "temperatura_concreto_c": 25, "madurez_arrhenius_h_eq": 0},
                {"minuto": 60, "temperatura_concreto_c": 25, "madurez_arrhenius_h_eq": 1},
            ],
        )
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "curva_id": curve_id,
            },
        )

        state = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T06:30")
        zone_1_state = next(zone for zone in state["zonas_activas"] if zone["zona_numero"] == 1)

        self.assertAlmostEqual(zone_1_state["madurez_h_eq"], 0.5, places=3)
        self.assertGreater(zone_1_state["avance_madurez"], 0)

    def test_reference_curve_maturity_extends_after_last_point(self) -> None:
        curve_id = insert_curve(
            self.conn,
            1,
            "test",
            "short_curve",
            [
                {"minuto": 0, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 0},
                {"minuto": 60, "temperatura_concreto_c": 30, "madurez_arrhenius_h_eq": 1},
            ],
        )
        generate_zones(
            self.conn,
            {
                "colado_id": self.colado_id,
                "hora_zona_1": "2026-07-23T06:00",
                "curva_id": curve_id,
            },
        )

        state_60 = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T07:00")
        state_90 = calculate_mold_state(self.conn, self.colado_id, as_of_iso="2026-07-23T07:30")
        zone_60 = next(zone for zone in state_60["zonas_activas"] if zone["zona_numero"] == 1)
        zone_90 = next(zone for zone in state_90["zonas_activas"] if zone["zona_numero"] == 1)

        self.assertGreater(zone_90["madurez_h_eq"], zone_60["madurez_h_eq"])
        self.assertGreater(zone_90["avance_madurez"], zone_60["avance_madurez"])


if __name__ == "__main__":
    unittest.main()
