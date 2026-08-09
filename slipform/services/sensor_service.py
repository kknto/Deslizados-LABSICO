"""Use cases related to sensors and automatic ingestion."""

from slipform.db import get_sensor_health, insert_reading


class SensorService:
    def ingest_reading(self, conn, payload: dict):
        payload = {**payload, "origen": payload.get("origen") or "sensor"}
        return insert_reading(conn, payload)

    def get_health(self, conn, colado_id: int | None = None):
        return get_sensor_health(conn, colado_id=colado_id)


__all__ = ["SensorService"]
