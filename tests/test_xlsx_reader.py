from __future__ import annotations

import unittest
from pathlib import Path

from slipform.xlsx_reader import normalize_temperature_curves


class XlsxReaderTests(unittest.TestCase):
    def test_reads_available_hrp_curves(self) -> None:
        path = Path("Curvas HRP.xlsx")
        if not path.exists():
            self.skipTest("Curvas HRP.xlsx no está disponible")
        curves = normalize_temperature_curves(path)
        self.assertGreaterEqual(len(curves), 10)
        self.assertIn("nombre_curva", curves[0])
        self.assertGreaterEqual(len(curves[0]["points"]), 10)


if __name__ == "__main__":
    unittest.main()

