"""HTTP handlers for exports and printable reports."""

from __future__ import annotations

import zipfile
import base64
import binascii
import re
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from slipform.core import calculate_state
from slipform.db import (
    connect,
    get_advances,
    get_colado,
    get_events,
    get_readings,
    get_reference_points,
    get_zones,
    init_db,
    insert_generated_report,
    list_operator_decisions,
    list_operational_alarms,
)
from slipform.mold import calculate_mold_state
from slipform.reports.control_central import build_control_report_context
from slipform.reports.csv_export import rows_to_csv
from slipform.reports.rendering import escape_html, svg_line_chart

HttpBytesResponse = tuple[int, dict[str, str], bytes]
ROOT = Path(__file__).resolve().parents[2]
LABSICO_LOGO_PATH = ROOT / "static" / "assets" / "labsico-logo.jpg"


def handle_report_get(path: str, query: str, db_path: Path) -> HttpBytesResponse | None:
    params = parse_qs(query)

    if path == "/api/export/lecturas.csv":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            readings = get_readings(conn, colado_id)
        return _csv_response(f"lecturas_colado_{colado_id}.csv", rows_to_csv(readings, _READING_COLUMNS))

    if path == "/api/export/eventos.csv":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            events = get_events(conn, colado_id)
        return _csv_response(f"eventos_colado_{colado_id}.csv", rows_to_csv(events, _EVENT_COLUMNS))

    if path == "/api/export/zonas.csv":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            zones = get_zones(conn, colado_id)
        return _csv_response(f"zonas_colado_{colado_id}.csv", rows_to_csv(zones))

    if path == "/api/export/avances.csv":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            advances = get_advances(conn, colado_id)
        return _csv_response(f"avances_colado_{colado_id}.csv", rows_to_csv(advances))

    if path == "/api/export/bitacora.csv":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            context = build_control_report_context(conn, colado_id)
        if not context["colado"]:
            return _not_found()
        return _csv_response(f"bitacora_colado_{colado_id}.csv", rows_to_csv(context["operational_log"]))

    if path == "/api/report/colado.html":
        colado_id = int(params.get("colado_id", ["0"])[0])
        return _colado_report_response(db_path, colado_id)

    if path in ("/api/report/control-central.html", "/api/report/control-central.pdf"):
        colado_id = int(params.get("colado_id", ["0"])[0])
        return _control_report_response(db_path, colado_id)

    if path == "/api/export/control-central.zip":
        colado_id = int(params.get("colado_id", ["0"])[0])
        return _control_zip_response(db_path, colado_id)

    return None


def _csv_response(filename: str, csv_text: str) -> HttpBytesResponse:
    body = csv_text.encode("utf-8")
    return 200, _headers("text/csv; charset=utf-8", filename, body), body


def _html_response(html: str) -> HttpBytesResponse:
    body = html.encode("utf-8")
    return 200, _headers("text/html; charset=utf-8", None, body), body


def _not_found() -> HttpBytesResponse:
    body = b"Not found"
    return 404, _headers("text/plain; charset=utf-8", None, body), body


def _headers(content_type: str, filename: str | None, body: bytes) -> dict[str, str]:
    headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
    if filename:
        headers["Content-Disposition"] = f"attachment; filename={filename}"
    return headers


def _colado_report_response(db_path: Path, colado_id: int) -> HttpBytesResponse:
    with connect(db_path) as conn:
        init_db(conn)
        colado = get_colado(conn, colado_id)
        if not colado:
            return _not_found()
        readings = get_readings(conn, colado_id)
        events = get_events(conn, colado_id)
        zones = get_zones(conn, colado_id)
        advances = get_advances(conn, colado_id)
        alarms = list_operational_alarms(conn, colado_id, include_closed=True)
        decisions = list_operator_decisions(conn, colado_id)
        mold_state = calculate_mold_state(conn, colado_id) if zones else None
        reference = get_reference_points(conn, colado.get("curva_id"))
        prediction = calculate_state(readings, colado.get("parametros"), reference)
        control_context = build_control_report_context(conn, colado_id)
        zone_temperature_readings = _get_zone_temperature_readings(conn, colado_id)
    return _html_response(
        render_colado_report(
            colado,
            readings,
            events,
            prediction,
            zones,
            advances,
            mold_state,
            alarms,
            decisions,
            control_context,
            zone_temperature_readings=zone_temperature_readings,
        )
    )


def _control_report_response(db_path: Path, colado_id: int) -> HttpBytesResponse:
    with connect(db_path) as conn:
        init_db(conn)
        context = build_control_report_context(conn, colado_id)
        if not context["colado"]:
            return _not_found()
        html = render_control_report(context)
        insert_generated_report(conn, {"colado_id": colado_id, "tipo": "CONTROL_CENTRAL", "resumen": context["resumen"]})
    return _html_response(html)


