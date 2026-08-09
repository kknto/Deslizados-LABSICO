from __future__ import annotations

import unittest

from slipform.core import arrhenius_factor, calculate_maturity, calculate_state


class CoreTests(unittest.TestCase):
    def test_arrhenius_factor_is_one_at_reference_temperature(self) -> None:
        self.assertAlmostEqual(arrhenius_factor(23.0), 1.0, places=6)

    def test_maturity_uses_first_elapsed_interval_like_excel_template(self) -> None:
        maturity, points = calculate_maturity(
            [{"minuto_transcurrido": 60, "temperatura_concreto_c": 23}]
        )
        self.assertAlmostEqual(maturity, 1.0, places=6)
        self.assertAlmostEqual(points[-1]["madurez_arrhenius_h_eq"], 1.0, places=6)

    def test_state_reaches_slide_threshold(self) -> None:
        result = calculate_state(
            [{"minuto_transcurrido": 480, "temperatura_concreto_c": 23}]
        )
        self.assertEqual(result["estado"], "DESLIZAR")

    def test_invalid_sensor_blocks_slide(self) -> None:
        result = calculate_state(
            [{"minuto_transcurrido": 480, "temperatura_concreto_c": 95}]
        )
        self.assertEqual(result["estado"], "SENSOR_INVALIDO")

    def test_duplicate_minutes_block_recommendation_without_crashing(self) -> None:
        result = calculate_state(
            [
                {"minuto_transcurrido": 60, "temperatura_concreto_c": 23},
                {"minuto_transcurrido": 60, "temperatura_concreto_c": 24},
            ]
        )
        self.assertEqual(result["estado"], "SENSOR_INVALIDO")
        self.assertIn("Lecturas duplicadas o con minutos no crecientes.", result["alertas"])
        self.assertGreater(result["madurez_acumulada_h_eq"], 0)


if __name__ == "__main__":
    unittest.main()
