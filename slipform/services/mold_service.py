"""Use cases related to the moving mold and 30 cm zones."""

from slipform.mold import calculate_mold_state
from slipform.repositories import avances_repo, zonas_repo


class MoldService:
    def calculate_state(self, conn, colado_id: int, evaluation_time: str | None = None):
        return calculate_mold_state(conn, colado_id, as_of_iso=evaluation_time)

    def generate_initial_zones(self, conn, payload: dict):
        return zonas_repo.generate_initial_zones(conn, payload)

    def register_advance(self, conn, payload: dict):
        return avances_repo.insert_mold_advance(conn, payload)

    def list_zones(self, conn, colado_id: int):
        return zonas_repo.list_zones(conn, colado_id)

    def list_advances(self, conn, colado_id: int):
        return avances_repo.list_mold_advances(conn, colado_id)


__all__ = ["MoldService"]
