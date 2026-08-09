from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from slipform.cloud_init import initialize_database
from slipform.http.legacy_server import resolve_runtime_config
from slipform.repositories.connection import connect

ROOT = Path(__file__).resolve().parents[1]


class CloudDeployTests(unittest.TestCase):
    def test_cloud_init_creates_clean_sqlite_without_curves_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "slipform.sqlite"
            missing_curves = Path(tmp) / "Curvas HRP.xlsx"

            result = initialize_database(db_path, missing_curves)

            self.assertEqual(result["imported_curves"], 0)
            self.assertEqual(result["curve_count"], 0)
            self.assertGreaterEqual(result["project_count"], 1)
            with connect(db_path) as conn:
                tables = {
                    row["name"]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                self.assertIn("colados", tables)
                self.assertIn("proyectos", tables)

    def test_runtime_config_uses_render_port_and_host_env(self) -> None:
        old_host = os.environ.get("SLIPFORM_HOST")
        old_port = os.environ.get("PORT")
        try:
            os.environ["SLIPFORM_HOST"] = "0.0.0.0"
            os.environ["PORT"] = "10000"

            host, port = resolve_runtime_config()

            self.assertEqual(host, "0.0.0.0")
            self.assertEqual(port, 10000)
        finally:
            if old_host is None:
                os.environ.pop("SLIPFORM_HOST", None)
            else:
                os.environ["SLIPFORM_HOST"] = old_host
            if old_port is None:
                os.environ.pop("PORT", None)
            else:
                os.environ["PORT"] = old_port

    def test_render_blueprint_contract(self) -> None:
        text = (ROOT / "render.yaml").read_text(encoding="utf-8")

        self.assertIn("runtime: python", text)
        self.assertNotIn("preDeployCommand", text)
        self.assertIn("startCommand: python -m slipform.server", text)
        self.assertIn("healthCheckPath: /api/health", text)
        self.assertIn("SLIPFORM_DB_PATH", text)
        self.assertIn("mountPath: /var/data", text)


if __name__ == "__main__":
    unittest.main()
