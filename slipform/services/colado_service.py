"""Use cases related to colados."""

from slipform.repositories import colados_repo


class ColadoService:
    def list_colados(self, conn):
        return colados_repo.list_colados(conn)

    def get_colado(self, conn, colado_id: int):
        return colados_repo.get_colado(conn, colado_id)

    def save_colado(self, conn, payload: dict):
        return colados_repo.upsert_colado(conn, payload)

    def update_colado(self, conn, colado_id: int, payload: dict):
        return colados_repo.update_colado(conn, colado_id, payload)

    def delete_colado(self, conn, colado_id: int):
        return colados_repo.delete_colado(conn, colado_id)


__all__ = ["ColadoService"]
