"""Input schemas exposed by the Phase 1 MCP tools."""

NO_ARGS = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

CALENDAR_ARGS = {
    "type": "object",
    "properties": {
        "month": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}$",
            "description": "Optional calendar month filter in YYYY-MM format.",
        }
    },
    "additionalProperties": False,
}

SUBMISSIONS_ARGS = {
    "type": "object",
    "properties": {
        "formType": {
            "type": "string",
            "enum": ["AL", "EL", "MC", "KPI", "EXP", "OT", "UNPAID", "OTHER"],
            "description": "Optional form type filter.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "description": "Optional maximum number of newest submissions to return.",
        },
    },
    "additionalProperties": False,
}

READ_TOOL_SCHEMAS = {
    "get_leave_balance": NO_ARGS,
    "get_profile": NO_ARGS,
    "get_calendar": CALENDAR_ARGS,
    "list_my_submissions": SUBMISSIONS_ARGS,
    "list_reference_forms": NO_ARGS,
}
