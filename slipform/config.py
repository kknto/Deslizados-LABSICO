from __future__ import annotations

DEFAULT_PARAMS = {
    "t_ref_c": 23.0,
    "activation_energy_j_mol": 40000.0,
    "gas_constant_j_mol_k": 8.314,
    "target_maturity_h_eq": 7.976855441542278,
    "prepare_threshold": 0.70,
    "slide_threshold": 0.90,
    "over_maturity_threshold": 1.05,
    "critical_maturity_threshold": 1.15,
    "max_sensor_gap_minutes": 10.0,
    "min_concrete_temp_c": 0.0,
    "max_concrete_temp_c": 85.0,
    "min_ambient_temp_c": -10.0,
    "max_ambient_temp_c": 60.0,
}

DEFAULT_ADVANCE_CM = 3.0
DEFAULT_ADVANCE_INTERVAL_MIN = 6.0
DEFAULT_ADVANCE_SPEED_CM_H = DEFAULT_ADVANCE_CM / (DEFAULT_ADVANCE_INTERVAL_MIN / 60.0)
DEFAULT_ADVANCE_TOLERANCE_CM_H = 5.0
