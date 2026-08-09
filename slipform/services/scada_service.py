"""Use cases related to SCADA state, alarms and operator decisions."""

from slipform.scada import confirm_scada_advance, get_scada_state
from slipform.repositories import scada_repo


class ScadaService:
    def get_state(self, conn, colado_id: int, evaluation_time: str | None = None):
        return get_scada_state(conn, colado_id, as_of_iso=evaluation_time)

    def confirm_advance(self, conn, payload: dict):
        return confirm_scada_advance(conn, payload)

    def list_alarms(self, conn, colado_id: int):
        return scada_repo.list_alarms(conn, colado_id)

    def acknowledge_alarm(self, conn, payload: dict):
        return scada_repo.acknowledge_alarm(conn, payload)

    def list_decisions(self, conn, colado_id: int):
        return scada_repo.list_decisions(conn, colado_id)


__all__ = ["ScadaService"]
