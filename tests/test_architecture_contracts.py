from __future__ import annotations

import sqlite3
import unittest

from slipform.domain.models import AvanceMolde, Colado, EstadoMolde, ZonaColado
from slipform.http.routes import GET_ROUTES, POST_ROUTES, ROUTE_GROUPS
from slipform.repositories import colados_repo, schema


class ArchitectureContractTests(unittest.TestCase):
    def test_route_registry_contains_operational_endpoints(self) -> None:
        for route in (
            "/api/bootstrap",
            "/api/health",
            "/api/schema/version",
            "/api/backups",
            "/api/auditoria",
            "/api/calidad-datos",
            "/api/molde/estado",
            "/api/scada/estado",
            "/api/tendencias",
            "/api/programa-deslizado",
            "/api/report/control-central.html",
            "/api/export/bitacora.csv",
        ):
            self.assertIn(route, GET_ROUTES)

        for route in (
            "/api/colados",
            "/api/colados/inicializar-arranque",
            "/api/ollas/registrar-zona",
            "/api/zonas/generar",
            "/api/avances/registrar-5min",
            "/api/scada/confirmar-avance",
            "/api/sensores/ingesta",
            "/api/demo/reset",
            "/api/backups",
            "/api/programa-deslizado/ensayo",
            "/api/bitacora-escrita/plantillas",
            "/api/bitacora-escrita/preview",
            "/api/bitacora-escrita/ocr-preview",
            "/api/bitacora-escrita/importar",
        ):
            self.assertIn(route, POST_ROUTES)

        self.assertEqual(set(ROUTE_GROUPS), {"GET", "POST", "PUT", "DELETE"})

    def test_domain_models_are_instantiable_contracts(self) -> None:
        colado = Colado(id=1, silo_id="S1", mezcla_id=1, fecha_hora_inicio="2026-07-24T09:00")
        zona = ZonaColado(
            id=1,
            colado_id=1,
            zona_numero=1,
            elevacion_inferior_cm=0,
            elevacion_superior_cm=30,
            hora_inicio_llenado="2026-07-24T09:00",
            hora_fin_llenado="2026-07-24T10:00",
            hora_referencia_madurez="2026-07-24T09:00",
        )
        avance = AvanceMolde(
            id=1,
            colado_id=1,
            fecha_hora="2026-07-24T10:00",
            avance_cm=2.5,
            avance_acumulado_cm=2.5,
        )
        estado = EstadoMolde(colado_id=1, estado_operativo="PREPARARSE", avance_acumulado_cm=2.5)

        self.assertEqual(colado.estado, "Activo")
        self.assertEqual(zona.estado, "ZONA_EN_LLENADO")
        self.assertEqual(avance.origen, "manual")
        self.assertEqual(estado.alertas, [])

    def test_repository_facade_preserves_colado_flow(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        schema.init_db(conn)
        conn.execute("INSERT INTO mezclas(id, nombre) VALUES (1, 'M1')")

        colado_id = colados_repo.upsert_colado(
            conn,
            {
                "silo_id": "S1",
                "mezcla_id": 1,
                "hora_colocacion_en_molde": "2026-07-24T09:00",
                "operador": "Operador",
            },
        )

        saved = colados_repo.get_colado(conn, colado_id)
        listed = colados_repo.list_colados(conn)

        self.assertEqual(saved["silo_id"], "S1")
        self.assertTrue(any(row["id"] == colado_id for row in listed))


if __name__ == "__main__":
    unittest.main()
