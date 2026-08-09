from __future__ import annotations

import sqlite3
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from slipform.db import (
    generate_zones,
    get_active_advance_recipe,
    get_colado,
    get_readings,
    get_zone_readings,
    get_zones,
    init_db,
    list_audit,
)
from slipform.domain.data_quality import DataQualityWarningError
from slipform.mold import calculate_mold_state
from slipform.http.operation_handlers import handle_delete, handle_post, handle_put
from slipform.http.report_handlers import handle_report_get


def path_id(path: str, prefix: str) -> int:
    return int(path.removeprefix(prefix).strip("/"))


class OperationHandlersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "slipform.sqlite"
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

    def test_create_colado_and_reading(self) -> None:
        status, body = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        self.assertEqual(status, 201)
        colado_id = body["id"]

        status, body = handle_post(
            "/api/lecturas",
            self.db_path,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-24T09:05",
                "temperatura_concreto_c": 28.5,
            },
        )

        self.assertEqual(status, 201)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            readings = get_readings(conn, colado_id)
        finally:
            conn.close()
        self.assertEqual(readings[0]["origen"], "manual")

    def test_written_log_preview_and_commit_imports_loads_events_and_evidence(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-04T23:00"},
        )
        colado_id = created["id"]
        evidence_dir = Path(self.tmp.name) / "Bitacora_escrita" / "Ollas_deslizado"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "Ollas_deslizado_1.jpeg").write_bytes(b"fake-jpeg")
        ollas_csv = "\n".join(
            [
                "numero_olla,hora_salida_planta,hora_llegada_obra,hora_inicio_descarga,hora_fin_descarga,temperatura_llegada_c,revenimiento_cm,zona_numero,altura_capa_cm,hora_4h,hora_5h,hora_6h,fuente_imagen,observaciones",
                "101,23:50,00:05,00:10,00:20,31.5,20,5,30,03:50,04:50,05:50,Ollas_deslizado_1.jpeg,registro historico",
                "102,00:10,00:25,00:30,00:40,30.0,19,6,30,,,,Ollas_deslizado_1.jpeg,cruce medianoche",
            ]
        )
        eventos_csv = "\n".join(
            [
                "fecha_hora,hora_original,tipo_evento,descripcion_original,decision_tomada,resultado_fisico,supervisor,fuente_imagen,linea_fuente",
                ",00:30,OBSERVACION,Se ajusta ritmo por revision de campo,AJUSTE,controlado,Sup,Ollas_deslizado_1.jpeg,12",
            ]
        )
        payload = {
            "colado_id": colado_id,
            "fecha_base": "2026-08-04",
            "modo_existentes": "omitir",
            "ollas_csv": ollas_csv,
            "eventos_csv": eventos_csv,
            "operador": "Importador",
        }

        status, preview = handle_post("/api/bitacora-escrita/preview", self.db_path, dict(payload))
        self.assertEqual(status, 200)
        self.assertTrue(preview["puede_importar"])
        self.assertEqual(preview["ollas"]["filas"][1]["payload"]["hora_salida_planta"], "2026-08-05T00:10")
        self.assertEqual(preview["resumen"]["imagenes_evidencia"], 1)

        status, imported = handle_post("/api/bitacora-escrita/importar", self.db_path, dict(payload))
        self.assertEqual(status, 201)
        self.assertTrue(Path(imported["backup"]["ruta"]).exists())

        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            zonas = [dict(row) for row in conn.execute("SELECT * FROM zonas_colado WHERE colado_id = ? ORDER BY zona_numero", (colado_id,))]
            descargas = [dict(row) for row in conn.execute("SELECT * FROM descargas_olla WHERE colado_id = ? ORDER BY id", (colado_id,))]
            eventos = [dict(row) for row in conn.execute("SELECT * FROM eventos_deslizamiento WHERE colado_id = ? ORDER BY fecha_hora, id", (colado_id,))]
            fotos = [dict(row) for row in conn.execute("SELECT * FROM fotografias_evidencia WHERE colado_id = ?", (colado_id,))]
        finally:
            conn.close()

        self.assertEqual([zona["zona_numero"] for zona in zonas], [5, 6])
        self.assertEqual(descargas[0]["numero_olla"], "101")
        self.assertEqual(zonas[0]["hora_referencia_madurez"], "2026-08-04T23:50")
        self.assertTrue(any(evento["decision_tomada"] == "PROGRAMA_CILINDRO" for evento in eventos))
        self.assertTrue(any(evento["decision_tomada"] == "AJUSTE" for evento in eventos))
        self.assertEqual(len(fotos), 1)

        status, headers, body = handle_report_get("/api/export/control-central.zip", f"colado_id={colado_id}", self.db_path)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(BytesIO(body)) as archive:
            names = archive.namelist()
        self.assertTrue(any(name.startswith("fotografias/") and name.endswith(".jpg") for name in names))

    def test_written_log_reimport_replaces_only_imported_events(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-04T19:00"},
        )
        colado_id = created["id"]
        header = "fecha_hora,hora_original,tipo_evento,descripcion_original,decision_tomada,resultado_fisico,supervisor,fuente_imagen,linea_fuente"
        first_csv = "\n".join(
            [
                header,
                ",19:35,OBSERVACION,Texto original,OBSERVACION,registro_escrito,Sup,hoja1.jpg,10",
            ]
        )
        corrected_csv = "\n".join(
            [
                header,
                ",19:35,OBSERVACION,Texto corregido,OBSERVACION,registro_escrito,Sup,hoja1.jpg,10",
            ]
        )
        first_payload = {
            "colado_id": colado_id,
            "fecha_base": "2026-08-04",
            "eventos_csv": first_csv,
            "operador": "Importador",
        }

        status, imported = handle_post("/api/bitacora-escrita/importar", self.db_path, dict(first_payload))
        self.assertEqual(status, 201)
        self.assertEqual(imported["resumen"]["eventos_importados"], 1)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                INSERT INTO eventos_deslizamiento(
                    colado_id, fecha_hora, minuto_transcurrido, decision_tomada, resultado_fisico, observacion
                )
                VALUES (?, '2026-08-04T20:00', 60, 'MANUAL', 'ok', 'Evento manual no importado')
                """,
                (colado_id,),
            )
            conn.execute(
                """
                INSERT INTO avances_molde(colado_id, fecha_hora, minuto_transcurrido, avance_cm, avance_acumulado_cm, origen)
                VALUES (?, '2026-08-04T20:05', 65, 3, 3, 'manual')
                """,
                (colado_id,),
            )
            conn.commit()
        finally:
            conn.close()

        blocked_payload = first_payload | {"eventos_csv": corrected_csv}
        status, preview = handle_post("/api/bitacora-escrita/preview", self.db_path, dict(blocked_payload))
        self.assertEqual(status, 200)
        self.assertFalse(preview["puede_importar"])
        self.assertEqual(preview["resumen"]["eventos_bloqueados"], 1)
        self.assertIn("Ya existen", preview["eventos"]["errores"][0])

        replace_payload = blocked_payload | {"modo_eventos_importados": "reemplazar_importados"}
        status, preview = handle_post("/api/bitacora-escrita/preview", self.db_path, dict(replace_payload))
        self.assertEqual(status, 200)
        self.assertTrue(preview["puede_importar"])
        self.assertEqual(preview["resumen"]["eventos_reemplazar"], 1)

        status, imported = handle_post("/api/bitacora-escrita/importar", self.db_path, dict(replace_payload))
        self.assertEqual(status, 201)
        self.assertEqual(imported["resumen"]["eventos_reemplazados"], 1)
        self.assertEqual(imported["resumen"]["eventos_importados"], 1)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            events = [
                dict(row)
                for row in conn.execute(
                    "SELECT decision_tomada, observacion FROM eventos_deslizamiento WHERE colado_id = ? ORDER BY id",
                    (colado_id,),
                )
            ]
            advances = [
                dict(row)
                for row in conn.execute("SELECT * FROM avances_molde WHERE colado_id = ?", (colado_id,))
            ]
        finally:
            conn.close()

        self.assertEqual(len(events), 2)
        self.assertTrue(any(event["observacion"] == "Evento manual no importado" for event in events))
        self.assertTrue(any("Texto corregido" in event["observacion"] for event in events))
        self.assertFalse(any("Texto original" in event["observacion"] for event in events))
        self.assertEqual(len(advances), 1)

    def test_written_log_imports_real_advances_with_previous_zone_offset(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-04T19:00"},
        )
        colado_id = created["id"]
        ollas_csv = "\n".join(
            [
                "numero_olla,hora_salida_planta,hora_llegada_obra,hora_inicio_descarga,hora_fin_descarga,temperatura_llegada_c,revenimiento_cm,zona_numero,altura_capa_cm,hora_4h,hora_5h,hora_6h,fuente_imagen,observaciones",
                "1,19:06,20:01,20:36,21:13,17,24,2,30,,,,Ollas_1.jpeg,primera zona fresca real",
            ]
        )
        eventos_csv = "\n".join(
            [
                "fecha_hora,hora_original,tipo_evento,descripcion_original,decision_tomada,resultado_fisico,supervisor,fuente_imagen,linea_fuente",
                ",02:30,Deslizado,Se inicia con el deslizado de la capa #1 que se encuentra con concreto viejo,DESLIZADO,registro,Sup,Bitacora_1.jpeg,13",
                ",02:44,Deslizado,3 Velocidad de 3 cada 14 min,DESLIZADO,registro,Sup,Bitacora_1.jpeg,14",
                ",02:58,Deslizado,6,DESLIZADO,registro,Sup,Bitacora_1.jpeg,15",
            ]
        )
        payload = {
            "colado_id": colado_id,
            "fecha_base": "2026-08-04",
            "primera_zona_fresca": 2,
            "crear_avances_desde_eventos": True,
            "ollas_csv": ollas_csv,
            "eventos_csv": eventos_csv,
            "operador": "Importador",
            "supervisor": "Supervisor",
        }

        status, preview = handle_post("/api/bitacora-escrita/preview", self.db_path, dict(payload))
        self.assertEqual(status, 200)
        self.assertTrue(preview["puede_importar"])
        self.assertEqual(preview["resumen"]["zonas_previas"], 1)
        self.assertEqual(preview["resumen"]["avances_importar"], 2)
        self.assertEqual(preview["resumen"]["avance_total_visible_estimado"], 36.0)
        self.assertEqual(preview["avances_deslizamiento"]["filas"][0]["avance_acumulado_cm"], 3.0)

        status, imported = handle_post("/api/bitacora-escrita/importar", self.db_path, dict(payload))
        self.assertEqual(status, 201)
        self.assertEqual(imported["resumen"]["avances_importados"], 2)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            zones = [dict(row) for row in conn.execute("SELECT * FROM zonas_colado WHERE colado_id = ? ORDER BY zona_numero", (colado_id,))]
            loads = [dict(row) for row in conn.execute("SELECT * FROM descargas_olla WHERE colado_id = ? ORDER BY id", (colado_id,))]
            advances = [dict(row) for row in conn.execute("SELECT * FROM avances_molde WHERE colado_id = ? ORDER BY id", (colado_id,))]
            state = calculate_mold_state(conn, colado_id, as_of_iso="2026-08-05T03:00")
        finally:
            conn.close()

        self.assertEqual([zone["zona_numero"] for zone in zones], [1, 2])
        self.assertEqual(zones[0]["origen_generacion"], "existente_previo")
        self.assertIsNone(zones[0]["hora_salida_planta"])
        self.assertEqual(zones[1]["temperatura_inicial_c"], 17)
        self.assertEqual(loads[0]["revenimiento_cm"], 24)
        self.assertEqual([row["avance_acumulado_cm"] for row in advances], [3.0, 6.0])
        self.assertTrue(all(row["origen"] == "importacion_bitacora_deslizamiento" for row in advances))
        self.assertEqual(state["progreso_operativo"]["avance_previo_cm"], 30.0)
        self.assertEqual(state["progreso_operativo"]["avance_total_cm"], 36.0)

    def test_written_log_blocks_advance_import_when_advances_already_exist(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-04T09:00"},
        )
        colado_id = created["id"]
        handle_post(
            "/api/avances",
            self.db_path,
            {"colado_id": colado_id, "fecha_hora": "2026-08-04T09:10", "avance_cm": 3, "avance_acumulado_cm": 3},
        )
        eventos_csv = "\n".join(
            [
                "fecha_hora,hora_original,tipo_evento,descripcion_original,decision_tomada,resultado_fisico,supervisor,fuente_imagen,linea_fuente",
                ",09:20,Deslizado,6,DESLIZADO,registro,Sup,Bitacora_1.jpeg,2",
            ]
        )

        status, preview = handle_post(
            "/api/bitacora-escrita/preview",
            self.db_path,
            {
                "colado_id": colado_id,
                "fecha_base": "2026-08-04",
                "crear_avances_desde_eventos": True,
                "eventos_csv": eventos_csv,
            },
        )

        self.assertEqual(status, 200)
        self.assertFalse(preview["puede_importar"])
        self.assertIn("Ya existen avances", preview["avances_deslizamiento"]["errores"][0])

    def test_written_log_can_correct_duplicate_previous_zone_before_advance_import(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-04T19:00"},
        )
        colado_id = created["id"]
        handle_post(
            "/api/ollas/registrar-zona",
            self.db_path,
            {
                "colado_id": colado_id,
                "numero_olla": 1,
                "zona_numero": 1,
                "hora_salida_planta": "2026-08-04T19:06",
                "temperatura_llegada_c": 17,
            },
        )
        handle_post(
            "/api/ollas/registrar-zona",
            self.db_path,
            {
                "colado_id": colado_id,
                "numero_olla": 1,
                "zona_numero": 2,
                "hora_salida_planta": "2026-08-04T19:06",
                "temperatura_llegada_c": 17,
            },
        )
        eventos_csv = "\n".join(
            [
                "fecha_hora,hora_original,tipo_evento,descripcion_original,decision_tomada,resultado_fisico,supervisor,fuente_imagen,linea_fuente",
                ",02:44,Deslizado,3,DESLIZADO,registro,Sup,Bitacora_1.jpeg,14",
                ",02:58,Deslizado,6,DESLIZADO,registro,Sup,Bitacora_1.jpeg,15",
            ]
        )
        payload = {
            "colado_id": colado_id,
            "fecha_base": "2026-08-04",
            "primera_zona_fresca": 2,
            "crear_avances_desde_eventos": True,
            "eventos_csv": eventos_csv,
            "supervisor": "Supervisor",
        }

        status, preview = handle_post("/api/bitacora-escrita/preview", self.db_path, dict(payload))
        self.assertEqual(status, 200)
        self.assertTrue(preview["puede_importar"])
        self.assertEqual(preview["arranque_historico"]["zonas_previas"][0]["estado"], "corregir")

        status, imported = handle_post("/api/bitacora-escrita/importar", self.db_path, dict(payload))
        self.assertEqual(status, 201)
        self.assertEqual(imported["resumen"]["avances_importados"], 2)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            zones = [dict(row) for row in conn.execute("SELECT * FROM zonas_colado WHERE colado_id = ? ORDER BY zona_numero", (colado_id,))]
            state = calculate_mold_state(conn, colado_id, as_of_iso="2026-08-05T03:00")
        finally:
            conn.close()

        self.assertEqual(zones[0]["zona_numero"], 1)
        self.assertEqual(zones[0]["origen_generacion"], "existente_previo")
        self.assertIsNone(zones[0]["descarga_olla_id"])
        self.assertIsNone(zones[0]["hora_salida_planta"])
        self.assertEqual(zones[1]["zona_numero"], 2)
        self.assertEqual(state["progreso_operativo"]["avance_total_cm"], 36.0)

    def test_written_log_preview_blocks_invalid_required_time(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-04T09:00"},
        )
        ollas_csv = "\n".join(
            [
                "numero_olla,hora_salida_planta,hora_llegada_obra,hora_inicio_descarga,hora_fin_descarga,temperatura_llegada_c,revenimiento_cm,zona_numero,altura_capa_cm,hora_4h,hora_5h,hora_6h,fuente_imagen,observaciones",
                "1,ilegible,,,,30,18,1,30,,,,Bitacora_Hoja1.jpeg,hora sin validar",
            ]
        )

        status, preview = handle_post(
            "/api/bitacora-escrita/preview",
            self.db_path,
            {"colado_id": created["id"], "fecha_base": "2026-08-04", "ollas_csv": ollas_csv},
        )

        self.assertEqual(status, 200)
        self.assertFalse(preview["puede_importar"])
        self.assertIn("hora_salida_planta invalida", preview["ollas"]["filas"][0]["errores"][0])

    def test_written_log_ocr_preview_reports_engine_and_keeps_import_guard(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-04T09:00"},
        )
        folder = Path(self.tmp.name) / "Bitacora_escrita" / "Bitacora_eventos_deslizado"
        folder.mkdir(parents=True)
        (folder / "Bitacora_Hoja1.jpeg").write_bytes(b"fake-jpeg")

        status, result = handle_post(
            "/api/bitacora-escrita/ocr-preview",
            self.db_path,
            {"colado_id": created["id"], "fecha_base": "2026-08-04"},
        )

        self.assertEqual(status, 200)
        self.assertIn("tesseract", str(result["motor"]).lower())
        self.assertEqual(len(result["imagenes"]), 1)
        self.assertIn("numero_olla", result["csv"]["ollas"])
        self.assertIn("fecha_hora", result["csv"]["eventos"])
        if not result["motor_disponible"]:
            self.assertFalse(result["preview"]["puede_importar"])

    def test_zone_reading_requires_zone_from_active_colado(self) -> None:
        _, first = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        _, second = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S2", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            generate_zones(
                conn,
                {
                    "colado_id": first["id"],
                    "hora_zona_1": "2026-07-24T09:00",
                    "zonas": 1,
                    "temperatura_inicial_c": 30,
                },
            )
            zone_id = get_zones(conn, first["id"])[0]["id"]
        finally:
            conn.close()

        with self.assertRaisesRegex(ValueError, "colado activo"):
            handle_post(
                "/api/lecturas-zona",
                self.db_path,
                {
                    "colado_id": second["id"],
                    "zona_colado_id": zone_id,
                    "fecha_hora": "2026-07-24T09:30",
                    "temperatura_concreto_c": 31,
                },
            )

        status, body = handle_post(
            "/api/lecturas-zona",
            self.db_path,
            {
                "colado_id": first["id"],
                "zona_colado_id": zone_id,
                "fecha_hora": "2026-07-24T09:30",
                "temperatura_concreto_c": 31,
            },
        )
        self.assertEqual(status, 201)
        self.assertIn("id", body)

    def test_zone_temperature_reading_can_be_invalidated_with_audit(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-24T09:00",
                "operador": "Operador 1",
            },
        )
        colado_id = created["id"]
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            generate_zones(
                conn,
                {
                    "colado_id": colado_id,
                    "hora_zona_1": "2026-07-24T09:00",
                    "zonas": 1,
                    "temperatura_inicial_c": 30,
                },
            )
            zone_id = get_zones(conn, colado_id)[0]["id"]
        finally:
            conn.close()

        _, wrong = handle_post(
            "/api/lecturas-zona",
            self.db_path,
            {
                "colado_id": colado_id,
                "zona_colado_id": zone_id,
                "fecha_hora": "2026-07-24T09:30",
                "temperatura_concreto_c": 60,
            },
        )
        _, correct = handle_post(
            "/api/lecturas-zona",
            self.db_path,
            {
                "colado_id": colado_id,
                "zona_colado_id": zone_id,
                "fecha_hora": "2026-07-24T09:35",
                "temperatura_concreto_c": 31,
            },
        )

        status, body = handle_post(
            "/api/lecturas-zona/anular",
            self.db_path,
            {
                "colado_id": colado_id,
                "lectura_id": wrong["id"],
                "motivo": "Captura equivocada",
                "operador": "Operador 1",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["lectura"]["valido"], 0)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            active_readings = get_zone_readings(conn, zone_id)
            audit = list_audit(conn, limit=5)
        finally:
            conn.close()
        self.assertEqual([reading["id"] for reading in active_readings], [correct["id"]])
        self.assertEqual(active_readings[0]["temperatura_concreto_c"], 31)
        self.assertTrue(any(row["accion"] == "INVALIDATE_ZONE_READING" for row in audit))

    def test_advance_handler_returns_mold_state(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        colado_id = created["id"]
        status, body = handle_post(
            "/api/avances/registrar-5min",
            self.db_path,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-24T10:00",
                "avance_cm": 2.5,
                "intervalo_minutos": 5,
            },
        )
        self.assertEqual(status, 201)
        self.assertIn("estado_molde", body)

    def test_update_and_delete_colado(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        colado_id = created["id"]
        status, body = handle_put(
            f"/api/colados/{colado_id}",
            self.db_path,
            {
                "silo_id": "S2",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-24T09:00",
                "estado": "ACTIVO",
            },
            path_id,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["colado"]["silo_id"], "S2")

        status, body = handle_delete(f"/api/colados/{colado_id}", self.db_path, path_id)
        self.assertEqual(status, 200)
        self.assertTrue(Path(body["backup"]["ruta"]).exists())
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            self.assertIsNone(get_colado(conn, colado_id))
        finally:
            conn.close()

    def test_colado_close_date_is_required_editable_and_blocks_operations(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        colado_id = created["id"]

        with self.assertRaisesRegex(ValueError, "fecha de cierre"):
            handle_put(
                f"/api/colados/{colado_id}",
                self.db_path,
                {
                    "silo_id": "S1",
                    "mezcla_id": 1,
                    "hora_colocacion_en_molde": "2026-07-24T09:00",
                    "estado": "CERRADO",
                },
                path_id,
            )

        status, body = handle_put(
            f"/api/colados/{colado_id}",
            self.db_path,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-24T09:00",
                "estado": "CERRADO",
                "fecha_cierre": "2026-07-25T18:30",
            },
            path_id,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["colado"]["estado"], "CERRADO")
        self.assertEqual(body["colado"]["fecha_cierre"], "2026-07-25T18:30")

        with self.assertRaisesRegex(ValueError, "CERRADO"):
            handle_post(
                "/api/avances",
                self.db_path,
                {
                    "colado_id": colado_id,
                    "fecha_hora": "2026-07-25T19:00",
                    "avance_cm": 3,
                },
            )

        with self.assertRaisesRegex(ValueError, "CERRADO"):
            handle_post(
                "/api/ollas/registrar-zona",
                self.db_path,
                {
                    "colado_id": colado_id,
                    "numero_olla": 1,
                    "hora_salida_planta": "2026-07-25T19:00",
                    "temperatura_llegada_c": 30,
                },
            )

        status, body = handle_put(
            f"/api/colados/{colado_id}",
            self.db_path,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-24T09:00",
                "estado": "ACTIVO",
                "fecha_cierre": "",
            },
            path_id,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["colado"]["estado"], "ACTIVO")
        self.assertIsNone(body["colado"]["fecha_cierre"])

        status, body = handle_post(
            "/api/avances",
            self.db_path,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-25T19:00",
                "avance_cm": 3,
            },
        )
        self.assertEqual(status, 201)

    def test_update_truck_load_recalculates_linked_zone_from_plant_departure(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        colado_id = created["id"]
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            generate_zones(
                conn,
                {
                    "colado_id": colado_id,
                    "hora_zona_1": "2026-07-24T10:00",
                    "intervalo_minutos": 60,
                    "temperatura_inicial_c": 30,
                },
            )
            zone_2 = get_zones(conn, colado_id)[1]
        finally:
            conn.close()

        status, body = handle_put(
            f"/api/descargas/{zone_2['descarga_olla_id']}",
            self.db_path,
            {
                "numero_olla": "2",
                "volumen_m3": 5,
                "hora_salida_planta": "2026-07-24T11:30",
                "hora_llegada_obra": "2026-07-24T11:50",
                "hora_inicio_descarga": "2026-07-24T12:00",
                "hora_fin_descarga": "2026-07-24T12:10",
                "temperatura_llegada_c": 31.5,
                "revenimiento_cm": 18,
            },
            path_id,
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["descarga"]["hora_salida_planta"], "2026-07-24T11:30")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            zones = get_zones(conn, colado_id)
            updated_zone_2 = zones[1]
            state = calculate_mold_state(conn, colado_id, as_of_iso="2026-07-24T14:30")
            zone_2_state = next(zone for zone in state["zonas_activas"] if zone["zona_numero"] == 2)
        finally:
            conn.close()

        self.assertEqual(updated_zone_2["hora_salida_planta"], "2026-07-24T11:30")
        self.assertEqual(updated_zone_2["hora_inicio_descarga"], "2026-07-24T12:00")
        self.assertEqual(updated_zone_2["temperatura_inicial_c"], 31.5)
        self.assertEqual(zone_2_state["edad_real_h"], 3.0)

    def test_register_truck_zone_endpoint_creates_matching_zone(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        colado_id = created["id"]

        status, body = handle_post(
            "/api/ollas/registrar-zona",
            self.db_path,
            {
                "colado_id": colado_id,
                "numero_olla": 2,
                "hora_salida_planta": "2026-07-24T11:00",
                "hora_llegada_obra": "2026-07-24T11:45",
                "hora_inicio_descarga": "2026-07-24T11:50",
                "volumen_m3": 5,
                "temperatura_llegada_c": 31,
            },
        )

        self.assertEqual(status, 201)
        self.assertEqual(body["zona"]["zona_numero"], 2)
        self.assertEqual(body["zona"]["elevacion_inferior_cm"], 30)
        self.assertEqual(body["zona"]["elevacion_superior_cm"], 60)
        self.assertEqual(body["zona"]["hora_referencia_madurez"], "2026-07-24T11:00")
        self.assertEqual(body["estado_molde"]["estado_operativo"], "MOLDE_INCOMPLETO")

    def test_backend_requires_confirmation_for_suspicious_truck_time(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        colado_id = created["id"]
        payload = {
            "colado_id": colado_id,
            "numero_olla": 1,
            "hora_salida_planta": "2099-07-24T11:00",
            "volumen_m3": 5,
            "temperatura_llegada_c": 31,
        }

        with self.assertRaises(DataQualityWarningError) as ctx:
            handle_post("/api/ollas/registrar-zona", self.db_path, dict(payload))

        self.assertEqual(ctx.exception.warnings[0]["code"], "HORA_FUTURA")

        status, body = handle_post(
            "/api/ollas/registrar-zona",
            self.db_path,
            payload | {"confirmar_horario_sospechoso": True, "operador": "QA"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["zona"]["hora_salida_planta"], "2099-07-24T11:00")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            audits = [dict(row) for row in conn.execute("SELECT * FROM auditoria_operativa ORDER BY id").fetchall()]
        finally:
            conn.close()
        self.assertTrue(any(row["accion"] == "REGISTER_TRUCK_ZONE_WITH_WARNINGS" for row in audits))

    def test_apply_cylinder_schedule_recipe_uses_active_scenario(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        colado_id = created["id"]

        status, body = handle_post(
            "/api/programa-deslizado/ensayo",
            self.db_path,
            {
                "colado_id": colado_id,
                "t_fabricacion": "2026-07-24T18:00",
                "resultado_4h": "PASA",
                "layer_thickness_cm": 30,
                "total_layers": 7,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["estado_ensayo"]["receta_sugerida"]["intervalo_objetivo_min"], 8)

        status, applied = handle_post(
            "/api/programa-deslizado/aplicar-receta",
            self.db_path,
            {"colado_id": colado_id, "fecha_hora": "2026-07-24T22:00", "operador": "Operador"},
        )

        self.assertEqual(status, 201)
        self.assertEqual(applied["receta_activa"]["avance_objetivo_cm"], 3)
        self.assertEqual(applied["receta_activa"]["intervalo_objetivo_min"], 8)
        self.assertEqual(applied["receta_activa"]["velocidad_objetivo_cm_h"], 22.5)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            recipe = get_active_advance_recipe(conn, colado_id)
        finally:
            conn.close()
        self.assertEqual(recipe["intervalo_objetivo_min"], 8)

    def test_initialize_start_offset_endpoint_creates_inherited_zone(self) -> None:
        _, created = handle_post(
            "/api/colados",
            self.db_path,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        colado_id = created["id"]

        status, body = handle_post(
            "/api/colados/inicializar-arranque",
            self.db_path,
            {
                "colado_id": colado_id,
                "primera_zona_nueva": 2,
                "hora_inicio_operativo": "2026-07-24T10:00",
                "motivo": "Zona 1 existente",
                "operador": "Operador",
                "supervisor": "Supervisor",
            },
        )

        self.assertEqual(status, 201)
        self.assertEqual(body["siguiente_olla_sugerida"], 2)
        self.assertEqual(len(body["zonas_heredadas"]), 1)
        self.assertEqual(body["zonas_heredadas"][0]["estado"], "EXISTENTE_PREVIO")
        self.assertEqual(body["estado_molde"]["zonas_confirmadas_iniciales"], 1)
        self.assertEqual(body["estado_molde"]["ventana_molde"]["base_cm"], 0)
        self.assertEqual(body["estado_molde"]["zonas_requeridas_molde"], [1, 2, 3, 4])
        self.assertEqual(body["estado_molde"]["zona_en_liberacion"]["zona_numero"], 2)
        self.assertEqual(body["estado_molde"]["estado_operativo"], "MOLDE_INCOMPLETO")


if __name__ == "__main__":
    unittest.main()
