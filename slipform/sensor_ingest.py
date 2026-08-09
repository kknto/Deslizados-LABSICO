from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .db import connect, init_db, insert_reading


def ingest_csv(path: str | Path, db_path: str | Path = "data/slipform.sqlite") -> int:
    conn = connect(db_path)
    init_db(conn)
    count = 0
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            payload = {
                "colado_id": row["colado_id"],
                "sensor_id": row.get("sensor_id"),
                "fecha_hora": row.get("fecha_hora"),
                "minuto_transcurrido": row["minuto_transcurrido"],
                "temperatura_concreto_c": row.get("temperatura_concreto_c"),
                "temperatura_ambiente_c": row.get("temperatura_ambiente_c"),
                "humedad_relativa_pct": row.get("humedad_relativa_pct"),
                "origen": row.get("origen") or "sensor",
            }
            insert_reading(conn, payload)
            count += 1
    conn.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta lecturas de sensores desde CSV.")
    parser.add_argument("csv_path")
    parser.add_argument("--db", default="data/slipform.sqlite")
    args = parser.parse_args()
    count = ingest_csv(args.csv_path, args.db)
    print(f"Lecturas importadas: {count}")


if __name__ == "__main__":
    main()

