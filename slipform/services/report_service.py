"""Report service facade."""


class ReportService:
    def build_control_central_context(self, colado_id: int):
        from slipform.server import _control_report_context

        return _control_report_context(colado_id)

    def render_control_central_html(self, context: dict):
        from slipform.server import _render_control_report

        return _render_control_report(context)


__all__ = ["ReportService"]
