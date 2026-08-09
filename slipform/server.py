"""Compatible server entrypoint.

The implementation lives in slipform.http.legacy_server while routes are
gradually extracted into the modular HTTP layer.
"""

from slipform.http.legacy_server import SlipformHandler, run
from slipform.reports.control_central import build_control_report_context as _control_report_context
from slipform.http.report_handlers import (
    render_colado_report as _render_report,
    render_control_report as _render_control_report,
)

__all__ = [
    "SlipformHandler",
    "_control_report_context",
    "_render_control_report",
    "_render_report",
    "run",
]


if __name__ == "__main__":
    run()
