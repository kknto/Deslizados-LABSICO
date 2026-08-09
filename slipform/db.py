"""Compatible database facade over modular repositories."""

from slipform.repositories.connection import connect  # noqa: F401
from slipform.repositories.schema import init_db  # noqa: F401
from slipform.repositories.colados_repo import (  # noqa: F401
    create_colado,
    delete_colado,
    get_colado,
    update_colado,
)
from slipform.repositories.lecturas_repo import (  # noqa: F401
    get_readings,
    insert_reading,
)
from slipform.repositories.avances_repo import (  # noqa: F401
    get_active_advance_recipe,
    get_advances,
    insert_mold_advance,
    latest_advance_cm,
    list_advance_recipes,
    upsert_advance_recipe,
)
from slipform.repositories.zonas_repo import (  # noqa: F401
    create_zone,
    ensure_continuous_zones,
    generate_zones,
    get_zone,
    get_zone_readings,
    get_zones,
    get_zones_generated_by_advance,
    initialize_colado_start_offset,
    invalidate_zone_reading,
    insert_zone_reading,
    list_zone_readings,
    register_truck_zone,
)
from slipform.repositories.evidencia_repo import (  # noqa: F401
    insert_photo_evidence,
    insert_plumb_reading,
    list_photo_evidence,
    list_plumb_readings,
)
from slipform.repositories.scada_repo import (  # noqa: F401
    acknowledge_operational_alarm,
    close_shift_detail,
    close_stale_operational_alarms,
    insert_field_release,
    insert_operator_decision,
    insert_shift,
    insert_shift_detail,
    latest_active_field_release,
    latest_field_prediction_adjustment,
    list_field_prediction_adjustments,
    list_field_releases,
    list_operational_alarms,
    list_operator_decisions,
    list_shift_details,
    upsert_field_prediction_adjustment,
    upsert_operational_alarm,
)
from slipform.repositories.audit_repo import (  # noqa: F401
    database_counts,
    delete_demo_data,
    get_schema_version,
    insert_audit,
    list_audit,
)
from slipform.repositories.project_repo import (  # noqa: F401
    get_active_project,
    upsert_project,
)
from slipform.repositories.mold_config_repo import (  # noqa: F401
    default_advance_recipe,
    get_mold_config,
    upsert_mold_config,
)
from slipform.repositories.descargas_repo import (  # noqa: F401
    create_descarga,
    get_descargas,
    update_descarga,
)
from slipform.repositories.calibration_repo import (  # noqa: F401
    insert_generated_report,
    insert_model_adjustment,
    list_model_adjustments,
)
from slipform.repositories.sensor_repo import get_sensor_health  # noqa: F401
from slipform.repositories.catalog_repo import (  # noqa: F401
    get_reference_points,
    insert_curve,
    list_bootstrap,
    list_sensor_status,
    upsert_mezcla,
)
from slipform.repositories.events_repo import (  # noqa: F401
    get_events,
    insert_prediction,
    insert_slide_event,
)
from slipform.repositories.simulation_repo import (  # noqa: F401
    simulate_curve_readings,
    simulate_operational_advances,
)
from slipform.repositories.schedule_repo import (  # noqa: F401
    get_cylinder_test_schedule,
    save_cylinder_test_schedule,
)
