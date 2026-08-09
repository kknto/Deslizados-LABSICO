from __future__ import annotations

import unittest

from slipform.domain.validation import (
    normalize_datetime,
    optional_float,
    parse_datetime,
    validate_advance_values,
    validate_colado_payload,
    validate_measurements,
    validate_origin,
)


class DomainValidationTests(unittest.TestCase):
    def test_optional_float_and_datetime(self) -> None:
        self.assertIsNone(optional_float(""))
        self.assertEqual(optional_float("2.5"), 2.5)
        self.assertEqual(parse_datetime("2026-07-24T09:00").hour, 9)

    def test_utc_datetime_is_converted_to_cancun_local_time(self) -> None:
        parsed = parse_datetime("2026-07-28T13:34:37Z")

        self.assertEqual(parsed.isoformat(timespec="seconds"), "2026-07-28T08:34:37")
        self.assertEqual(normalize_datetime("2026-07-28T13:34:37Z"), "2026-07-28T08:34:37")

    def test_colado_dates_must_be_ordered(self) -> None:
        with self.assertRaises(ValueError):
            validate_colado_payload(
                {
                    "silo_id": "S1",
                    "mezcla_id": 1,
                    "hora_salida_planta": "2026-07-24T10:00",
                    "hora_llegada_obra": "2026-07-24T09:00",
                }
            )

    def test_reading_origin_and_ranges(self) -> None:
        validate_origin("estimado")
        with self.assertRaises(ValueError):
            validate_origin("externo")
        with self.assertRaises(ValueError):
            validate_measurements({"humedad_relativa_pct": 101})

    def test_advance_values_positive(self) -> None:
        validate_advance_values({"avance_cm": "2.5", "intervalo_minutos": "5"})
        with self.assertRaises(ValueError):
            validate_advance_values({"avance_cm": "-1"})


if __name__ == "__main__":
    unittest.main()
