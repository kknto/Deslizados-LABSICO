"""Use cases related to photographs and desplome readings."""

from slipform.repositories import evidencia_repo


class EvidenceService:
    def add_photo(self, conn, payload: dict):
        return evidencia_repo.insert_photo_evidence(conn, payload)

    def list_photos(self, conn, colado_id: int):
        return evidencia_repo.list_photo_evidence(conn, colado_id)

    def add_desplome(self, conn, payload: dict):
        return evidencia_repo.insert_desplome(conn, payload)

    def list_desplomes(self, conn, colado_id: int):
        return evidencia_repo.list_desplomes(conn, colado_id)


__all__ = ["EvidenceService"]
