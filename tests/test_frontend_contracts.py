from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def _assert_view_exports_required_names(self, global_name: str, module_filename: str) -> None:
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")
        module = (ROOT / "static" / "js" / module_filename).read_text(encoding="utf-8")

        legacy_match = re.search(rf"const\s+\{{(?P<body>[^{{}}]*?)\}}\s*=\s*window\.{global_name}", legacy, re.S)
        self.assertIsNotNone(legacy_match)
        required = {
            name.strip()
            for name in legacy_match.group("body").split(",")
            if name.strip()
        }

        return_match = re.search(r"return\s+\{(?P<body>[^{}]*?)\};\s*\}\)\(\);", module, re.S)
        self.assertIsNotNone(return_match)
        exported = {
            name.strip()
            for name in return_match.group("body").split(",")
            if name.strip()
        }

        self.assertTrue(required)
        self.assertTrue(required.issubset(exported), f"Faltan exports: {sorted(required - exported)}")

    def test_operator_view_exports_renderers_used_by_legacy_app(self) -> None:
        self._assert_view_exports_required_names("SlipformOperatorView", "view-operator.js")

    def test_operator_advance_requires_recent_inspection_signal(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")

        self.assertIn('id="operator-slide-form"', index)
        self.assertIn("function latestInspectionOk()", legacy)
        self.assertIn("Primero confirma inspeccion fisica", legacy)

    def test_removed_panels_are_not_part_of_lite_dom_or_load_order(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
        sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")

        for removed in (
            'id="field-command-zone"',
            'id="critical-alarm-banner"',
            'id="trend-detail"',
            'id="movement-detail"',
            'id="alarms-detail"',
            'id="timeline-detail"',
            'id="operator-explanation"',
            'id="trend-prediction-cards"',
            'id="zone-prediction-summary"',
        ):
            self.assertNotIn(removed, index)
        self.assertNotIn("/js/view-scada.js", main)
        self.assertNotIn("/js/view-trends.js", main)
        self.assertNotIn("/js/view-scada.js", sw)
        self.assertNotIn("/js/view-trends.js", sw)
        self.assertFalse((ROOT / "static" / "js" / "view-scada.js").exists())
        self.assertFalse((ROOT / "static" / "js" / "view-trends.js").exists())

    def test_landing_page_uses_labsico_logo_before_app_shell(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
        sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")

        for token in (
            'id="landing-screen"',
            'class="landing-logo"',
            'src="/assets/labsico-logo.jpg"',
            'id="landing-enter"',
            "Entrar al sistema",
        ):
            self.assertIn(token, index)
        self.assertIn("function initLanding()", main)
        self.assertIn('document.body.classList.remove("landing-active")', main)
        self.assertIn("/assets/labsico-logo.jpg", sw)

    def test_operator_has_guided_operation_and_fast_checklist(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")

        for element_id in (
            "operator-action-btn",
            "operator-authorize-btn",
            "operator-slide-form",
            "operator-temp-input",
            "operator-supervisor-input",
            "operator-data-check-list",
            "data-quality-panel",
            "operator-zone-status-list",
            "operator-zone-temp-btn",
            "zone-temperature-dialog",
            "zone-temperature-form",
            "zone-temperature-input",
            "zone-temperature-history",
        ):
            self.assertIn(f'id="{element_id}"', index)
        self.assertIn("function renderOperationalGuidance()", legacy)
        self.assertIn("async function handleOperatorAction", legacy)
        self.assertIn("function openOperatorZoneTemperatureDialog", legacy)
        self.assertIn("async function saveOperatorZoneTemperature", legacy)
        self.assertIn("function loadZoneTemperatureCorrection", legacy)
        self.assertIn("async function invalidateZoneTemperatureReading", legacy)
        self.assertIn("Guardar correccion", legacy)
        self.assertIn("/api/lecturas-zona", legacy)
        self.assertIn("/api/lecturas-zona/anular", legacy)
        self.assertIn("function rememberLocalInspection", legacy)
        self.assertIn("localInspectionSignals", legacy)
        self.assertIn("dataQualityIssues", legacy)

    def test_operator_has_visible_checklist_log_and_demo_controls(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")

        for element_id in (
            "operator-data-check-list",
            "operator-data-check-count",
            "operator-log-list",
            "operator-log-export-link",
            "bitacora-export-link",
            "report-data-quality-panel",
        ):
            self.assertIn(f'id="{element_id}"', index)
        self.assertIn("function renderOperatorDataChecklist", legacy)
        self.assertIn("function renderOperatorLog", legacy)
        self.assertIn("function eventLogText", legacy)
        self.assertIn('/^\\d+$/.test(String(zoneId || ""))', legacy)
        self.assertNotIn('text: `${event.decision_tomada || "--"}; minuto ${format(event.minuto_transcurrido, 1)}.`', legacy)
        self.assertIn("/api/export/bitacora.csv", legacy)

    def test_report_has_written_log_import_flow(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")
        sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")

        for element_id in (
            "written-log-title",
            "written-log-template-btn",
            "written-log-auto-btn",
            "written-log-ocr-status",
            "written-log-base-date",
            "written-log-mode",
            "written-log-operator",
            "written-log-first-fresh-zone",
            "written-log-create-advances",
            "written-log-existing-advances-mode",
            "written-log-events-mode",
            "written-log-advance-interpretation",
            "written-log-ollas-file",
            "written-log-events-file",
            "written-log-status",
            "written-log-preview",
            "written-log-preview-btn",
            "written-log-import-btn",
        ):
            self.assertIn(f'id="{element_id}"', index)

        for token in (
            "/api/bitacora-escrita/plantillas",
            "/api/bitacora-escrita/preview",
            "/api/bitacora-escrita/ocr-preview",
            "/api/bitacora-escrita/importar",
            "function writtenLogPayload",
            "function writtenLogBasePayload",
            "function renderWrittenLogPreview",
            "function writtenLogMessages",
            "function renderWrittenLogOcrStatus",
            "primera_zona_fresca",
            "crear_avances_desde_eventos",
            "modo_avances_existentes",
            "modo_eventos_importados",
            "Eventos a reemplazar",
            "Eventos existentes",
            "avance_total_visible_estimado",
            "Se creara un backup SQLite antes de importar",
        ):
            self.assertIn(token, legacy)
        self.assertIn("seybaplaya-slipform-lite-v19", sw)

    def test_report_can_upload_photos_for_control_central(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "css" / "legacy.css").read_text(encoding="utf-8")

        for element_id in (
            "report-photo-form",
            "report-photo-status",
            "report-photo-count",
            "report-photos-list",
        ):
            self.assertIn(f'id="{element_id}"', index)
        self.assertIn('name="imagenes" type="file" accept="image/*" multiple required', index)
        self.assertIn('$("#report-photo-form")?.addEventListener("submit"', legacy)
        self.assertIn("renderReportPhotos", legacy)
        self.assertIn("/api/fotografias", legacy)
        self.assertIn("report-photo-grid", css)
        self.assertIn("object-fit: contain", css)

    def test_trends_use_local_echarts_assets(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
        sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")

        self.assertIn("/vendor/echarts.min.js", main)
        self.assertIn("/js/app-echarts.js", main)
        self.assertLess(main.index("/vendor/echarts.min.js"), main.index("/js/app-echarts.js"))
        self.assertLess(main.index("/js/app-echarts.js"), main.index("/js/view-operator.js"))
        self.assertIn("/vendor/echarts.min.js", sw)
        self.assertIn("/js/app-echarts.js", sw)

        for chart_id in (
            "operator-temperature-trend",
        ):
            self.assertRegex(index, rf'id="{chart_id}"[^>]*class="[^"]*echart')

    def test_android_assets_removed_from_lite(self) -> None:
        package_json = (ROOT / "package.json").read_text(encoding="utf-8")
        app_state = (ROOT / "static" / "js" / "app-state.js").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")

        self.assertFalse((ROOT / "static" / "js" / "mobile-api.js").exists())
        self.assertFalse((ROOT / "static" / "mobile" / "seed.json").exists())
        self.assertNotIn("android:apk", package_json)
        self.assertNotIn("MobileApiClient", app_state)
        self.assertNotIn("MobileApiClient", legacy)

    def test_trend_view_prefers_echarts_with_canvas_fallback(self) -> None:
        view = (ROOT / "static" / "js" / "view-operator.js").read_text(encoding="utf-8")
        wrapper = (ROOT / "static" / "js" / "app-echarts.js").read_text(encoding="utf-8")

        self.assertIn("window.SlipformECharts", wrapper)
        self.assertIn("renderTemperature", wrapper)
        self.assertIn("renderMaturity", wrapper)
        self.assertIn("renderAdvance", wrapper)
        self.assertIn("renderZoneMaturity", wrapper)
        self.assertIn("echart()?.renderTemperature", view)
        self.assertIn("operator-temperature-trend", view)

    def test_operator_shows_zone_prediction_controls(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        view = (ROOT / "static" / "js" / "view-operator.js").read_text(encoding="utf-8")
        charts = (ROOT / "static" / "js" / "app-echarts.js").read_text(encoding="utf-8")

        for element_id in (
            "operator-maturity-eta",
            "operator-zone-status-list",
        ):
            self.assertIn(f'id="{element_id}"', index)
        self.assertIn("function renderOperatorMaturityEta", view)
        self.assertIn("zone-temperature-action", view)
        self.assertIn("window.saveOperatorZoneTemperature", view)
        self.assertIn("90% / Deslizar", charts)

    def test_operator_and_trends_show_speed_recommendation(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")
        operator = (ROOT / "static" / "js" / "view-operator.js").read_text(encoding="utf-8")

        for element_id in (
            "operator-speed-advice",
            "operator-speed-recommendation",
            "operator-speed-action",
            "operator-speed-reason",
            "operator-speed-suggested",
            "operator-apply-speed-recipe-btn",
            "advance-recipe-suggestion",
            "advance-recipe-suggestion-text",
            "advance-recipe-suggestion-compare",
            "use-recipe-suggestion-btn",
        ):
            self.assertIn(f'id="{element_id}"', index)
        self.assertIn("function renderOperatorSpeedAdvice", legacy)
        self.assertIn("function saveSuggestedAdvanceRecipe", legacy)
        self.assertIn("function fillAdvanceRecipeFormFromSuggestion", legacy)
        self.assertIn("function calculateRecipeSpeeds", legacy)
        self.assertIn('name="avance_objetivo_cm" type="number" step="0.1" min="0.1" value="3.0" required', index)
        self.assertIn('name="intervalo_objetivo_min" type="number" step="0.1" min="0.1" value="6.0" required', index)
        self.assertNotIn('name="avance_objetivo_cm" type="number" step="0.1" min="0.1" value="3.0" readonly', index)
        self.assertNotIn('name="intervalo_objetivo_min" type="number" step="0.1" min="0.1" value="6.0" readonly', index)
        self.assertIn('name="tolerancia_velocidad_min_cm_h" type="number" step="0.1" value="25" readonly', index)
        self.assertIn('name="tolerancia_velocidad_max_cm_h" type="number" step="0.1" value="35" readonly', index)
        self.assertIn("Puedes ajustar avance e intervalo", index)
        self.assertIn("receta_sugerida", legacy)
        self.assertIn("prediccion_deslizamiento", legacy)
        self.assertIn("renderOperatorLiveTrend", operator)

    def test_colado_form_hides_truck_operational_times(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        colado_form = index.split('<form id="colado-form"', 1)[1].split("</form>", 1)[0]
        start_offset_form = index.split('<form id="start-offset-form"', 1)[1].split("</form>", 1)[0]
        truck_form = index.split('<form id="truck-zone-form"', 1)[1].split("</form>", 1)[0]

        for field_name in (
            "hora_salida_planta",
            "hora_llegada_obra",
            "hora_inicio_descarga",
            "hora_colocacion_en_molde",
            "hora_fin_descarga",
        ):
            self.assertNotIn(f'name="{field_name}"', colado_form)

        self.assertIn('name="estado"', colado_form)
        self.assertIn('name="fecha_cierre" type="datetime-local"', colado_form)

        for field_name in (
            "hora_salida_planta",
            "hora_llegada_obra",
            "hora_inicio_descarga",
            "hora_fin_descarga",
        ):
            self.assertIn(f'name="{field_name}"', truck_form)

        for field_name in (
            "primera_zona_nueva",
            "zonas_previas_existentes",
            "hora_inicio_operativo",
            "supervisor",
        ):
            self.assertIn(f'name="{field_name}"', start_offset_form)

        self.assertIn("/api/colados/inicializar-arranque", (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8"))

        self.assertIn("salida de planta de la primera olla", index)

    def test_closed_colado_has_operator_guards(self) -> None:
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")
        utils = (ROOT / "static" / "js" / "app-utils.js").read_text(encoding="utf-8")

        for token in (
            "function isColadoClosed",
            "function coladoClosureText",
            "applyClosedColadoUi",
            "Colado finalizado",
            "Captura la fecha de cierre",
            "fecha_cierre",
        ):
            self.assertIn(token, legacy)
        self.assertIn('if (value === "CERRADO") return "state-closed";', utils)

    def test_cylinder_schedule_program_tab_contract(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        legacy = (ROOT / "static" / "js" / "legacy-app.js").read_text(encoding="utf-8")

        for element_id in (
            "tab-programa",
            "slip-schedule-form",
            "program-scenario",
            "program-recipe",
            "program-layers-table",
            "program-apply-recipe-btn",
            "program-simple-zone",
            "program-next-load-summary",
            "program-pass-4h-btn",
            "program-fail-4h-btn",
            "program-pass-5h-btn",
            "program-fail-5h-btn",
            "program-pass-6h-btn",
            "program-fail-6h-btn",
            "program-next-evaluation-btn",
            "program-correct-result-btn",
            "operator-schedule-card",
            "operator-schedule-status",
            "operator-schedule-summary",
        ):
            self.assertIn(f'id="{element_id}"', index)

        for token in (
            "/api/programa-deslizado",
            "/api/programa-deslizado/ensayo",
            "function renderSlipSchedule",
            "function renderSimpleSlipSchedule",
            "function saveSimpleCylinderEvaluation",
            "Confirmar resultado de cilindro",
            "function confirmSuspiciousTiming",
            "Confirmar horarios sospechosos",
            "Estos horarios afectan madurez, programa y reportes.",
            "/api/calidad-datos",
            "function prepareCylinderCorrection",
            "refreshOperatorTrendsSilently",
            "function renderOperatorSchedule",
            "resultado_4h",
            "resultado_5h",
            "resultado_6h",
        ):
            self.assertIn(token, legacy)
        self.assertNotIn("await refreshOperatorTrends();", legacy)

    def test_primary_tabs_start_with_operator_capture_program_bitacora_report(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        nav = index.split('<nav class="tabs"', 1)[1].split("</nav>", 1)[0]
        expected = [
            'data-tab="operador"',
            'data-tab="captura"',
            'data-tab="programa"',
            'data-tab="bitacora"',
            'data-tab="reportes"',
        ]
        positions = [nav.index(item) for item in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('<section id="tab-operador" class="tab-panel active">', index)
        self.assertIn('<section id="tab-bitacora" class="tab-panel">', index)
        self.assertEqual(nav.count('class="tab-button'), 5)
        for removed_tab in (
            "tab-inicio",
            "tab-operacion",
            "tab-zonas",
            "tab-tendencias",
            "tab-eventos",
            "tab-evidencia",
            "tab-sensores",
            "tab-diagnostico",
            "tab-calibracion",
        ):
            self.assertNotIn(f'id="{removed_tab}"', index)

    def test_static_text_has_no_common_mojibake(self) -> None:
        bad_tokens = ("Ã", "Â", "â", "�")
        for path in (ROOT / "static").rglob("*"):
            if path.suffix not in {".html", ".js", ".css"}:
                continue
            text = path.read_text(encoding="utf-8")
            for token in bad_tokens:
                self.assertNotIn(token, text, f"Texto con codificacion danada en {path.relative_to(ROOT)}")


if __name__ == "__main__":
    unittest.main()
