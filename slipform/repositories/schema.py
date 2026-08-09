"""SQLite schema creation and lightweight migrations."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from slipform.config import (
    DEFAULT_ADVANCE_CM,
    DEFAULT_ADVANCE_SPEED_CM_H,
)

SCHEMA_VERSION = 9
SCHEMA_DESCRIPTION = "preserve_active_advance_recipes"


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS auditoria_operativa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            accion TEXT NOT NULL,
            entidad TEXT NOT NULL,
            entidad_id INTEGER,
            colado_id INTEGER,
            operador TEXT,
            motivo TEXT,
            detalle_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mezclas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cemento TEXT,
            aditivo TEXT,
            dosificacion_hrp_cc REAL,
            relacion_agua_cemento REAL,
            observaciones TEXT,
            UNIQUE(nombre, dosificacion_hrp_cc)
        );

        CREATE TABLE IF NOT EXISTS curvas_laboratorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mezcla_id INTEGER NOT NULL REFERENCES mezclas(id),
            origen_archivo TEXT NOT NULL,
            nombre_curva TEXT NOT NULL,
            fecha_ensayo TEXT,
            madurez_objetivo_h_eq REAL NOT NULL,
            parametros_json TEXT NOT NULL,
            UNIQUE(origen_archivo, nombre_curva)
        );

        CREATE TABLE IF NOT EXISTS curvas_laboratorio_puntos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            curva_id INTEGER NOT NULL REFERENCES curvas_laboratorio(id) ON DELETE CASCADE,
            minuto REAL NOT NULL,
            temperatura_concreto_c REAL NOT NULL,
            madurez_arrhenius_h_eq REAL NOT NULL,
            UNIQUE(curva_id, minuto)
        );

        CREATE TABLE IF NOT EXISTS colados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE SET NULL,
            silo_id TEXT NOT NULL,
            mezcla_id INTEGER NOT NULL REFERENCES mezclas(id),
            curva_id INTEGER REFERENCES curvas_laboratorio(id),
            fecha_hora_inicio TEXT NOT NULL,
            hora_salida_planta TEXT,
            hora_llegada_obra TEXT,
            hora_inicio_descarga TEXT,
            hora_colocacion_en_molde TEXT,
            hora_fin_descarga TEXT,
            fecha_cierre TEXT,
            operador TEXT,
            estado TEXT NOT NULL DEFAULT 'ACTIVO',
            es_demo INTEGER NOT NULL DEFAULT 0,
            observaciones TEXT
        );

        CREATE TABLE IF NOT EXISTS sensores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            variable TEXT NOT NULL,
            ubicacion TEXT,
            silo_id TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            fecha_calibracion TEXT,
            observaciones TEXT
        );

        CREATE TABLE IF NOT EXISTS lecturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            sensor_id INTEGER REFERENCES sensores(id),
            fecha_hora TEXT NOT NULL,
            minuto_transcurrido REAL NOT NULL,
            temperatura_concreto_c REAL,
            temperatura_ambiente_c REAL,
            humedad_relativa_pct REAL,
            origen TEXT NOT NULL CHECK(origen IN ('manual', 'sensor', 'importacion', 'estimado')),
            valido INTEGER NOT NULL DEFAULT 1,
            motivo_invalidez TEXT
        );

        CREATE TABLE IF NOT EXISTS predicciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            fecha_hora TEXT NOT NULL,
            madurez_acumulada_h_eq REAL NOT NULL,
            avance REAL NOT NULL,
            estado TEXT NOT NULL,
            minutos_restantes REAL,
            desviacion_vs_laboratorio REAL,
            alertas_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS eventos_deslizamiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            fecha_hora TEXT NOT NULL,
            minuto_transcurrido REAL NOT NULL,
            velocidad_deslizamiento_cm_h REAL,
            decision_tomada TEXT NOT NULL,
            resultado_fisico TEXT NOT NULL,
            checklist_no_desmorona INTEGER NOT NULL DEFAULT 0,
            checklist_no_se_pega INTEGER NOT NULL DEFAULT 0,
            checklist_acabado_aceptable INTEGER NOT NULL DEFAULT 0,
            checklist_sin_arrastre INTEGER NOT NULL DEFAULT 0,
            observacion TEXT,
            supervisor TEXT
        );

        CREATE TABLE IF NOT EXISTS configuracion_molde (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            altura_molde_m REAL NOT NULL,
            altura_zona_m REAL NOT NULL,
            zonas_por_molde INTEGER NOT NULL,
            velocidad_objetivo_cm_h REAL NOT NULL,
            avance_objetivo_cm_5min REAL NOT NULL,
            residencia_minima_h REAL NOT NULL,
            residencia_preferente_h REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS descargas_olla (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            numero_olla TEXT NOT NULL,
            volumen_m3 REAL NOT NULL DEFAULT 5.0,
            hora_salida_planta TEXT,
            hora_llegada_obra TEXT,
            hora_inicio_descarga TEXT,
            hora_fin_descarga TEXT,
            temperatura_salida_c REAL,
            temperatura_llegada_c REAL,
            revenimiento_cm REAL,
            origen_generacion TEXT NOT NULL DEFAULT 'manual',
            estado_operativo TEXT NOT NULL DEFAULT 'CONFIRMADA_EN_MOLDE',
            observaciones TEXT
        );

        CREATE TABLE IF NOT EXISTS zonas_colado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            descarga_olla_id INTEGER REFERENCES descargas_olla(id) ON DELETE SET NULL,
            zona_numero INTEGER NOT NULL,
            elevacion_inferior_cm REAL NOT NULL,
            elevacion_superior_cm REAL NOT NULL,
            volumen_m3 REAL NOT NULL DEFAULT 5.0,
            hora_salida_planta TEXT,
            hora_inicio_llenado TEXT NOT NULL,
            hora_fin_llenado TEXT,
            hora_referencia_madurez TEXT NOT NULL,
            mezcla_id INTEGER REFERENCES mezclas(id),
            curva_id INTEGER REFERENCES curvas_laboratorio(id),
            temperatura_inicial_c REAL,
            origen_generacion TEXT NOT NULL DEFAULT 'manual',
            avance_generador_id INTEGER REFERENCES avances_molde(id) ON DELETE SET NULL,
            estado TEXT NOT NULL DEFAULT 'ZONA_EN_LLENADO'
        );

        CREATE TABLE IF NOT EXISTS avances_molde (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            receta_avance_id INTEGER,
            fecha_hora TEXT NOT NULL,
            minuto_transcurrido REAL NOT NULL,
            avance_cm REAL NOT NULL,
            avance_acumulado_cm REAL NOT NULL,
            velocidad_real_cm_h REAL,
            intervalo_minutos REAL,
            origen TEXT NOT NULL DEFAULT 'manual',
            observacion TEXT,
            operador TEXT
        );

        CREATE TABLE IF NOT EXISTS recetas_avance_colado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            fecha_hora TEXT NOT NULL,
            avance_objetivo_cm REAL NOT NULL,
            intervalo_objetivo_min REAL NOT NULL,
            velocidad_objetivo_cm_h REAL NOT NULL,
            tolerancia_velocidad_min_cm_h REAL NOT NULL,
            tolerancia_velocidad_max_cm_h REAL NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1,
            motivo TEXT,
            operador TEXT,
            supervisor TEXT
        );

        CREATE TABLE IF NOT EXISTS lecturas_zona (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zona_colado_id INTEGER NOT NULL REFERENCES zonas_colado(id) ON DELETE CASCADE,
            sensor_id INTEGER REFERENCES sensores(id),
            fecha_hora TEXT NOT NULL,
            minuto_desde_zona REAL NOT NULL,
            temperatura_concreto_c REAL,
            temperatura_ambiente_c REAL,
            humedad_relativa_pct REAL,
            origen TEXT NOT NULL CHECK(origen IN ('manual', 'sensor', 'importacion', 'estimado')),
            valido INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS alarmas_operativas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            zona_colado_id INTEGER REFERENCES zonas_colado(id) ON DELETE SET NULL,
            tipo TEXT NOT NULL,
            severidad TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'ACTIVA',
            fecha_hora_inicio TEXT NOT NULL,
            fecha_hora_reconocimiento TEXT,
            fecha_hora_cierre TEXT,
            operador_reconoce TEXT,
            mensaje TEXT NOT NULL,
            UNIQUE(colado_id, zona_colado_id, tipo, fecha_hora_inicio)
        );

        CREATE TABLE IF NOT EXISTS decisiones_operador (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            zona_colado_id INTEGER REFERENCES zonas_colado(id) ON DELETE SET NULL,
            avance_molde_id INTEGER REFERENCES avances_molde(id) ON DELETE SET NULL,
            fecha_hora TEXT NOT NULL,
            recomendacion_sistema TEXT NOT NULL,
            decision_operador TEXT NOT NULL,
            conforme_recomendacion INTEGER NOT NULL DEFAULT 1,
            requiere_supervisor INTEGER NOT NULL DEFAULT 0,
            operador TEXT,
            supervisor TEXT,
            checklist_json TEXT NOT NULL,
            observacion TEXT
        );

        CREATE TABLE IF NOT EXISTS liberaciones_campo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            zona_colado_id INTEGER NOT NULL REFERENCES zonas_colado(id) ON DELETE CASCADE,
            fecha_hora TEXT NOT NULL,
            madurez_calculada_pct REAL NOT NULL,
            madurez_operativa_pct REAL NOT NULL DEFAULT 90.0,
            temperatura_concreto_c REAL NOT NULL,
            temperatura_ambiente_c REAL,
            humedad_relativa_pct REAL,
            condicion_observada TEXT NOT NULL,
            checklist_json TEXT NOT NULL,
            motivo TEXT NOT NULL,
            operador TEXT,
            supervisor TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS ajustes_prediccion_campo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            zona_base_id INTEGER NOT NULL REFERENCES zonas_colado(id) ON DELETE CASCADE,
            fecha_hora TEXT NOT NULL,
            hora_salida_planta_zona_base TEXT NOT NULL,
            edad_observada_liberacion_h REAL NOT NULL,
            madurez_calculada_pct REAL NOT NULL,
            temperatura_concreto_c REAL,
            motivo TEXT,
            operador TEXT,
            supervisor TEXT,
            activo INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS ensayos_cilindro_deslizamiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            t_fabricacion TEXT NOT NULL,
            resultado_4h TEXT NOT NULL DEFAULT 'PENDIENTE',
            fecha_hora_4h TEXT,
            resultado_5h TEXT NOT NULL DEFAULT 'PENDIENTE',
            fecha_hora_5h TEXT,
            resultado_6h TEXT NOT NULL DEFAULT 'PENDIENTE',
            fecha_hora_6h TEXT,
            escenario_activo TEXT,
            estado TEXT NOT NULL DEFAULT 'ESPERANDO_ENSAYO',
            operador TEXT,
            supervisor TEXT,
            observaciones TEXT,
            updated_at TEXT NOT NULL,
            layer_thickness_cm REAL NOT NULL DEFAULT 30.0,
            total_layers INTEGER NOT NULL DEFAULT 7,
            start_zone INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS programas_deslizado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            ensayo_cilindro_id INTEGER REFERENCES ensayos_cilindro_deslizamiento(id) ON DELETE SET NULL,
            t_fabricacion TEXT NOT NULL,
            escenario TEXT NOT NULL,
            step_cm REAL NOT NULL,
            step_minutes REAL NOT NULL,
            layer_thickness_cm REAL NOT NULL,
            total_layers INTEGER NOT NULL,
            start_zone INTEGER NOT NULL DEFAULT 1,
            layer_interval_minutes REAL NOT NULL,
            speed_cm_min REAL NOT NULL,
            speed_cm_h REAL NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS programas_deslizado_capas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            programa_id INTEGER NOT NULL REFERENCES programas_deslizado(id) ON DELETE CASCADE,
            capa_numero INTEGER NOT NULL,
            zona_numero INTEGER NOT NULL,
            hora_programada TEXT NOT NULL,
            offset_min REAL NOT NULL,
            estado TEXT NOT NULL DEFAULT 'PROGRAMADA',
            UNIQUE(programa_id, capa_numero)
        );

        CREATE TABLE IF NOT EXISTS turnos_operacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            operador TEXT NOT NULL,
            inicio_turno TEXT NOT NULL,
            fin_turno TEXT
        );

        CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            cliente TEXT,
            obra TEXT,
            ubicacion TEXT,
            elemento TEXT,
            contratista TEXT,
            supervisor TEXT,
            logo_izquierdo TEXT,
            logo_derecho TEXT,
            altura_objetivo_m REAL,
            nivel_inicial_m REAL,
            nivel_final_m REAL,
            volumen_estimado_m3 REAL,
            area_cimbra_m2 REAL,
            fecha_inicio_programada TEXT,
            fecha_fin_programada TEXT,
            activo INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS turnos_operacion_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            turno TEXT NOT NULL,
            operador TEXT,
            inicio_turno TEXT NOT NULL,
            fin_turno TEXT,
            nivel_fin_turno_m REAL,
            avance_parcial_m REAL,
            avance_acumulado_m REAL,
            ritmo_cm_h REAL,
            observaciones TEXT
        );

        CREATE TABLE IF NOT EXISTS fotografias_evidencia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            zona_colado_id INTEGER REFERENCES zonas_colado(id) ON DELETE SET NULL,
            fecha_hora TEXT NOT NULL,
            elevacion_cm REAL,
            descripcion TEXT,
            operador TEXT,
            imagen_data_url TEXT
        );

        CREATE TABLE IF NOT EXISTS lecturas_desplome (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            fecha_hora TEXT NOT NULL,
            punto TEXT NOT NULL,
            direccion TEXT NOT NULL,
            lectura_mm REAL NOT NULL,
            tolerancia_mm REAL,
            estado TEXT NOT NULL,
            operador TEXT,
            observaciones TEXT
        );

        CREATE TABLE IF NOT EXISTS ajustes_modelo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mezcla_id INTEGER REFERENCES mezclas(id) ON DELETE SET NULL,
            colado_id INTEGER REFERENCES colados(id) ON DELETE CASCADE,
            fecha_hora TEXT NOT NULL,
            madurez_objetivo_h_eq REAL,
            umbral_prepararse REAL,
            umbral_deslizar REAL,
            umbral_sobremadurez REAL,
            tolerancia_velocidad_min_cm_h REAL,
            tolerancia_velocidad_max_cm_h REAL,
            operador TEXT,
            supervisor TEXT,
            justificacion TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reportes_generados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
            tipo TEXT NOT NULL,
            fecha_hora TEXT NOT NULL,
            resumen_json TEXT NOT NULL
        );
        """
    )
    _ensure_column(conn, "colados", "proyecto_id", "INTEGER REFERENCES proyectos(id) ON DELETE SET NULL")
    _ensure_column(conn, "colados", "hora_salida_planta", "TEXT")
    _ensure_column(conn, "colados", "hora_llegada_obra", "TEXT")
    _ensure_column(conn, "colados", "hora_inicio_descarga", "TEXT")
    _ensure_column(conn, "colados", "hora_colocacion_en_molde", "TEXT")
    _ensure_column(conn, "colados", "hora_fin_descarga", "TEXT")
    _ensure_column(conn, "colados", "fecha_cierre", "TEXT")
    _ensure_column(conn, "colados", "es_demo", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "eventos_deslizamiento", "checklist_no_desmorona", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "eventos_deslizamiento", "checklist_no_se_pega", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "eventos_deslizamiento", "checklist_acabado_aceptable", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "eventos_deslizamiento", "checklist_sin_arrastre", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "descargas_olla", "volumen_m3", "REAL NOT NULL DEFAULT 5.0")
    _ensure_column(conn, "descargas_olla", "temperatura_salida_c", "REAL")
    _ensure_column(conn, "descargas_olla", "origen_generacion", "TEXT NOT NULL DEFAULT 'manual'")
    _ensure_column(conn, "descargas_olla", "estado_operativo", "TEXT NOT NULL DEFAULT 'CONFIRMADA_EN_MOLDE'")
    _ensure_column(conn, "zonas_colado", "volumen_m3", "REAL NOT NULL DEFAULT 5.0")
    _ensure_column(conn, "zonas_colado", "hora_salida_planta", "TEXT")
    _ensure_column(conn, "zonas_colado", "temperatura_inicial_c", "REAL")
    _ensure_column(conn, "zonas_colado", "origen_generacion", "TEXT NOT NULL DEFAULT 'manual'")
    _ensure_column(conn, "zonas_colado", "avance_generador_id", "INTEGER REFERENCES avances_molde(id) ON DELETE SET NULL")
    _ensure_column(conn, "avances_molde", "receta_avance_id", "INTEGER")
    _ensure_column(conn, "avances_molde", "intervalo_minutos", "REAL")
    _ensure_column(conn, "decisiones_operador", "conforme_recomendacion", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "liberaciones_campo", "activo", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "ajustes_prediccion_campo", "activo", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "ensayos_cilindro_deslizamiento", "layer_thickness_cm", "REAL NOT NULL DEFAULT 30.0")
    _ensure_column(conn, "ensayos_cilindro_deslizamiento", "total_layers", "INTEGER NOT NULL DEFAULT 7")
    _ensure_column(conn, "ensayos_cilindro_deslizamiento", "start_zone", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "programas_deslizado", "start_zone", "INTEGER NOT NULL DEFAULT 1")
    _ensure_origin_estimado_supported(conn, "lecturas")
    _ensure_origin_estimado_supported(conn, "lecturas_zona")
    conn.execute(
        """
        UPDATE zonas_colado
        SET hora_salida_planta = hora_referencia_madurez
        WHERE hora_salida_planta IS NULL OR hora_salida_planta = ''
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO configuracion_molde(
            nombre, altura_molde_m, altura_zona_m, zonas_por_molde,
            velocidad_objetivo_cm_h, avance_objetivo_cm_5min,
            residencia_minima_h, residencia_preferente_h
        )
        VALUES ('Default 1.20m', 1.20, 0.30, 4, 30, 3.0, 4.0, 4.5)
        """
    )
    conn.execute(
        """
        UPDATE configuracion_molde
        SET velocidad_objetivo_cm_h = ?, avance_objetivo_cm_5min = ?
        WHERE nombre = 'Default 1.20m'
        """,
        (DEFAULT_ADVANCE_SPEED_CM_H, DEFAULT_ADVANCE_CM),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO proyectos(nombre, cliente, obra, ubicacion, elemento, activo)
        VALUES ('Seybaplaya', 'Cliente pendiente', 'Silos de concreto', 'Seybaplaya, Campeche', 'Silo', 1)
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, applied_at, description)
        VALUES (?, ?, ?)
        """,
        (SCHEMA_VERSION, datetime.now().isoformat(timespec="seconds"), SCHEMA_DESCRIPTION),
    )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _ensure_origin_estimado_supported(conn: sqlite3.Connection, table: str) -> None:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    if not row or "estimado" in str(row["sql"]):
        return
    suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    old_table = f"{table}_old_origin_{suffix}"
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(f"ALTER TABLE {table} RENAME TO {old_table}")
    if table == "lecturas":
        conn.execute(
            """
            CREATE TABLE lecturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                colado_id INTEGER NOT NULL REFERENCES colados(id) ON DELETE CASCADE,
                sensor_id INTEGER REFERENCES sensores(id),
                fecha_hora TEXT NOT NULL,
                minuto_transcurrido REAL NOT NULL,
                temperatura_concreto_c REAL,
                temperatura_ambiente_c REAL,
                humedad_relativa_pct REAL,
                origen TEXT NOT NULL CHECK(origen IN ('manual', 'sensor', 'importacion', 'estimado')),
                valido INTEGER NOT NULL DEFAULT 1,
                motivo_invalidez TEXT
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO lecturas(
                id, colado_id, sensor_id, fecha_hora, minuto_transcurrido,
                temperatura_concreto_c, temperatura_ambiente_c, humedad_relativa_pct,
                origen, valido, motivo_invalidez
            )
            SELECT id, colado_id, sensor_id, fecha_hora, minuto_transcurrido,
                temperatura_concreto_c, temperatura_ambiente_c, humedad_relativa_pct,
                origen, valido, motivo_invalidez
            FROM {old_table}
            """
        )
    elif table == "lecturas_zona":
        conn.execute(
            """
            CREATE TABLE lecturas_zona (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zona_colado_id INTEGER NOT NULL REFERENCES zonas_colado(id) ON DELETE CASCADE,
                sensor_id INTEGER REFERENCES sensores(id),
                fecha_hora TEXT NOT NULL,
                minuto_desde_zona REAL NOT NULL,
                temperatura_concreto_c REAL,
                temperatura_ambiente_c REAL,
                humedad_relativa_pct REAL,
                origen TEXT NOT NULL CHECK(origen IN ('manual', 'sensor', 'importacion', 'estimado')),
                valido INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO lecturas_zona(
                id, zona_colado_id, sensor_id, fecha_hora, minuto_desde_zona,
                temperatura_concreto_c, temperatura_ambiente_c, humedad_relativa_pct,
                origen, valido
            )
            SELECT id, zona_colado_id, sensor_id, fecha_hora, minuto_desde_zona,
                temperatura_concreto_c, temperatura_ambiente_c, humedad_relativa_pct,
                origen, valido
            FROM {old_table}
            """
        )
    conn.execute(f"DROP TABLE {old_table}")
    conn.execute("PRAGMA foreign_keys = ON")


__all__ = ["SCHEMA_DESCRIPTION", "SCHEMA_VERSION", "init_db"]
