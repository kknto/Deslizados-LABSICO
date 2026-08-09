from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from .config import DEFAULT_PARAMS
from .core import calculate_maturity
from .db import connect, init_db, insert_curve, upsert_mezcla
from .xlsx_reader import normalize_temperature_curves


def import_curves(xlsx_path: str | Path, db_path: str | Path = "data/slipform.sqlite") -> int:
    conn = connect(db_path)
    init_db(conn)
    imported = 0
    for curve in normalize_temperature_curves(xlsx_path):
        readings = [
            {
                "minuto_transcurrido": point["minuto"],
                "temperatura_concreto_c": point["temperatura_concreto_c"],
            }
            for point in curve["points"]
        ]
        _, maturity_points = calculate_maturity(readings, DEFAULT_PARAMS)
        points = [
            {
                "minuto": point["minuto"],
                "temperatura_concreto_c": point["temperatura_concreto_c"],
                "madurez_arrhenius_h_eq": point["madurez_arrhenius_h_eq"],
            }
            for point in maturity_points
        ]
        dose = _parse_dose(curve["nombre_curva"])
        mezcla_id = upsert_mezcla(conn, curve["nombre_curva"], dose)
        insert_curve(
            conn,
            mezcla_id,
            Path(xlsx_path).name,
            f"{curve['sheet_name']} - {curve['nombre_curva']}",
            points,
            DEFAULT_PARAMS,
        )
        imported += 1
    conn.close()
    return imported


def export_curve_report(
    db_path: str | Path = "data/slipform.sqlite",
    output_path: str | Path = "reports/resumen_curvas.csv",
) -> Path:
    conn = connect(db_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT
            cl.id,
            cl.nombre_curva,
            COUNT(p.id) AS puntos,
            MIN(p.temperatura_concreto_c) AS temp_min_c,
            MAX(p.temperatura_concreto_c) AS temp_max_c,
            MAX(p.madurez_arrhenius_h_eq) AS madurez_final_h_eq
        FROM curvas_laboratorio cl
        JOIN curvas_laboratorio_puntos p ON p.curva_id = cl.id
        GROUP BY cl.id, cl.nombre_curva
        ORDER BY cl.nombre_curva
        """
    ).fetchall()
    with Path(output_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "curva_id",
                "nombre_curva",
                "puntos",
                "temp_min_c",
                "temp_max_c",
                "madurez_final_h_eq",
            ]
        )
        for row in rows:
            writer.writerow([row[key] for key in row.keys()])
    conn.close()
    return Path(output_path)


def _parse_dose(name: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*cc", name, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa curvas HRP a SQLite.")
    parser.add_argument("--xlsx", default="Curvas HRP.xlsx")
    parser.add_argument("--db", default="data/slipform.sqlite")
    parser.add_argument("--report", default="reports/resumen_curvas.csv")
    args = parser.parse_args()
    count = import_curves(args.xlsx, args.db)
    report = export_curve_report(args.db, args.report)
    print(f"Curvas importadas: {count}")
    print(f"Base SQLite: {args.db}")
    print(f"Reporte: {report}")


if __name__ == "__main__":
    main()

