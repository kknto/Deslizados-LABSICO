from __future__ import annotations

import unittest

from slipform.reports.rendering import escape_html, svg_line_chart


class ReportRenderingTests(unittest.TestCase):
    def test_escape_html(self) -> None:
        self.assertEqual(escape_html("<A&B>"), "&lt;A&amp;B&gt;")

    def test_svg_line_chart_empty_and_with_points(self) -> None:
        self.assertIn("Sin datos", svg_line_chart([], "x", "y"))
        chart = svg_line_chart([{"x": 0, "y": 0}, {"x": 10, "y": 5}], "x", "y", expected_speed=30)
        self.assertIn("<svg", chart)
        self.assertIn("polyline", chart)

    def test_svg_line_chart_normalizes_negative_minutes(self) -> None:
        chart = svg_line_chart([{"x": -4107, "y": 3}, {"x": -4093, "y": 6}], "x", "y", expected_speed=30)

        self.assertIn("<svg", chart)
        self.assertIn("stroke='#155e75'", chart)
        self.assertIn("Duracion 60 min", chart)
        self.assertNotIn("points='-0", chart)


if __name__ == "__main__":
    unittest.main()
