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

    def test_svg_line_chart_renders_axis_ticks_legend_and_datetime_labels(self) -> None:
        chart = svg_line_chart(
            [
                {"minuto": 0, "avance": 0, "fecha_hora": "2026-08-04T19:35"},
                {"minuto": 720, "avance": 220, "fecha_hora": "2026-08-05T07:35"},
                {"minuto": 1440, "avance": 510, "fecha_hora": "2026-08-05T19:35"},
                {"minuto": 2810, "avance": 783, "fecha_hora": "2026-08-07T18:25"},
            ],
            "minuto",
            "avance",
            expected_speed=30,
            x_label_key="fecha_hora",
            x_axis_title="Fecha / hora",
            y_axis_title="Avance acumulado (cm)",
            y_tick_step=100,
            legend=True,
        )

        self.assertIn("Avance acumulado (cm)", chart)
        self.assertIn("Fecha / hora", chart)
        self.assertIn("Avance real", chart)
        self.assertIn("Avance esperado", chart)
        self.assertIn("100 cm", chart)
        self.assertIn("200 cm", chart)
        self.assertIn("300 cm", chart)
        self.assertIn("04-ago 19:35", chart)
        self.assertIn("07-ago 18:25", chart)
        self.assertNotEqual(chart.count("min</text>"), 2)


if __name__ == "__main__":
    unittest.main()