def _control_zip_response(db_path: Path, colado_id: int) -> HttpBytesResponse:
    with connect(db_path) as conn:
        init_db(conn)
        context = build_control_report_context(conn, colado_id)
        if not context["colado"]:
            return _not_found()
        files = {
            "control_central.html": render_control_report(context),
            "avances.csv": rows_to_csv(context["advances"]),
            "turnos.csv": rows_to_csv(context["turnos"]),
            "zonas.csv": rows_to_csv(context["zones"]),
            "lecturas.csv": rows_to_csv(context["readings"]),
            "eventos.csv": rows_to_csv(context["events"]),
            "alarmas.csv": rows_to_csv(context["alarms"]),
            "decisiones.csv": rows_to_csv(context["decisions"]),
            "bitacora.csv": rows_to_csv(context["operational_log"]),
            "desplomes.csv": rows_to_csv(context["desplomes"]),
            "fotografias.csv": rows_to_csv([{k: v for k, v in row.items() if k != "imagen_data_url"} for row in context["fotografias"]]),
        }

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode("utf-8"))
        for photo in context["fotografias"]:
            data_url = photo.get("imagen_data_url")
            decoded = _decode_data_url(data_url)
            if decoded:
                archive.writestr(_photo_zip_name(photo, decoded["extension"]), decoded["bytes"])
            elif data_url:
                archive.writestr(f"fotografias/foto_{photo['id']}.dataurl.txt", str(data_url).encode("utf-8"))
    body = buffer.getvalue()
    return 200, _headers("application/zip", f"control_central_colado_{colado_id}.zip", body), body


def _decode_data_url(value: Any) -> dict[str, Any] | None:
    text = str(value or "")
    if not text.startswith("data:") or "," not in text:
        return None
    meta, encoded = text.split(",", 1)
    if ";base64" not in meta:
        return None
    mime = meta.removeprefix("data:").split(";", 1)[0].lower()
    extension = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get(mime, "bin")
    try:
        return {"bytes": base64.b64decode(encoded, validate=True), "extension": extension}
    except (ValueError, binascii.Error):
        return None


def _photo_zip_name(photo: dict[str, Any], extension: str) -> str:
    raw = str(photo.get("descripcion") or f"foto_{photo.get('id') or 'sin_id'}")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")[:80] or "foto"
    return f"fotografias/{int(photo.get('id') or 0):04d}_{safe}.{extension}"


