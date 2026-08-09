from __future__ import annotations

import sqlite3
import unittest

from slipform.db import create_colado, init_db, insert_mold_advance, insert_photo_evidence, insert_slide_event
from slipform.http.report_handlers import render_colado_report, render_control_report
from slipform.reports.control_central import build_control_report_context, days_between


class ControlCentralReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.conn.execute("INSERT INTO mezclas(id, nombre) VALUES (1, 'M1')")

    def tearDown(self) -> None:
        self.conn.close()

    def test_days_between_returns_days(self) -> None:
        self.assertEqual(days_between("2026-07-24T00:00", "2026-07-25T12:00"), 1.5)
        self.assertIsNone(days_between(None, "2026-07-25T12:00"))

    def test_build_context_summarizes_advance(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        insert_mold_advance(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-24T10:00",
                "avance_cm": 2.5,
                "intervalo_minutos": 5,
            },
        )
        context = build_control_report_context(self.conn, colado_id)
        self.assertEqual(context["colado"]["id"], colado_id)
        self.assertEqual(context["resumen"]["altura_total_deslizada_m"], 0.025)
        self.assertEqual(len(context["advances"]), 1)
        self.assertEqual(context["operational_log"][0]["tipo"], "AVANCE")

    def test_control_report_uses_historical_period_and_auto_shift_summary(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-07T22:57"},
        )
        for index, when in enumerate(
            [
                "2026-08-05T02:30",
                "2026-08-05T02:44",
                "2026-08-06T00:07",
            ],
            start=1,
        ):
            insert_mold_advance(
                self.conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": when,
                    "minuto_transcurrido": (index - 1) * 14,
                    "avance_cm": 3,
                    "avance_acumulado_cm": index * 3,
                    "asegurar_continuidad": False,
                },
            )

        context = build_control_report_context(self.conn, colado_id)
        html = render_control_report(context)

        self.assertEqual(context["resumen"]["periodo_inicio"], "2026-08-05T02:30:00")
        self.assertEqual(len(context["turnos"]), 2)
        self.assertIn("Historico 2026-08-05", html)
        self.assertIn("2026-08-05T02:30", html)
        self.assertIn("2026-08-06T00:07", html)

    def test_control_report_includes_operational_conclusion(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        context = build_control_report_context(self.conn, colado_id)
        html = render_control_report(context)
        self.assertIn("Conclusion operativa", html)
        self.assertIn("Bitacora Operativa", html)
        self.assertIn("Control con observaciones", html)
        self.assertIn("Faltan lecturas de temperatura", html)

    def test_control_report_includes_discreet_labsico_logo(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )

        context = build_control_report_context(self.conn, colado_id)
        html = render_control_report(context)

        self.assertIn("brand-logo", html)
        self.assertIn('alt="LABSICO"', html)
        self.assertIn("max-height: 44px", html)
        self.assertIn("max-width: 126px", html)

    def test_control_report_includes_colado_closure_state(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        self.conn.execute(
            "UPDATE colados SET estado = 'CERRADO', fecha_cierre = '2026-07-25T18:30' WHERE id = ?",
            (colado_id,),
        )

        context = build_control_report_context(self.conn, colado_id)
        html = render_control_report(context)

        self.assertEqual(context["resumen"]["estado_colado"], "CERRADO")
        self.assertEqual(context["resumen"]["fecha_cierre"], "2026-07-25T18:30")
        self.assertIn("Estado colado", html)
        self.assertIn("CERRADO", html)
        self.assertIn("2026-07-25T18:30", html)

    def test_control_report_operational_log_hides_imported_sliding_events_and_cleans_text(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        insert_slide_event(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-08-07T19:35",
                "decision_tomada": "Deslizado",
                "resultado_fisico": "registro_escrito",
                "observacion": "Importado de bitacora escrita. 696 Hora original: 19:35:00. Fuente: sin imagen capturada linea 318.",
            },
        )
        insert_slide_event(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-08-07T19:40",
                "decision_tomada": "Observacion",
                "resultado_fisico": "registro_escrito",
                "observacion": "Importado de bitacora escrita. Se revisa junta y se continua normal. Hora original: 19:40:00. Fuente: hoja_14.jpg linea 319.",
                "supervisor": "Supervisor",
            },
        )

        context = build_control_report_context(self.conn, colado_id)
        html = render_control_report(context)
        rows = [row for row in context["operational_log"] if row.get("fecha_hora", "").startswith("2026-08-07T19")]
        report_rows = context["bitacora_reporte"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tipo"], "OBSERVACION")
        self.assertEqual(rows[0]["detalle"], "Se revisa junta y se continua normal")
        self.assertEqual(len(report_rows), 1)
        self.assertEqual(report_rows[0]["tipo"], "OBSERVACION")
        self.assertEqual(report_rows[0]["detalle"], "Se revisa junta y se continua normal")
        self.assertIn("Se revisa junta y se continua normal", html)
        self.assertNotIn("Deslizado - registro_escrito", html)
        self.assertNotIn("Importado de bitacora escrita", html)
        self.assertNotIn("Fuente: sin imagen capturada", html)

    def test_control_report_places_all_photos_in_print_section(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        for index in range(1, 10):
            insert_photo_evidence(
                self.conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": f"2026-07-24T10:{index:02d}",
                    "descripcion": f"Evidencia {index}",
                    "imagen_data_url": "data:image/png;base64,aW1hZ2Vu",
                },
            )

        context = build_control_report_context(self.conn, colado_id)
        html = render_control_report(context)

        self.assertIn("Evidencia Fotografica", html)
        self.assertIn("photo-section", html)
        self.assertIn("object-fit: contain", html)
        self.assertIn("break-inside: avoid", html)
        self.assertIn("Evidencia 1", html)
        self.assertIn("Evidencia 9", html)
        self.assertNotIn("Fotografias Actualizadas", html)

    def test_printable_colado_report_includes_control_summary(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        insert_mold_advance(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-24T10:00",
                "minuto_transcurrido": 60,
                "avance_cm": 3,
                "avance_acumulado_cm": 3,
                "asegurar_continuidad": False,
            },
        )
        context = build_control_report_context(self.conn, colado_id)

        html = render_colado_report(
            context["colado"],
            context["readings"],
            context["events"],
            {"estado": "SIN_DATOS", "avance": 0},
            context["zones"],
            context["advances"],
            context["mold_state"],
            context["alarms"],
            context["decisions"],
            context,
        )

        for token in (
            "Resumen Operativo De Deslizado",
            "Altura visible",
            "Ritmo programado",
            "Estado molde",
            "Avance Real Vs Programado",
            "Avance Por Turno",
        ):
            self.assertIn(token, html)
        self.assertNotIn("orange", html.lower())

    def test_printable_colado_report_uses_historical_control_turns_and_chart(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-08-07T22:57"},
        )
        for index, when in enumerate(
            [
                "2026-08-05T02:30",
                "2026-08-05T02:44",
                "2026-08-06T00:07",
            ],
            start=1,
        ):
            insert_mold_advance(
                self.conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": when,
                    "minuto_transcurrido": (index - 1) * 14,
                    "avance_cm": 3,
                    "avance_acumulado_cm": index * 3,
                    "asegurar_continuidad": False,
                },
            )
        context = build_control_report_context(self.conn, colado_id)

        html = render_colado_report(
            context["colado"],
            context["readings"],
            context["events"],
            {"estado": "SIN_DATOS", "avance": 0},
            context["zones"],
            context["advances"],
            context["mold_state"],
            context["alarms"],
            context["decisions"],
            context,
        )

        self.assertIn("Historico 2026-08-05", html)
        self.assertIn("Historico 2026-08-06", html)
        self.assertIn("2026-08-05T02:30", html)
        self.assertIn("Grafica de avance", html)

    def test_printable_colado_report_shows_event_date_not_elapsed_minute(self) -> None:
        colado_id = create_colado(
            self.conn,
            {"silo_id": "S1", "mezcla_id": 1, "hora_colocacion_en_molde": "2026-07-24T09:00"},
        )
        insert_slide_event(
            self.conn,
            {
                "colado_id": colado_id,
                "fecha_hora": "2026-07-26T16:24",
                "decision_tomada": "Deslizado",
                "resultado_fisico": "registro_escrito",
                "observacion": "Importado de bitacora escrita. 63 cm. Hora original: 16:24.",
            },
        )
        event = dict(self.conn.execute("SELECT * FROM eventos_deslizamiento WHERE colado_id = ?", (colado_id,)).fetchone())
        html = render_colado_report(
            {"id": colado_id, "silo_id": "S1"},
            [],
            [event],
            {"estado": "SIN_DATOS", "avance": 0},
        )

        self.assertIn("<th>Fecha</th><th>Decision</th>", html)
        self.assertIn("2026-07-26T16:24", html)
        self.assertNotIn("<th>Min</th><th>Decision</th>", html)

    def test_missing_colado_returns_null_contract(self) -> None:
        self.assertEqual(build_control_report_context(self.conn, 999), {"colado": None})


if __name__ == "__main__":
    unittest.main()
