from __future__ import annotations

import unittest

from slipform.reports.csv_export import rows_to_csv


class CsvExportTests(unittest.TestCase):
    def test_rows_to_csv_uses_explicit_field_order(self) -> None:
        csv_text = rows_to_csv(
            [{"b": 2, "a": 1, "ignored": 3}],
            ["a", "b"],
        )
        self.assertEqual(csv_text.splitlines()[0], "a,b")
        self.assertEqual(csv_text.splitlines()[1], "1,2")

    def test_rows_to_csv_empty_without_fieldnames(self) -> None:
        self.assertEqual(rows_to_csv([]), "")

    def test_rows_to_csv_empty_with_fieldnames_keeps_header(self) -> None:
        self.assertEqual(rows_to_csv([], ["id", "name"]).strip(), "id,name")


if __name__ == "__main__":
    unittest.main()
