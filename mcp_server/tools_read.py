from __future__ import annotations

import re
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from .api_client import ApiClient, worker_path
from .auth import current_worker_id
from .schemas import READ_TOOL_SCHEMAS


_FORM_TYPES = {"AL", "EL", "MC", "KPI", "EXP", "OT", "UNPAID", "OTHER"}


def _worker_id(ctx: Context) -> str:
    worker_id = current_worker_id()
    if not worker_id:
        request = ctx.request_context.request
        worker_id = getattr(getattr(request, "state", None), "worker_id", None)
    if not worker_id:
        raise RuntimeError("Authenticated worker context is missing.")
    return worker_id


def _set_schema(mcp: FastMCP, tool_name: str) -> None:
    # FastMCP derives schemas from Python signatures; replace only the public
    # input schema so the wire contract stays exact while SDK validation remains active.
    tool = mcp._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover - registration failure is not expected
        raise RuntimeError(f"Could not register MCP tool {tool_name}.")
    tool.parameters = READ_TOOL_SCHEMAS[tool_name]


def register_read_tools(mcp: FastMCP, api: ApiClient) -> None:
    @mcp.tool(
        name="get_leave_balance",
        description=(
            "Get the authenticated worker's current annual-leave balance: total "
            "entitlement, days already taken, and days remaining. Use this before applying leave."
        ),
        structured_output=True,
    )
    def get_leave_balance(ctx: Context) -> dict[str, Any]:
        worker_id = _worker_id(ctx)
        worker = api.get(worker_id, worker_path(worker_id)).get("worker", {})
        return {
            "workerId": worker.get("workerId"),
            "entitlement": worker.get("annualLeaveEntitlement"),
            "taken": worker.get("annualLeaveTaken"),
            "remaining": worker.get("annualLeaveBalance"),
            "employmentType": worker.get("employmentType"),
            "periodStart": worker.get("employmentStartDate"),
            "periodEnd": worker.get("employmentEndDate"),
        }

    @mcp.tool(
        name="get_profile",
        description=(
            "Get the authenticated worker's full profile (name, designation, department, "
            "evaluator, leave entitlement/taken/balance, employment type and period)."
        ),
        structured_output=True,
    )
    def get_profile(ctx: Context) -> dict[str, Any]:
        worker_id = _worker_id(ctx)
        return api.get(worker_id, worker_path(worker_id)).get("worker", {})

    @mcp.tool(
        name="get_calendar",
        description=(
            "Show the shared team calendar of AL/EL/MC leave. Optional month (YYYY-MM) "
            "restricts to one month; omit it to get the full year. Each entry shows who is "
            "on which leave and a link to the generated PDF. Other people's reasons are never "
            "exposed. Entries where isOwn=true belong to the current worker."
        ),
        structured_output=True,
    )
    def get_calendar(ctx: Context, month: str | None = None) -> list[dict[str, Any]]:
        worker_id = _worker_id(ctx)
        if month is not None and not re.fullmatch(r"\d{4}-\d{2}", month):
            raise ValueError("month must use YYYY-MM format.")
        entries = api.get(worker_id, "/api/calendar").get("entries", [])
        if month:
            entries = [entry for entry in entries if str(entry.get("calendarStart", "")).startswith(month)]
        return [
            {
                "date": entry.get("calendarStart"),
                "workerName": (
                    entry.get("calendarName")
                    if entry.get("calendarName") is not None
                    else entry.get("workerName")
                ),
                "formType": entry.get("formType"),
                "isOwn": entry.get("isOwn", entry.get("workerId") == worker_id),
                "pdfUrl": entry.get("pdfUrl"),
                "isHalfDay": entry.get("isHalfDay"),
                "halfDayPeriod": entry.get("halfDayPeriod"),
            }
            for entry in entries
        ]

    @mcp.tool(
        name="list_my_submissions",
        description=(
            "List the authenticated worker's own submission history, newest first. Optional "
            "formType filter (AL, EL, MC, KPI, EXP, OT, UNPAID, OTHER). Optional limit."
        ),
        structured_output=True,
    )
    def list_my_submissions(
        ctx: Context,
        formType: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        worker_id = _worker_id(ctx)
        if formType is not None and formType not in _FORM_TYPES:
            raise ValueError("formType must be one of AL, EL, MC, KPI, EXP, OT, UNPAID, OTHER.")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1.")
        submissions = api.get(worker_id, "/api/submissions").get("submissions", [])
        if formType:
            submissions = [submission for submission in submissions if submission.get("formType") == formType]
        if limit is not None:
            submissions = submissions[:limit]
        fields = (
            "id",
            "formType",
            "formName",
            "startDate",
            "endDate",
            "durationDays",
            "isHalfDay",
            "halfDayPeriod",
            "reason",
            "kpiMonth",
            "pdfUrl",
            "createdAt",
        )
        return [{field: submission.get(field) for field in fields} for submission in submissions]

    @mcp.tool(
        name="list_reference_forms",
        description=(
            "List the shared reference files in the Others tab (PDFs, images, Office docs) "
            "that the team can view."
        ),
        structured_output=True,
    )
    def list_reference_forms(ctx: Context) -> list[dict[str, Any]]:
        worker_id = _worker_id(ctx)
        forms = api.get(worker_id, "/api/others").get("forms", [])
        fields = ("name", "fileName", "url", "size", "updatedAt")
        return [{field: form.get(field) for field in fields} for form in forms]

    for tool_name in READ_TOOL_SCHEMAS:
        _set_schema(mcp, tool_name)
