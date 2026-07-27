from __future__ import annotations

from flask import Blueprint, jsonify, request, g, current_app

from .auth import require_auth, _serialize_worker
from .db import query_one, execute, query
from .utils import (
    normalize_worker_id,
    clean_profile_value,
    standardize_profile_text,
    parse_non_negative_number,
    format_number,
    parse_optional_date,
    current_year_bounds,
    enrich_worker,
    get_leave_period,
    affects_annual_leave,
    count_al_taken_from_list,
    parse_iso_date,
)

bp = Blueprint("workers", __name__)


def _get_worker_enriched(worker_id: str) -> dict | None:
    row = query_one("SELECT * FROM workers WHERE worker_id = %s", (worker_id,))
    if not row:
        return None
    worker = _serialize_worker(row)
    from .auth import _get_user_role
    worker["role"] = _get_user_role(worker_id)

    employment_type, period_start, period_end = get_leave_period(worker)
    submissions_rows = query(
        "SELECT leave_type, affects_al, al_days_applied, start_date, end_date FROM submissions WHERE worker_id = %s",
        (worker_id,),
    )
    # Build lightweight dicts for count_al_taken_from_list
    sub_list = [
        {
            "workerId": worker_id,
            "leaveType": r.get("leave_type"),
            "affectsAnnualLeave": bool(r.get("affects_al")),
            "calendarStart": r.get("start_date").isoformat() if r.get("start_date") else None,
            "calendarEnd": r.get("end_date").isoformat() if r.get("end_date") else None,
        }
        for r in submissions_rows
    ]
    taken = count_al_taken_from_list(worker_id, period_start, period_end, sub_list)
    return enrich_worker(worker, taken_to_date=float(taken))


@bp.get("/api/workers/<worker_id>")
@require_auth
def worker_profile(worker_id: str):
    normalized = normalize_worker_id(worker_id)
    if normalized != g.worker_id:
        return jsonify({"error": "Access denied."}), 403
    worker = _get_worker_enriched(normalized)
    if not worker:
        return jsonify({"error": f"No saved worker profile found for {normalized}."}), 404
    return jsonify({"worker": worker})


@bp.put("/api/workers/<worker_id>")
@require_auth
def update_worker_profile(worker_id: str):
    normalized = normalize_worker_id(worker_id)
    if normalized != g.worker_id:
        return jsonify({"error": "Access denied."}), 403

    row = query_one("SELECT * FROM workers WHERE worker_id = %s", (normalized,))
    if not row:
        return jsonify({"error": f"No saved worker profile found for {normalized}."}), 404

    body = request.get_json(silent=True) or {}

    name = standardize_profile_text(body.get("name", row.get("name")), is_name=True)
    if not name:
        return jsonify({"error": "Name is required."}), 400

    designation = standardize_profile_text(body.get("designation", row.get("designation")))
    department = standardize_profile_text(body.get("department", row.get("department")))
    house_tel = clean_profile_value(body.get("houseTel", row.get("house_tel")))
    other_tel = clean_profile_value(body.get("otherTel", row.get("other_tel")))
    evaluator_name = standardize_profile_text(body.get("evaluatorName", row.get("evaluator_name")), is_name=True)

    if "annualLeaveEntitlement" in body:
        try:
            entitlement = parse_non_negative_number(body.get("annualLeaveEntitlement"), "AL entitlement")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
    else:
        entitlement = float(row.get("annual_leave_entitlement") or 0)

    employment_type = clean_profile_value(
        body.get("employmentType", row.get("employment_type") or "permanent")
    ).lower()
    if employment_type not in {"permanent", "contract"}:
        return jsonify({"error": "Employment type must be permanent or contract."}), 400

    if employment_type == "permanent":
        period_start, period_end = current_year_bounds()
        emp_start = period_start.isoformat()
        emp_end = period_end.isoformat()
    else:
        start = parse_optional_date(body.get("employmentStartDate") or (row.get("employment_start_date").isoformat() if row.get("employment_start_date") else None))
        end = parse_optional_date(body.get("employmentEndDate") or (row.get("employment_end_date").isoformat() if row.get("employment_end_date") else None))
        if not start or not end:
            return jsonify({"error": "Contract start date and end date are required."}), 400
        if end < start:
            return jsonify({"error": "Contract end date cannot be before start date."}), 400
        emp_start = start.isoformat()
        emp_end = end.isoformat()

    profile_complete = True

    execute(
        """UPDATE workers SET
            name = %s, designation = %s, department = %s,
            house_tel = %s, other_tel = %s, evaluator_name = %s,
            annual_leave_entitlement = %s, employment_type = %s,
            employment_start_date = %s, employment_end_date = %s,
            profile_complete = %s
           WHERE worker_id = %s""",
        (name, designation, department, house_tel, other_tel, evaluator_name,
         entitlement, employment_type, emp_start, emp_end, profile_complete, normalized),
    )

    worker = _get_worker_enriched(normalized)
    return jsonify({"worker": worker})