def _get_zone_temperature_readings(conn, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                lz.id,
                z.zona_numero,
                COALESCE(d.numero_olla, CAST(z.zona_numero AS TEXT)) AS numero_olla,
                COALESCE(d.hora_salida_planta, z.hora_salida_planta, z.hora_referencia_madurez) AS hora_salida_planta,
                lz.fecha_hora,
                lz.minuto_desde_zona,
                lz.temperatura_concreto_c,
                lz.temperatura_ambiente_c,
                lz.humedad_relativa_pct,
                lz.origen
            FROM lecturas_zona lz
            JOIN zonas_colado z ON z.id = lz.zona_colado_id
            LEFT JOIN descargas_olla d ON d.id = z.descarga_olla_id
            WHERE z.colado_id = ? AND lz.valido = 1
            ORDER BY z.zona_numero, lz.minuto_desde_zona, lz.id
            """,
            (colado_id,),
        ).fetchall()
    ]


def render_control_report(context: dict[str, Any]) -> str:
    esc = escape_html
    project = context["proyecto"]
    colado = context["colado"]
    summary = context["resumen"]
    advances = context["advances"]
    turnos = context["turnos"]
    zones = context["zones"]
    alarms = context["alarms"]
    decisions = context["decisions"]
    operational_log = context.get("operational_log") or []
    report_log = context.get("bitacora_reporte") or []
    events = context["events"]
    readings = context["readings"]
    fotos = context["fotografias"]
    desplomes = context["desplomes"]
    mold_state = context["mold_state"] or {}
    target_speed = float(summary.get("ritmo_programado_cm_h") or 30)
    labsico_logo = _labsico_logo_markup()

    turno_rows = _rows(
        turnos,
        lambda t: [
            t.get("turno"),
            t.get("inicio_turno"),
            t.get("fin_turno"),
            t.get("operador"),
            t.get("avance_parcial_m"),
            t.get("avance_acumulado_m"),
            t.get("ritmo_cm_h"),
            t.get("observaciones"),
        ],
    )
    avance_rows = _rows(advances, lambda a: [a.get("fecha_hora"), a.get("avance_cm"), a.get("avance_acumulado_cm"), a.get("velocidad_real_cm_h"), a.get("operador")])
    zone_rows = _rows(
        zones[-80:],
        lambda z: [
            z.get("zona_numero"),
            z.get("numero_olla") or z.get("zona_numero"),
            z.get("volumen_olla_m3") or z.get("volumen_m3"),
            f"{z.get('elevacion_inferior_cm')}-{z.get('elevacion_superior_cm')}",
            z.get("hora_salida_planta") or z.get("hora_referencia_madurez"),
            z.get("hora_inicio_descarga") or z.get("hora_inicio_llenado"),
            z.get("estado"),
        ],
    )
    alarm_rows = _rows(alarms[:40], lambda a: [a.get("fecha_hora_inicio"), a.get("tipo"), a.get("severidad"), a.get("estado"), a.get("mensaje")])
    decision_rows = _rows(decisions[:40], lambda d: [d.get("fecha_hora"), d.get("recomendacion_sistema"), d.get("decision_operador"), d.get("operador"), d.get("supervisor"), d.get("observacion")])
    bitacora_rows = _rows(report_log, lambda b: [b.get("fecha_hora"), b.get("tipo"), b.get("zona"), b.get("detalle"), b.get("operador"), b.get("supervisor")])
    desplome_rows = _rows(desplomes[:60], lambda d: [d.get("fecha_hora"), d.get("punto"), d.get("direccion"), d.get("lectura_mm"), d.get("tolerancia_mm"), d.get("estado")])
    photo_cards = "".join(_photo_card(photo) for photo in fotos)
    chart = svg_line_chart(
        advances,
        "minuto_transcurrido",
        "avance_acumulado_cm",
        target_speed,
        x_label_key="fecha_hora",
        x_axis_title="Fecha / hora",
        y_axis_title="Avance acumulado (cm)",
        y_tick_step=100,
        legend=True,
    )
    window = mold_state.get("ventana_molde") or {}
    explanation = mold_state.get("explicacion_operativa") or {}
    explanation_items = "".join(f"<li>{esc(item)}</li>" for item in explanation.get("items", []))
    conclusion = _operational_conclusion(context)
    conclusion_items = "".join(f"<li>{esc(item)}</li>" for item in conclusion["items"])

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Control Central De Deslizado - Colado {esc(colado.get('id'))}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 18px; color: #172026; }}
    .sheet {{ border: 1px solid #737373; padding: 14px; }}
    header {{ display: grid; grid-template-columns: 150px 1fr 150px; align-items: center; gap: 16px; text-align: center; }}
    .logo {{ min-height: 58px; display: flex; align-items: center; justify-content: center; color: #64748b; font-weight: 700; }}
    .brand-logo img {{ max-width: 126px; max-height: 44px; object-fit: contain; opacity: 0.92; }}
    .text-logo {{ border: 1px solid #cbd5db; padding: 6px; font-size: 11px; line-height: 1.2; }}
    .bar {{ background: #0ea5e9; color: #fff; text-align: center; font-weight: 700; padding: 6px; margin: 12px 0; }}
    .summary {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-bottom: 12px; }}
    .box {{ border: 1px solid #cbd5db; padding: 8px; min-height: 54px; }}
    .box b {{ display: block; color: #475569; font-size: 11px; text-transform: uppercase; }}
    .layout {{ display: grid; grid-template-columns: 1.1fr 1.7fr 1fr; gap: 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
    th, td {{ border: 1px solid #d6dde1; padding: 4px; text-align: left; }}
    th {{ background: #eef2f3; color: #334155; }}
    h2 {{ font-size: 14px; margin: 12px 0 6px; }}
    svg {{ width: 100%; border: 1px solid #d6dde1; }}
    .photos {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; align-items: start; }}
    .operational-reading {{ border: 1px solid #94a3b8; border-left: 6px solid #0f766e; padding: 10px; margin: 10px 0 12px; background: #f8fafc; }}
    .operational-reading strong {{ display: block; font-size: 15px; margin-bottom: 4px; }}
    .operational-reading p {{ margin: 0 0 6px; font-weight: 700; }}
    .operational-reading ul {{ margin: 0; padding-left: 18px; font-size: 11px; }}
    .conclusion {{ border: 2px solid #cbd5db; border-left-width: 8px; padding: 10px; margin: 10px 0 12px; background: #fff; }}
    .conclusion.ok {{ border-left-color: #147a4d; background: #f0fdf4; }}
    .conclusion.warn {{ border-left-color: #b45309; background: #fff7ed; }}
    .conclusion.critical {{ border-left-color: #b42318; background: #fee2e2; }}
    .conclusion strong {{ display: block; font-size: 15px; margin-bottom: 4px; }}
    .conclusion ul {{ margin: 0; padding-left: 18px; font-size: 11px; }}
    figure {{ margin: 0; border: 1px solid #d6dde1; padding: 4px; break-inside: avoid; page-break-inside: avoid; }}
    img, .photo-empty {{ width: 100%; height: 155px; object-fit: contain; background: #f1f5f9; display: block; }}
    figcaption {{ font-size: 10px; color: #475569; margin-top: 4px; }}
    .print {{ margin-bottom: 10px; }}
    .photo-section {{ break-before: page; page-break-before: always; }}
    .photo-empty {{ display: flex; align-items: center; justify-content: center; }}
    @media print {{
      .print {{ display: none; }}
      body {{ margin: 0; }}
      .sheet {{ border: 0; }}
      .photos {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      img, .photo-empty {{ height: 180px; }}
    }}
  </style>
</head>
<body>
  <button class="print" onclick="window.print()">Imprimir / Guardar PDF</button>
  <section class="sheet">
    <header>
      <div class="logo brand-logo">{labsico_logo}</div>
      <div>
        <strong>CLIENTE: {esc(project.get('cliente'))}</strong><br>
        <strong>EDIFICIO: {esc(project.get('elemento') or project.get('obra'))}</strong><br>
        <strong>UBICACION: {esc(project.get('ubicacion'))}</strong>
      </div>
      <div class="logo text-logo">{esc(project.get('logo_derecho') or project.get('logo_izquierdo') or 'Control de deslizado')}</div>
    </header>
    <div class="bar">CONTROL CENTRAL DE DESLIZADO</div>
    <div class="summary">
      <div class="box"><b>Colado</b>#{esc(colado.get('id'))} {esc(colado.get('silo_id'))}</div>
      <div class="box"><b>Altura visible</b>{esc(summary.get('altura_visible_m') or summary.get('altura_total_deslizada_m'))} m</div>
      <div class="box"><b>Ritmo real</b>{esc(summary.get('ritmo_real_cm_h'))} cm/h</div>
      <div class="box"><b>Ritmo programado</b>{esc(summary.get('ritmo_programado_cm_h'))} cm/h</div>
      <div class="box"><b>Volumen estimado</b>{esc(project.get('volumen_estimado_m3'))} m3</div>
      <div class="box"><b>Area cimbra</b>{esc(project.get('area_cimbra_m2'))} m2</div>
      <div class="box"><b>Inicio operativo</b>{esc(summary.get('periodo_inicio') or colado.get('fecha_hora_inicio'))}</div>
      <div class="box"><b>Estado colado</b>{esc(summary.get('estado_colado') or colado.get('estado'))}</div>
      <div class="box"><b>Fecha cierre</b>{esc(summary.get('fecha_cierre') or colado.get('fecha_cierre') or 'Abierto')}</div>
      <div class="box"><b>Duracion real</b>{esc(summary.get('duracion_real_dias'))} dias</div>
      <div class="box"><b>Estado molde</b>{esc(mold_state.get('estado_operativo'))}</div>
      <div class="box"><b>Ventana molde</b>{esc(window.get('base_cm'))}-{esc(window.get('corona_cm'))} cm</div>
      <div class="box"><b>Alarmas</b>{esc(summary.get('alarmas'))}</div>
      <div class="box"><b>Desplomes fuera</b>{esc(summary.get('desplomes_fuera_tolerancia'))}</div>
    </div>
    <section class="operational-reading">
      <strong>{esc(explanation.get('titulo') or 'Lectura operativa')}</strong>
      <p>{esc(explanation.get('resumen') or 'Sin explicacion SCADA disponible.')}</p>
      <ul>{explanation_items}</ul>
    </section>
    <section class="conclusion {esc(conclusion['tone'])}">
      <strong>Conclusion operativa: {esc(conclusion['title'])}</strong>
      <ul>{conclusion_items}</ul>
    </section>
    <div class="layout">
      <section>
        <h2>Desplomes</h2>
        <table><thead><tr><th>Fecha</th><th>Punto</th><th>Dir.</th><th>mm</th><th>Tol.</th><th>Estado</th></tr></thead><tbody>{desplome_rows}</tbody></table>
      </section>
      <section>
        <h2>Avance Real Vs Programado</h2>
        {chart}
        <h2>Avance Por Turno</h2>
        <table><thead><tr><th>Turno</th><th>Inicio</th><th>Fin</th><th>Operador</th><th>Parcial m</th><th>Acum. m</th><th>cm/h</th><th>Obs.</th></tr></thead><tbody>{turno_rows}</tbody></table>
        <h2>Avances Del Molde</h2>
        <table><thead><tr><th>Fecha</th><th>Avance cm</th><th>Acum. cm</th><th>cm/h</th><th>Operador</th></tr></thead><tbody>{avance_rows}</tbody></table>
      </section>
      <section>
        <h2>Zonas</h2>
        <table><thead><tr><th>Zona</th><th>Olla</th><th>m3</th><th>Elevacion</th><th>Salida planta</th><th>Inicio descarga</th><th>Estado</th></tr></thead><tbody>{zone_rows}</tbody></table>
        <h2>Alarmas</h2>
        <table><thead><tr><th>Inicio</th><th>Tipo</th><th>Sev.</th><th>Estado</th><th>Mensaje</th></tr></thead><tbody>{alarm_rows}</tbody></table>
        <h2>Decisiones</h2>
        <table><thead><tr><th>Fecha</th><th>Sistema</th><th>Operador</th><th>Op.</th><th>Sup.</th><th>Obs.</th></tr></thead><tbody>{decision_rows}</tbody></table>
        <h2>Bitacora Operativa</h2>
        <table><thead><tr><th>Fecha</th><th>Tipo</th><th>Zona</th><th>Detalle</th><th>Operador</th><th>Supervisor</th></tr></thead><tbody>{bitacora_rows}</tbody></table>
      </section>
    </div>
    <section class="photo-section">
      <h2>Evidencia Fotografica</h2>
      <div class="photos">{photo_cards or '<div class="photo-empty">Sin fotografias</div>'}</div>
    </section>
  </section>
</body>
</html>"""


def _labsico_logo_markup() -> str:
    if not LABSICO_LOGO_PATH.exists():
        return "LABSICO"
    encoded = base64.b64encode(LABSICO_LOGO_PATH.read_bytes()).decode("ascii")
    return f'<img src="data:image/jpeg;base64,{encoded}" alt="LABSICO" />'


def _operational_conclusion(context: dict[str, Any]) -> dict[str, Any]:
    advances = context.get("advances") or []
    zones = context.get("zones") or []
    readings = context.get("readings") or []
    alarms = context.get("alarms") or []
    decisions = context.get("decisions") or []
    events = context.get("events") or []
    active_high_alarms = [
        alarm
        for alarm in alarms
        if str(alarm.get("estado") or "").upper() == "ACTIVA"
        and str(alarm.get("severidad") or "").upper() in {"ALTA", "CRITICA"}
    ]
    off_recommendation = [
        decision
        for decision in decisions
        if str(decision.get("conforme_recomendacion")) in {"0", "False", "false"}
    ]
    physical_findings = [
        event
        for event in events
        if str(event.get("resultado_fisico") or "").lower() not in {"", "correcto"}
    ]
    items = [
        f"Avances registrados: {len(advances)}; zonas registradas: {len(zones)}; lecturas de temperatura: {len(readings)}.",
        f"Alarmas altas/criticas activas: {len(active_high_alarms)}; decisiones contra recomendacion: {len(off_recommendation)}.",
        f"Eventos fisicos no conformes: {len(physical_findings)}.",
    ]
    if not advances:
        items.append("Falta evidencia de avance del molde para cerrar control operativo.")
    if not readings:
        items.append("Faltan lecturas de temperatura para sustentar la madurez calculada.")
    if not decisions:
        items.append("Faltan decisiones del operador registradas con checklist.")
    if active_high_alarms or off_recommendation:
        return {"tone": "critical", "title": "Requiere revision de supervisor", "items": items}
    if physical_findings or not readings or not decisions:
        return {"tone": "warn", "title": "Control con observaciones", "items": items}
    return {"tone": "ok", "title": "Control documentado sin alertas criticas activas", "items": items}


def _printable_control_summary(context: dict[str, Any] | None) -> str:
    if not context or not context.get("colado"):
        return ""
    esc = escape_html
    colado = context["colado"]
    summary = context.get("resumen") or {}
    advances = context.get("advances") or []
    turnos = context.get("turnos") or []
    mold_state = context.get("mold_state") or {}
    window = mold_state.get("ventana_molde") or {}
    target_speed = float(summary.get("ritmo_programado_cm_h") or 30)
    chart = svg_line_chart(
        advances,
        "minuto_transcurrido",
        "avance_acumulado_cm",
        target_speed,
        x_label_key="fecha_hora",
        x_axis_title="Fecha / hora",
        y_axis_title="Avance acumulado (cm)",
        y_tick_step=100,
        legend=True,
    )
    turno_rows = _rows(
        turnos,
        lambda t: [
            t.get("turno"),
            t.get("inicio_turno"),
            t.get("fin_turno"),
            t.get("operador"),
            t.get("avance_parcial_m"),
            t.get("avance_acumulado_m"),
            t.get("ritmo_cm_h"),
            t.get("observaciones"),
        ],
    )
    window_label = ""
    if window.get("base_cm") is not None or window.get("corona_cm") is not None:
        window_label = f"{window.get('base_cm')}-{window.get('corona_cm')} cm"
    return f"""
  <section class="control-summary">
    <h2>Resumen Operativo De Deslizado</h2>
    <div class="control-grid">
      <div class="control-box"><b>Colado</b>#{esc(colado.get('id'))} {esc(colado.get('silo_id'))}</div>
      <div class="control-box"><b>Altura visible</b>{esc(summary.get('altura_visible_m') or summary.get('altura_total_deslizada_m'))} m</div>
      <div class="control-box"><b>Ritmo real</b>{esc(summary.get('ritmo_real_cm_h'))} cm/h</div>
      <div class="control-box"><b>Ritmo programado</b>{esc(summary.get('ritmo_programado_cm_h'))} cm/h</div>
      <div class="control-box"><b>Inicio operativo</b>{esc(summary.get('periodo_inicio') or colado.get('fecha_hora_inicio'))}</div>
      <div class="control-box"><b>Estado colado</b>{esc(summary.get('estado_colado') or colado.get('estado'))}</div>
      <div class="control-box"><b>Fecha cierre</b>{esc(summary.get('fecha_cierre') or colado.get('fecha_cierre') or 'Abierto')}</div>
      <div class="control-box"><b>Duracion real</b>{esc(summary.get('duracion_real_dias'))} dias</div>
      <div class="control-box"><b>Estado molde</b>{esc(mold_state.get('estado_operativo'))}</div>
      <div class="control-box"><b>Ventana molde</b>{esc(window_label)}</div>
      <div class="control-box"><b>Alarmas</b>{esc(summary.get('alarmas'))}</div>
      <div class="control-box"><b>Desplomes fuera</b>{esc(summary.get('desplomes_fuera_tolerancia'))}</div>
    </div>
    <div class="control-layout">
      <section>
        <h3>Avance Real Vs Programado</h3>
        {chart}
      </section>
      <section>
        <h3>Avance Por Turno</h3>
        <table class="compact-table"><thead><tr><th>Turno</th><th>Inicio</th><th>Fin</th><th>Operador</th><th>Parcial m</th><th>Acum. m</th><th>cm/h</th><th>Obs.</th></tr></thead><tbody>{turno_rows}</tbody></table>
      </section>
    </div>
  </section>"""


def _printable_status_line(
    colado: dict[str, Any],
    mold_state: dict[str, Any] | None,
    control_context: dict[str, Any] | None,
    zone_temperature_readings: list[dict[str, Any]] | None,
    prediction: dict[str, Any],
) -> str:
    colado_state = _friendly_colado_state(colado)
    operative_state = _friendly_mold_state(colado, mold_state)
    has_operational_context = bool(
        mold_state
        or zone_temperature_readings
        or (control_context or {}).get("zones")
        or (control_context or {}).get("advances")
        or (control_context or {}).get("events")
    )
    source = "control operativo" if has_operational_context else "lectura general"
    if source == "lectura general" and prediction.get("estado"):
        operative_state = "Sin lectura general" if prediction.get("estado") == "SIN_DATOS" else str(prediction.get("estado"))
    elif not mold_state and has_operational_context:
        operative_state = "Sin zona activa"
    zones_count = len((control_context or {}).get("zones") or [])
    advances_count = len((control_context or {}).get("advances") or [])
    zone_readings_count = len(zone_temperature_readings or [])
    support = f"{zones_count} zonas, {advances_count} avances, {zone_readings_count} lecturas por zona"
    return (
        f"Silo: {colado.get('silo_id') or '--'} | Estado colado: {colado_state} | "
        f"Estado operativo: {operative_state} | Fuente: {source} | Soporte: {support}"
    )


def _printable_operational_summary(
    colado: dict[str, Any],
    prediction: dict[str, Any],
    mold_state: dict[str, Any] | None,
    control_context: dict[str, Any] | None,
    zone_temperature_readings: list[dict[str, Any]] | None,
) -> str:
    esc = escape_html
    zone = (mold_state or {}).get("zona_en_liberacion") or {}
    progress = (mold_state or {}).get("progreso_operativo") or {}
    summary = (control_context or {}).get("resumen") or {}
    latest_zone_reading = _latest_zone_temperature(zone_temperature_readings or [])

    if _is_colado_closed(colado):
        zone_label = "Colado cerrado"
        maturity_label = _format_zone_maturity(zone, fallback="Cierre registrado")
        remaining_label = "No aplica"
    elif zone:
        zone_label = f"Zona {zone.get('zona_numero') or '--'}"
        maturity_label = _format_zone_maturity(zone)
        remaining_label = _format_remaining_minutes(zone)
    else:
        zone_label = "Sin zona activa"
        maturity_label = _format_general_maturity(prediction)
        remaining_label = "Sin estimacion"

    temp_label = _format_zone_temperature(zone, latest_zone_reading)
    visible_advance = summary.get("altura_visible_m") or summary.get("altura_total_deslizada_m")
    if visible_advance not in (None, ""):
        advance_label = f"{visible_advance} m"
    elif progress.get("avance_total_cm") is not None:
        advance_label = f"{progress.get('avance_total_cm')} cm"
    else:
        advance_label = "Sin avance registrado"

    latest_label = _format_latest_zone_reading(latest_zone_reading)
    source_label = "Lecturas por zona"
    if not zone_temperature_readings and prediction.get("temperatura_actual_concreto_c") is not None:
        source_label = "Lectura general"
    elif not zone_temperature_readings:
        source_label = "Sin lecturas de temperatura"

    return f"""
  <div class="operational-summary">
    <div class="box"><b>Zona / condicion</b><br>{esc(zone_label)}</div>
    <div class="box"><b>Madurez zona</b><br>{esc(maturity_label)}</div>
    <div class="box"><b>Temperatura zona</b><br>{esc(temp_label)}</div>
    <div class="box"><b>Avance visible</b><br>{esc(advance_label)}</div>
    <div class="box"><b>Ultima lectura zona</b><br>{esc(latest_label)}</div>
    <div class="box"><b>Min. restantes</b><br>{esc(remaining_label)}<br><small>{esc(source_label)}</small></div>
  </div>"""


def _friendly_colado_state(colado: dict[str, Any]) -> str:
    state = str(colado.get("estado") or "ACTIVO").strip().upper()
    if state == "CERRADO":
        close_date = colado.get("fecha_cierre")
        return f"Cerrado {close_date}" if close_date else "Cerrado"
    if state == "ACTIVO":
        return "Activo"
    return state.replace("_", " ").title()


def _friendly_mold_state(colado: dict[str, Any], mold_state: dict[str, Any] | None) -> str:
    if _is_colado_closed(colado):
        return "Colado cerrado"
    state = str((mold_state or {}).get("estado_operativo") or "").strip()
    if not state:
        return "Sin estado operativo"
    labels = {
        "FALTA_ZONA_SUPERIOR": "Falta zona superior",
        "SIN_ZONA_A_LIBERAR": "Sin zona a liberar",
        "SIN_ZONAS": "Sin zonas registradas",
        "MOLDE_INCOMPLETO": "Molde incompleto",
        "NO_LIBERAR": "No liberar",
        "RIESGO_AGARROTAMIENTO": "Riesgo de agarrotamiento",
        "CONTINUAR": "Continuar",
        "PREPARARSE": "Prepararse",
    }
    return labels.get(state, state.replace("_", " ").title())


def _is_colado_closed(colado: dict[str, Any]) -> bool:
    return str(colado.get("estado") or "").upper() == "CERRADO"


def _format_zone_maturity(zone: dict[str, Any], fallback: str = "Sin dato de zona") -> str:
    for key in ("avance_madurez_efectiva", "avance_madurez"):
        if zone.get(key) is not None:
            return f"{float(zone[key]) * 100:.1f}%"
    if zone.get("madurez_h_eq") is not None:
        return f"{float(zone['madurez_h_eq']):.2f} h_eq"
    return fallback


def _format_general_maturity(prediction: dict[str, Any]) -> str:
    if prediction.get("madurez_acumulada_h_eq") is not None and prediction.get("estado") != "SIN_DATOS":
        return f"{prediction.get('madurez_acumulada_h_eq')} h_eq"
    return "Sin lectura general"


def _format_zone_temperature(zone: dict[str, Any], latest_zone_reading: dict[str, Any] | None) -> str:
    if zone.get("temperatura_actual_c") is not None:
        return f"{float(zone['temperatura_actual_c']):.1f} C"
    if latest_zone_reading and latest_zone_reading.get("temperatura_concreto_c") is not None:
        return f"{float(latest_zone_reading['temperatura_concreto_c']):.1f} C"
    return "Sin lectura"


def _format_remaining_minutes(zone: dict[str, Any]) -> str:
    if zone.get("minutos_restantes_deslizar_ajustado") is not None:
        return f"{float(zone['minutos_restantes_deslizar_ajustado']):.1f} min"
    if zone.get("minutos_restantes_deslizar") is not None:
        return f"{float(zone['minutos_restantes_deslizar']):.1f} min"
    if zone.get("estado_zona") == "LIBERABLE":
        return "Lista para evaluar"
    if zone.get("estado_zona") == "LIBERADA":
        return "Liberada"
    if zone.get("hora_estimada_lista"):
        return f"Estimada {zone.get('hora_estimada_lista')}"
    return "Sin estimacion"


def _latest_zone_temperature(readings: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not readings:
        return None
    return sorted(readings, key=lambda row: str(row.get("fecha_hora") or ""))[-1]


def _format_latest_zone_reading(reading: dict[str, Any] | None) -> str:
    if not reading:
        return "Sin lectura"
    zone = reading.get("zona_numero") or "--"
    time = reading.get("fecha_hora") or "--"
    temp = reading.get("temperatura_concreto_c")
    temp_label = f"{float(temp):.1f} C" if temp is not None else "sin temperatura"
    return f"Zona {zone} | {time} | {temp_label}"


def render_colado_report(
    colado: dict[str, Any],
    readings: list[dict[str, Any]],
    events: list[dict[str, Any]],
    prediction: dict[str, Any],
    zones: list[dict[str, Any]] | None = None,
    advances: list[dict[str, Any]] | None = None,
    mold_state: dict[str, Any] | None = None,
    alarms: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    control_context: dict[str, Any] | None = None,
    zone_temperature_readings: list[dict[str, Any]] | None = None,
) -> str:
    esc = escape_html
    event_rows = _rows(events, lambda e: [e.get("fecha_hora"), e.get("decision_tomada"), e.get("resultado_fisico"), e.get("velocidad_deslizamiento_cm_h"), e.get("supervisor"), e.get("observacion")])
    zone_temperature_rows = _rows(
        zone_temperature_readings or [],
        lambda r: [
            r.get("zona_numero"),
            r.get("numero_olla"),
            r.get("fecha_hora"),
            r.get("hora_salida_planta"),
            r.get("temperatura_concreto_c"),
            r.get("temperatura_ambiente_c"),
            r.get("humedad_relativa_pct"),
        ],
    )
    zone_rows = _rows(
        zones or [],
        lambda z: [
            z.get("zona_numero"),
            f"{z.get('elevacion_inferior_cm')}-{z.get('elevacion_superior_cm')}",
            z.get("numero_olla") or z.get("zona_numero"),
            z.get("volumen_olla_m3") or z.get("volumen_m3"),
            z.get("hora_salida_planta") or z.get("hora_referencia_madurez"),
            z.get("hora_inicio_descarga") or z.get("hora_inicio_llenado"),
            z.get("origen_generacion"),
            z.get("avance_generador_id"),
            z.get("estado"),
        ],
    )
    advance_rows = _rows(advances or [], lambda a: [a.get("fecha_hora"), a.get("avance_cm"), a.get("intervalo_minutos"), a.get("avance_acumulado_cm"), a.get("velocidad_real_cm_h"), a.get("receta_avance_id"), a.get("operador")])
    alarm_rows = _rows(alarms or [], lambda a: [a.get("fecha_hora_inicio"), a.get("tipo"), a.get("severidad"), a.get("estado"), a.get("mensaje"), a.get("operador_reconoce")])
    decision_rows = _rows(decisions or [], lambda d: [d.get("fecha_hora"), d.get("recomendacion_sistema"), d.get("decision_operador"), d.get("conforme_recomendacion"), d.get("operador"), d.get("supervisor"), d.get("observacion")])
    labsico_logo = _labsico_logo_markup()
    mold_summary = ""
    if mold_state:
        next_move = mold_state.get("siguiente_avance_5min") or {}
        mold_summary = f"""
  <h2>Estado Del Molde</h2>
  <div class="summary">
    <div class="box"><b>Estado operativo</b><br>{esc(mold_state.get('estado_operativo'))}</div>
    <div class="box"><b>Avance acumulado</b><br>{esc(mold_state.get('avance_acumulado_cm'))} cm</div>
    <div class="box"><b>Velocidad real</b><br>{esc(mold_state.get('velocidad_real_cm_h'))} cm/h</div>
    <div class="box"><b>Siguiente avance</b><br>{esc(next_move.get('avance_cm'))} cm</div>
  </div>"""
    status_line = _printable_status_line(colado, mold_state, control_context, zone_temperature_readings, prediction)
    operational_summary = _printable_operational_summary(colado, prediction, mold_state, control_context, zone_temperature_readings)
    printable_control_summary = _printable_control_summary(control_context)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Reporte Colado {esc(colado.get('id'))}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #172026; }}
    h1, h2 {{ margin-bottom: 8px; }}
    h3 {{ margin: 10px 0 6px; font-size: 14px; }}
    .printable-header {{ display: grid; grid-template-columns: 1fr 132px; gap: 18px; align-items: start; margin: 8px 0 14px; }}
    .printable-header h1 {{ margin: 0 0 6px; }}
    .printable-logo {{ min-height: 54px; display: flex; align-items: flex-start; justify-content: flex-end; color: #64748b; font-size: 11px; font-weight: 700; }}
    .printable-logo img {{ max-width: 118px; max-height: 46px; object-fit: contain; opacity: 0.92; }}
    .report-meta {{ margin: 4px 0 14px; color: #334155; font-size: 15px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 14px 0; }}
    .operational-summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 14px 0; }}
    .box {{ border: 1px solid #ccd4d8; padding: 10px; border-radius: 6px; }}
    .box small {{ color: #64748b; font-size: 11px; }}
    .control-summary {{ border: 1px solid #cbd5db; padding: 12px; margin: 16px 0 18px; background: #fbfcfd; }}
    .control-summary h2 {{ margin-top: 0; }}
    .control-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 10px 0 12px; }}
    .control-box {{ border: 1px solid #cbd5db; border-radius: 4px; padding: 8px; min-height: 50px; background: #fff; }}
    .control-box b {{ display: block; color: #475569; font-size: 11px; text-transform: uppercase; }}
    .control-layout {{ display: grid; grid-template-columns: 1.15fr 1fr; gap: 12px; align-items: start; }}
    .control-layout svg {{ width: 100%; border: 1px solid #d6dde1; }}
    .compact-table {{ font-size: 11px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
    th, td {{ border-bottom: 1px solid #d6dde1; padding: 7px; text-align: left; }}
    th {{ color: #5c6b73; }}
    @media print {{ button {{ display: none; }} .control-layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <button onclick="window.print()">Imprimir / Guardar PDF</button>
  <header class="printable-header">
    <div>
      <h1>Reporte De Colado #{esc(colado.get('id'))}</h1>
      <p class="report-meta">{esc(status_line)}</p>
    </div>
    <div class="printable-logo">{labsico_logo}</div>
  </header>
  {operational_summary}
  {printable_control_summary}
  {mold_summary}
  <h2>Zonas Del Molde</h2>
  <table><thead><tr><th>Zona</th><th>Elevacion cm</th><th>Olla</th><th>m3</th><th>Salida planta</th><th>Inicio descarga</th><th>Origen</th><th>Avance generador</th><th>Estado</th></tr></thead><tbody>{zone_rows}</tbody></table>
  <h2>Avances Del Molde</h2>
  <table><thead><tr><th>Fecha</th><th>Avance cm</th><th>Intervalo min</th><th>Acumulado cm</th><th>Velocidad cm/h</th><th>Receta</th><th>Operador</th></tr></thead><tbody>{advance_rows}</tbody></table>
  <h2>Alarmas SCADA</h2>
  <table><thead><tr><th>Inicio</th><th>Tipo</th><th>Severidad</th><th>Estado</th><th>Mensaje</th><th>Reconoce</th></tr></thead><tbody>{alarm_rows}</tbody></table>
  <h2>Decisiones Del Operador</h2>
  <table><thead><tr><th>Fecha</th><th>Recomendacion</th><th>Decision</th><th>Conforme</th><th>Operador</th><th>Supervisor</th><th>Observacion</th></tr></thead><tbody>{decision_rows}</tbody></table>
  <h2>Eventos De Deslizamiento</h2>
  <table><thead><tr><th>Fecha</th><th>Decision</th><th>Resultado</th><th>Velocidad</th><th>Supervisor</th><th>Observacion</th></tr></thead><tbody>{event_rows}</tbody></table>
  <h2>Temperatura Por Zona</h2>
  <table><thead><tr><th>Zona</th><th>Olla</th><th>Fecha</th><th>Salida planta</th><th>Concreto C</th><th>Ambiente C</th><th>HR %</th></tr></thead><tbody>{zone_temperature_rows}</tbody></table>
</body>
</html>"""


def _rows(rows: list[dict[str, Any]], cells) -> str:
    return "".join("<tr>" + "".join(f"<td>{escape_html(cell)}</td>" for cell in cells(row)) + "</tr>" for row in rows)


def _photo_card(photo: dict[str, Any]) -> str:
    image = (
        f"<img src=\"{escape_html(photo.get('imagen_data_url'))}\" />"
        if photo.get("imagen_data_url")
        else '<div class="photo-empty">Sin imagen</div>'
    )
    return f"<figure>{image}<figcaption>{escape_html(photo.get('fecha_hora'))}<br>{escape_html(photo.get('descripcion'))}</figcaption></figure>"


_READING_COLUMNS = [
    "id",
    "colado_id",
    "sensor_id",
    "fecha_hora",
    "minuto_transcurrido",
    "temperatura_concreto_c",
    "temperatura_ambiente_c",
    "humedad_relativa_pct",
    "origen",
    "valido",
    "motivo_invalidez",
]

_EVENT_COLUMNS = [
    "id",
    "colado_id",
    "fecha_hora",
    "minuto_transcurrido",
    "velocidad_deslizamiento_cm_h",
    "decision_tomada",
    "resultado_fisico",
    "checklist_no_desmorona",
    "checklist_no_se_pega",
    "checklist_acabado_aceptable",
    "checklist_sin_arrastre",
    "observacion",
    "supervisor",
]


__all__ = ["handle_report_get", "render_colado_report", "render_control_report"]
