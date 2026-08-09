"""Route registry used for documentation and contract tests."""

GET_ROUTES = {
    "/": "static_index",
    "/api/bootstrap": "bootstrap",
    "/api/health": "health",
    "/api/schema/version": "schema_version",
    "/api/backups": "list_backups",
    "/api/auditoria": "audit_log",
    "/api/calidad-datos": "data_quality",
    "/api/eventos": "events",
    "/api/proyecto": "project",
    "/api/prediccion": "prediction",
    "/api/molde/estado": "mold_state",
    "/api/scada/estado": "scada_state",
    "/api/scada/alarmas": "scada_alarms",
    "/api/tendencias": "trends",
    "/api/receta-avance": "advance_recipe",
    "/api/programa-deslizado": "slipform_schedule",
    "/api/zonas": "zones",
    "/api/descargas": "truck_loads",
    "/api/turnos": "shifts",
    "/api/fotografias": "photo_evidence",
    "/api/desplomes": "plumb_readings",
    "/api/modelo/ajustes": "model_adjustments",
    "/api/sensores/salud": "sensor_health",
    "/api/report/colado.html": "technical_report",
    "/api/report/control-central.html": "control_central_report",
    "/api/report/control-central.pdf": "control_central_report_print",
    "/api/export/lecturas.csv": "readings_csv",
    "/api/export/eventos.csv": "events_csv",
    "/api/export/zonas.csv": "zones_csv",
    "/api/export/avances.csv": "advances_csv",
    "/api/export/bitacora.csv": "operational_log_csv",
    "/api/export/control-central.zip": "control_central_zip",
}

POST_ROUTES = {
    "/api/colados": "create_colado",
    "/api/proyecto": "save_project",
    "/api/lecturas": "create_reading",
    "/api/sensor-readings": "create_sensor_reading",
    "/api/eventos": "create_event",
    "/api/molde/configuracion": "save_mold_config",
    "/api/descargas": "create_truck_load",
    "/api/colados/inicializar-arranque": "initialize_colado_start_offset",
    "/api/ollas/registrar-zona": "register_truck_zone",
    "/api/zonas": "create_zone",
    "/api/zonas/generar": "generate_zones",
    "/api/zonas/asegurar-continuidad": "ensure_zone_continuity",
    "/api/zonas/liberar-por-criterio": "release_zone_by_field_criteria",
    "/api/lecturas-zona": "create_zone_reading",
    "/api/avances": "create_advance",
    "/api/avances/registrar-5min": "create_recipe_advance",
    "/api/scada/confirmar-avance": "confirm_scada_advance",
    "/api/scada/alarmas/reconocer": "acknowledge_alarm",
    "/api/fotografias": "create_photo_evidence",
    "/api/desplomes": "create_desplome",
    "/api/sensores/ingesta": "ingest_sensor_reading",
    "/api/backups": "create_backup",
    "/api/demo/reset": "reset_demo_data",
    "/api/turnos": "start_shift",
    "/api/turnos/cerrar": "close_shift",
    "/api/modelo/ajustes": "create_model_adjustment",
    "/api/receta-avance": "save_advance_recipe",
    "/api/programa-deslizado": "save_slipform_schedule",
    "/api/programa-deslizado/ensayo": "save_cylinder_test_schedule",
    "/api/programa-deslizado/aplicar-receta": "apply_slipform_schedule_recipe",
    "/api/bitacora-escrita/plantillas": "create_written_log_templates",
    "/api/bitacora-escrita/preview": "preview_written_log_import",
    "/api/bitacora-escrita/ocr-preview": "preview_written_log_ocr_import",
    "/api/bitacora-escrita/importar": "commit_written_log_import",
    "/api/simular-curva": "simulate_curve",
    "/api/simular-operacion": "simulate_operation",
}

PUT_ROUTES = {
    "/api/colados": "update_colado",
    "/api/descargas": "update_truck_load",
}

DELETE_ROUTES = {
    "/api/colados": "delete_colado",
}

ROUTE_GROUPS = {
    "GET": GET_ROUTES,
    "POST": POST_ROUTES,
    "PUT": PUT_ROUTES,
    "DELETE": DELETE_ROUTES,
}

__all__ = ["DELETE_ROUTES", "GET_ROUTES", "POST_ROUTES", "PUT_ROUTES", "ROUTE_GROUPS"]
