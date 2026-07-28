from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, g, current_app

from .auth import require_auth
from .db import query, query_one, execute
from .workers import _get_worker_enriched
from .utils import (
    normalize_worker_id,
    sanitize_file_part,
    parse_iso_date,
    to_iso_date,
    parse_optional_date,
    parse_year_month,
    end_of_month,
    normalize_leave_type,
    clean_profile_value,
    get_leave_summary,
    format_kpi_month_label,
    format_month_range_label,
    parse_kpi_scores,
    parse_kpi_comments,
    parse_kpi_options,
    parse_expense_items,
    parse_ot_items,
    parse_optional_non_negative_number,
    OT_RATE_TYPES,
    AL_DEDUCTING_LEAVE_TYPES,
    LEAVE_TYPES,
)
from . import pdf_service
from . import google_sheets

bp = Blueprint("submissions", __name__)


def _sheets_label(form_type: str, display_name: str, is_half_day: bool, half_day_period: str | None) -> str:
    return google_sheets.build_calendar_label(form_type, display_name, is_half_day, half_day_period)


def _build_sheets_label(row: dict, worker_override: dict | None = None) -> str | None:
    """Reconstruct the calendar label for a submission row. Returns None for non-calendar forms."""
    form_type = row.get("form_type")
    if form_type not in ("AL", "EL", "MC"):
        return None
    snapshot = json.loads(row["worker_snapshot"]) if isinstance(row.get("worker_snapshot"), str) else (row.get("worker_snapshot") or {})
    name = (worker_override or {}).get("name") or snapshot.get("name")
    calendar_name = (worker_override or {}).get("calendarName") or snapshot.get("calendarName")
    display_name = google_sheets.calendar_display_name(name, row.get("worker_id"), calendar_name)
    return _sheets_label(form_type, display_name, bool(row.get("is_half_day")), row.get("half_day_period"))


def _submission_date_range(row: dict):
    start_date = row.get("start_date")
    end_date = row.get("end_date")
    if not start_date or not end_date:
        return None
    start_d = start_date if isinstance(start_date, date) else datetime.fromisoformat(str(start_date)).date()
    end_d = end_date if isinstance(end_date, date) else datetime.fromisoformat(str(end_date)).date()
    return start_d, end_d


def _sync_submission_to_sheets(row: dict) -> None:
    """Best-effort Google Sheets calendar sync for AL/EL/MC. Never raises."""
    cfg = current_app.config
    if not cfg.get("GOOGLE_SHEETS_ENABLED"):
        return
    label = _build_sheets_label(row)
    if not label:
        return
    rng = _submission_date_range(row)
    if not rng:
        return
    start_d, end_d = rng
    try:
        written = False
        for d in google_sheets.date_range(start_d, end_d):
            if google_sheets.append_calendar_entry(d, label):
                written = True
        if written:
            execute("UPDATE submissions SET sheets_synced_at = %s WHERE id = %s", (datetime.now(timezone.utc).replace(microsecond=0), row["id"]))
    except Exception as exc:
        current_app.logger.warning("Google Sheets sync failed for submission %s: %s", row.get("id"), exc)


def _remove_submission_from_sheets(row: dict) -> None:
    """Best-effort removal of a submission's calendar lines on delete. Never raises.

    Uses the worker's CURRENT calendar name (from the workers table) rather than the
    submission snapshot, because the rename hook rewrites sheet lines to the latest name
    whenever the worker updates their profile. Snapshot-based labels would miss lines
    that were renamed after submission.
    """
    cfg = current_app.config
    if not cfg.get("GOOGLE_SHEETS_ENABLED"):
        return
    if row.get("form_type") not in ("AL", "EL", "MC"):
        return
    rng = _submission_date_range(row)
    if not rng:
        return
    start_d, end_d = rng
    try:
        worker_row = query_one("SELECT name, calendar_name FROM workers WHERE worker_id = %s", (row.get("worker_id"),))
        worker_override = {
            "name": (worker_row or {}).get("name"),
            "calendarName": (worker_row or {}).get("calendar_name"),
        }
        label = _build_sheets_label(row, worker_override=worker_override)
        if not label:
            return
        for d in google_sheets.date_range(start_d, end_d):
            google_sheets.remove_calendar_line(d, label)
    except Exception as exc:
        current_app.logger.warning("Google Sheets removal failed for submission %s: %s", row.get("id"), exc)


def _remove_generated_file(file_name: str | None, folder: Path) -> None:
    if not file_name:
        return
    candidate = (folder / Path(str(file_name)).name).resolve()
    if candidate.parent != folder.resolve():
        raise RuntimeError("Invalid generated file path.")
    candidate.unlink(missing_ok=True)


def _remove_generated_workbook(file_name: str | None, folder: Path) -> None:
    if not file_name:
        return
    candidate = (folder / Path(str(file_name)).name).resolve()
    resolved_folder = folder.resolve()
    if candidate.parent != resolved_folder:
        raise RuntimeError("Invalid generated file path.")
    candidate.unlink(missing_ok=True)
    for temp_path in resolved_folder.glob(f"{candidate.stem}~*.tmp"):
        if temp_path.resolve().parent != resolved_folder:
            raise RuntimeError("Invalid generated file path.")
        temp_path.unlink(missing_ok=True)


def _row_to_submission(row: dict) -> dict:
    def _load(val):
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return val
        return val

    return {
        "id": row.get("id"),
        "workerId": row.get("worker_id"),
        "formType": row.get("form_type"),
        "formName": row.get("form_name"),
        "leaveType": row.get("leave_type"),
        "startDate": row.get("start_date").isoformat() if row.get("start_date") else None,
        "endDate": row.get("end_date").isoformat() if row.get("end_date") else None,
        "calendarStart": row.get("start_date").isoformat() if row.get("start_date") else None,
        "calendarEnd": row.get("end_date").isoformat() if row.get("end_date") else None,
        "durationDays": float(row["duration_days"]) if row.get("duration_days") is not None else None,
        "affectsAnnualLeave": bool(row.get("affects_al")),
        "annualLeaveDaysApplied": float(row["al_days_applied"]) if row.get("al_days_applied") is not None else 0,
        "isHalfDay": bool(row.get("is_half_day")),
        "halfDayPeriod": row.get("half_day_period"),
        "reason": row.get("reason"),
        "kpiMonth": row.get("kpi_month"),
        "applicationDate": row.get("application_date").isoformat() if row.get("application_date") else None,
        "kpiData": _load(row.get("kpi_data")),
        "expenseData": _load(row.get("kpi_data")) if row.get("form_type") == "EXP" else None,
        "otData": _load(row.get("kpi_data")) if row.get("form_type") == "OT" else None,
        "workerSnapshot": _load(row.get("worker_snapshot")),
        "leaveSummary": _load(row.get("leave_summary")),
        "pdfFileName": row.get("pdf_file_name"),
        "workbookFileName": row.get("workbook_file_name"),
        "pdfUrl": f"/generated/pdfs/{row['pdf_file_name']}" if row.get("pdf_file_name") else None,
        "workbookUrl": f"/generated/workbooks/{row['workbook_file_name']}" if row.get("workbook_file_name") else None,
        "createdAt": row.get("created_at").isoformat() + "Z" if row.get("created_at") else None,
    }


def _row_to_calendar_entry(row: dict) -> dict:
    pdf_file_name = row.get("pdf_file_name")
    return {
        "id": row.get("id"),
        "workerId": row.get("worker_id"),
        "workerName": row.get("worker_name") or row.get("worker_id"),
        "calendarName": row.get("calendar_name"),
        "formType": row.get("form_type"),
        "leaveType": row.get("leave_type"),
        "calendarStart": row.get("start_date").isoformat() if row.get("start_date") else None,
        "calendarEnd": row.get("end_date").isoformat() if row.get("end_date") else None,
        "durationDays": row.get("duration_days"),
        "isHalfDay": bool(row.get("is_half_day")),
        "halfDayPeriod": row.get("half_day_period"),
        "pdfUrl": f"/generated/pdfs/{pdf_file_name}" if pdf_file_name else None,
        "isOwn": row.get("worker_id") == g.worker_id,
    }


@bp.get("/api/calendar")
@require_auth
def calendar_entries():
    rows = query(
        """SELECT
             s.id, s.worker_id, COALESCE(w.name, s.worker_id) AS worker_name,
             w.calendar_name,
             s.form_type, s.leave_type, s.start_date, s.end_date, s.duration_days,
             s.is_half_day, s.half_day_period, s.pdf_file_name, s.created_at
           FROM submissions s
           LEFT JOIN workers w ON w.worker_id = s.worker_id
           WHERE s.form_type IN ('AL', 'EL', 'MC')
           ORDER BY s.start_date ASC, s.created_at ASC"""
    )
    return jsonify({"entries": [_row_to_calendar_entry(r) for r in rows]})


@bp.get("/api/submissions")
@require_auth
def submissions():
    rows = query(
        "SELECT * FROM submissions WHERE worker_id = %s ORDER BY created_at DESC",
        (g.worker_id,),
    )
    return jsonify({"submissions": [_row_to_submission(r) for r in rows]})


@bp.delete("/api/submissions/<submission_id>")
@require_auth
def delete_submission(submission_id: str):
    row = query_one(
        "SELECT * FROM submissions WHERE id = %s AND worker_id = %s",
        (submission_id, g.worker_id),
    )
    if not row:
        return jsonify({"error": "Submission not found."}), 404

    pdf_dir = current_app.config["PDF_DIR"]
    wb_dir = current_app.config["WORKBOOK_DIR"]
    try:
        _remove_generated_file(row.get("pdf_file_name"), pdf_dir)
        _remove_generated_workbook(row.get("workbook_file_name"), wb_dir)
    except OSError as exc:
        return jsonify({"error": f"Could not delete generated file: {exc}"}), 500
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    execute("DELETE FROM submissions WHERE id = %s", (submission_id,))
    _remove_submission_from_sheets(row)
    return jsonify({"deleted": _row_to_submission(row)})


@bp.post("/api/submissions/al")
@require_auth
def create_al_submission():
    body = request.get_json(silent=True) or {}
    worker = _get_worker_enriched(g.worker_id)
    if not worker:
        return jsonify({"error": f"No saved worker profile found for {g.worker_id}."}), 404

    try:
        start = parse_iso_date(body.get("startDate"), "startDate")
        end = parse_iso_date(body.get("endDate") or body.get("startDate"), "endDate")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if end < start:
        return jsonify({"error": "End date cannot be before start date."}), 400

    period_start = parse_optional_date(worker.get("employmentStartDate"))
    period_end = parse_optional_date(worker.get("employmentEndDate"))
    if period_start and period_end and (start.date() < period_start or end.date() > period_end):
        return jsonify({"error": "AL dates must be within the worker employment period."}), 400

    try:
        leave_type = normalize_leave_type(body.get("leaveType"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    reason = clean_profile_value(body.get("reason"))
    if not reason:
        return jsonify({"error": "Reason is required."}), 400

    is_half_day = body.get("isHalfDay", False)
    half_day_period = None
    if is_half_day:
        if start.date() != end.date():
            return jsonify({"error": "Half-day leave must be for a single day."}), 400
        half_day_period = clean_profile_value(body.get("halfDayPeriod", "")).upper()
        if half_day_period not in ("AM", "PM"):
            return jsonify({"error": "HalfDayPeriod must be AM or PM."}), 400
    raw_days = (end.date() - start.date()).days + 1
    duration_days = 0.5 if is_half_day else float(raw_days)
    affects_al = leave_type in AL_DEDUCTING_LEAVE_TYPES
    annual_leave_days = duration_days if affects_al else 0
    leave_summary = get_leave_summary(worker, annual_leave_days)
    if bool(body.get("removeEntitlement")):
        leave_summary["remove_entitlement"] = True
    leave_type_meta = LEAVE_TYPES[leave_type]
    now = datetime.now()
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    submission_id = f"{leave_type_meta['code']}-{uuid.uuid4().hex[:8].upper()}"
    start_iso = to_iso_date(start)
    end_iso = to_iso_date(end)
    application_iso = to_iso_date(now)

    safe_worker_id = sanitize_file_part(g.worker_id)
    safe_sub_id = sanitize_file_part(submission_id)
    pdf_file_name = f"{safe_worker_id}_{leave_type_meta['code']}_{start_iso}_{safe_sub_id}.pdf"
    workbook_file_name = f"{safe_worker_id}_{leave_type_meta['code']}_{start_iso}_{safe_sub_id}.xls"
    pdf_path = current_app.config["PDF_DIR"] / pdf_file_name
    workbook_path = current_app.config["WORKBOOK_DIR"] / workbook_file_name
    form_ori_dir = current_app.config["FORM_ORI_DIR"]

    try:
        pdf_service.generate_al(
            template_path=form_ori_dir / "Leave Application Form.xls",
            workbook_path=workbook_path,
            pdf_path=pdf_path,
            worker=worker,
            start_iso=start_iso,
            end_iso=end_iso,
            duration_days=duration_days,
            leave_type=leave_type,
            reason=reason,
            leave_summary=leave_summary,
            application_iso=application_iso,
            half_day_period=half_day_period,
        )
    except Exception as exc:
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    worker_snapshot = {
        "workerId": worker.get("workerId"),
        "name": worker.get("name"),
        "designation": worker.get("designation"),
        "department": worker.get("department"),
        "houseTel": worker.get("houseTel"),
        "otherTel": worker.get("otherTel"),
        "calendarName": worker.get("calendarName"),
    }

    execute(
        """INSERT INTO submissions
           (id, worker_id, form_type, form_name, leave_type, start_date, end_date,
            duration_days, affects_al, al_days_applied, is_half_day, half_day_period,
            reason, application_date,
            leave_summary, worker_snapshot, pdf_file_name, workbook_file_name, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (submission_id, g.worker_id, leave_type_meta["code"], leave_type_meta["name"],
         leave_type, start_iso, end_iso, duration_days, affects_al, annual_leave_days,
         is_half_day, half_day_period, reason, application_iso, json.dumps(leave_summary),
         json.dumps(worker_snapshot), pdf_file_name, workbook_file_name, created_at),
    )

    row = query_one("SELECT * FROM submissions WHERE id = %s", (submission_id,))
    _sync_submission_to_sheets(row)
    return jsonify({"submission": _row_to_submission(row)}), 201


@bp.post("/api/submissions/mc")
@require_auth
def create_mc_submission():
    body = request.get_json(silent=True) or {}
    worker = _get_worker_enriched(g.worker_id)
    if not worker:
        return jsonify({"error": f"No saved worker profile found for {g.worker_id}."}), 404

    try:
        start = parse_iso_date(body.get("startDate"), "startDate")
        end = parse_iso_date(body.get("endDate") or body.get("startDate"), "endDate")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if end < start:
        return jsonify({"error": "End date cannot be before start date."}), 400

    period_start = parse_optional_date(worker.get("employmentStartDate"))
    period_end = parse_optional_date(worker.get("employmentEndDate"))
    if period_start and period_end and (start.date() < period_start or end.date() > period_end):
        return jsonify({"error": "MC dates must be within the worker employment period."}), 400

    sickness_reason = clean_profile_value(body.get("sicknessReason") or body.get("reason"))
    if not sickness_reason:
        return jsonify({"error": "Sickness/reason is required."}), 400

    duration_days = (end.date() - start.date()).days + 1
    now = datetime.now()
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    submission_id = f"MC-{uuid.uuid4().hex[:8].upper()}"
    start_iso = to_iso_date(start)
    end_iso = to_iso_date(end)
    application_iso = to_iso_date(now)

    safe_worker_id = sanitize_file_part(g.worker_id)
    safe_sub_id = sanitize_file_part(submission_id)
    pdf_file_name = f"{safe_worker_id}_MC_{start_iso}_{safe_sub_id}.pdf"
    workbook_file_name = f"{safe_worker_id}_MC_{start_iso}_{safe_sub_id}.xls"
    pdf_path = current_app.config["PDF_DIR"] / pdf_file_name
    workbook_path = current_app.config["WORKBOOK_DIR"] / workbook_file_name
    form_ori_dir = current_app.config["FORM_ORI_DIR"]

    try:
        pdf_service.generate_mc(
            template_path=form_ori_dir / "MC FORM .xls",
            workbook_path=workbook_path,
            pdf_path=pdf_path,
            worker=worker,
            start_iso=start_iso,
            end_iso=end_iso,
            duration_days=duration_days,
            sickness_reason=sickness_reason,
            application_iso=application_iso,
        )
    except Exception as exc:
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    worker_snapshot = {
        "workerId": worker.get("workerId"),
        "name": worker.get("name"),
        "designation": worker.get("designation"),
        "department": worker.get("department"),
        "houseTel": worker.get("houseTel"),
        "otherTel": worker.get("otherTel"),
        "calendarName": worker.get("calendarName"),
    }

    execute(
        """INSERT INTO submissions
           (id, worker_id, form_type, form_name, start_date, end_date,
            duration_days, affects_al, al_days_applied, reason, application_date,
            worker_snapshot, pdf_file_name, workbook_file_name, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (submission_id, g.worker_id, "MC", "Medical Certificate",
         start_iso, end_iso, duration_days, False, 0,
         sickness_reason, application_iso, json.dumps(worker_snapshot),
         pdf_file_name, workbook_file_name, created_at),
    )

    row = query_one("SELECT * FROM submissions WHERE id = %s", (submission_id,))
    _sync_submission_to_sheets(row)
    return jsonify({"submission": _row_to_submission(row)}), 201


@bp.post("/api/submissions/kpi")
@require_auth
def create_kpi_submission():
    body = request.get_json(silent=True) or {}
    worker = _get_worker_enriched(g.worker_id)
    if not worker:
        return jsonify({"error": f"No saved worker profile found for {g.worker_id}."}), 404

    try:
        month_start = parse_year_month(body.get("kpiMonth"), "kpiMonth")
        scores = parse_kpi_scores(body)
        comments = parse_kpi_comments(body)
        summary_options = parse_kpi_options(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    period_start = parse_optional_date(worker.get("employmentStartDate"))
    period_end = parse_optional_date(worker.get("employmentEndDate"))
    month_end = end_of_month(month_start)
    if period_start and period_end and (month_start < period_start or month_end > period_end):
        return jsonify({"error": "KPI month must be within the worker employment period."}), 400

    month_key = month_start.strftime("%Y-%m")
    existing = query_one(
        "SELECT id FROM submissions WHERE worker_id = %s AND form_type = 'KPI' AND kpi_month = %s",
        (g.worker_id, month_key),
    )
    if existing:
        return jsonify({"error": f"KPI form for {month_key} already exists. Delete it first to regenerate."}), 400

    evaluator_name = clean_profile_value(body.get("evaluatorName") or worker.get("evaluatorName"))
    if not evaluator_name:
        return jsonify({"error": "Evaluator name is required."}), 400

    task_list = clean_profile_value(body.get("taskList"))
    if not task_list:
        return jsonify({"error": "Task list is required."}), 400

    worker_feedback = clean_profile_value(body.get("workerFeedback"))
    training_needs = clean_profile_value(body.get("trainingNeeds"))
    evaluator_feedback = clean_profile_value(body.get("evaluatorFeedback"))
    month_label = format_kpi_month_label(month_start)
    application_date = to_iso_date(datetime.now())
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    submission_id = f"KPI-{uuid.uuid4().hex[:8].upper()}"

    safe_worker_id = sanitize_file_part(g.worker_id)
    safe_sub_id = sanitize_file_part(submission_id)
    pdf_file_name = f"{safe_worker_id}_KPI_{month_key}_{safe_sub_id}.pdf"
    workbook_file_name = f"{safe_worker_id}_KPI_{month_key}_{safe_sub_id}.xlsx"
    pdf_path = current_app.config["PDF_DIR"] / pdf_file_name
    workbook_path = current_app.config["WORKBOOK_DIR"] / workbook_file_name
    form_ori_dir = current_app.config["FORM_ORI_DIR"]

    try:
        pdf_service.generate_kpi(
            template_path=form_ori_dir / "Borang Penilaian Prestasi (Non Leader).xlsx",
            workbook_path=workbook_path,
            pdf_path=pdf_path,
            worker=worker,
            evaluator_name=evaluator_name,
            month_label=month_label,
            task_list=task_list,
            scores=scores,
            comments=comments,
            summary_options=summary_options,
            worker_feedback=worker_feedback,
            training_needs=training_needs,
            evaluator_feedback=evaluator_feedback,
            application_date=application_date,
        )
    except Exception as exc:
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    kpi_data = {
        "evaluatorName": evaluator_name,
        "taskList": task_list,
        "scores": scores,
        "comments": comments,
        "summaryOptions": summary_options,
        "workerFeedback": worker_feedback,
        "trainingNeeds": training_needs,
        "evaluatorFeedback": evaluator_feedback,
    }
    worker_snapshot = {
        "workerId": worker.get("workerId"),
        "name": worker.get("name"),
        "designation": worker.get("designation"),
        "department": worker.get("department"),
        "houseTel": worker.get("houseTel"),
        "otherTel": worker.get("otherTel"),
        "evaluatorName": worker.get("evaluatorName"),
    }

    execute(
        """INSERT INTO submissions
           (id, worker_id, form_type, form_name, start_date, end_date,
            duration_days, affects_al, al_days_applied, reason, kpi_month,
            application_date, kpi_data, worker_snapshot, pdf_file_name, workbook_file_name, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (submission_id, g.worker_id, "KPI", "KPI Form",
         month_start.isoformat(), month_end.isoformat(),
         1, False, 0, task_list, month_key, application_date,
         json.dumps(kpi_data), json.dumps(worker_snapshot),
         pdf_file_name, workbook_file_name, created_at),
    )

    row = query_one("SELECT * FROM submissions WHERE id = %s", (submission_id,))
    return jsonify({"submission": _row_to_submission(row)}), 201


@bp.post("/api/submissions/ot")
@require_auth
def create_ot_submission():
    body = request.get_json(silent=True) or {}
    worker = _get_worker_enriched(g.worker_id)
    if not worker:
        return jsonify({"error": f"No saved worker profile found for {g.worker_id}."}), 404

    try:
        month_start = parse_year_month(body.get("claimMonth"), "claimMonth")
        month_end_start = parse_year_month(body.get("claimMonthEnd"), "claimMonthEnd") if body.get("claimMonthEnd") else None
        items = parse_ot_items(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if month_end_start and month_end_start < month_start:
        return jsonify({"error": "Claim month end cannot be before the start month."}), 400

    range_end = end_of_month(month_end_start) if month_end_start else end_of_month(month_start)
    for item in items:
        item_date = parse_optional_date(item["date"])
        if not item_date or item_date < month_start or item_date > range_end:
            return jsonify({"error": "Overtime item dates must be within the claim month range."}), 400

    month_key = month_start.strftime("%Y-%m")
    month_label = format_month_range_label(month_start, month_end_start)
    application_iso = to_iso_date(datetime.now())
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    submission_id = f"OT-{uuid.uuid4().hex[:8].upper()}"

    safe_worker_id = sanitize_file_part(g.worker_id)
    safe_sub_id = sanitize_file_part(submission_id)
    pdf_file_name = f"{safe_worker_id}_OT_{month_key}_{safe_sub_id}.pdf"
    workbook_file_name = f"{safe_worker_id}_OT_{month_key}_{safe_sub_id}.xls"
    pdf_path = current_app.config["PDF_DIR"] / pdf_file_name
    workbook_path = current_app.config["WORKBOOK_DIR"] / workbook_file_name
    form_ori_dir = current_app.config["FORM_ORI_DIR"]

    try:
        pdf_service.generate_ot(
            template_path=form_ori_dir / "OT Form latest.xls",
            workbook_path=workbook_path,
            pdf_path=pdf_path,
            worker=worker,
            month_label=month_label,
            items=items,
        )
    except Exception as exc:
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    hours_by_rate = {
        rate_type: round(sum(float(item["hours"]) for item in items if item["rateType"] == rate_type), 2)
        for rate_type in OT_RATE_TYPES
    }
    total_hours = round(sum(float(item["hours"]) for item in items), 2)
    ot_data = {
        "claimMonth": month_key,
        "claimMonthEnd": month_end_start.strftime("%Y-%m") if month_end_start else None,
        "totalHours": total_hours,
        "hoursByRate": hours_by_rate,
        "items": items,
    }
    worker_snapshot = {
        "workerId": worker.get("workerId"),
        "name": worker.get("name"),
        "designation": worker.get("designation"),
        "department": worker.get("department"),
    }
    start_iso = min(item["date"] for item in items)
    end_iso = max(item["date"] for item in items)

    execute(
        """INSERT INTO submissions
           (id, worker_id, form_type, form_name, start_date, end_date,
            duration_days, affects_al, al_days_applied, reason, kpi_month,
            application_date, kpi_data, worker_snapshot, pdf_file_name, workbook_file_name, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (submission_id, g.worker_id, "OT", "Overtime Claim",
         start_iso, end_iso, len(items), False, 0, f"{month_key} overtime claim",
         month_key, application_iso, json.dumps(ot_data), json.dumps(worker_snapshot),
         pdf_file_name, workbook_file_name, created_at),
    )

    row = query_one("SELECT * FROM submissions WHERE id = %s", (submission_id,))
    return jsonify({"submission": _row_to_submission(row)}), 201


@bp.post("/api/submissions/expenses")
@require_auth
def create_expense_submission():
    body = request.get_json(silent=True) or {}
    worker = _get_worker_enriched(g.worker_id)
    if not worker:
        return jsonify({"error": f"No saved worker profile found for {g.worker_id}."}), 404

    try:
        month_start = parse_year_month(body.get("claimMonth"), "claimMonth")
        month_end_start = parse_year_month(body.get("claimMonthEnd"), "claimMonthEnd") if body.get("claimMonthEnd") else None
        items = parse_expense_items(body)
        advances = parse_optional_non_negative_number(body.get("advances"), "advances")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if month_end_start and month_end_start < month_start:
        return jsonify({"error": "Claim month end cannot be before the start month."}), 400

    range_end = end_of_month(month_end_start) if month_end_start else end_of_month(month_start)
    for item in items:
        item_date = parse_optional_date(item["date"])
        if not item_date or item_date < month_start or item_date > range_end:
            return jsonify({"error": "Expense item dates must be within the claim month range."}), 400

    supervisor_name = clean_profile_value(body.get("supervisorName") or worker.get("evaluatorName"))
    if not supervisor_name:
        return jsonify({"error": "Supervisor name is required."}), 400

    site = clean_profile_value(body.get("site"))
    month_key = month_start.strftime("%Y-%m")
    month_label = format_month_range_label(month_start, month_end_start, upper=True)
    application_iso = to_iso_date(datetime.now())
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    submission_id = f"EXP-{uuid.uuid4().hex[:8].upper()}"

    safe_worker_id = sanitize_file_part(g.worker_id)
    safe_sub_id = sanitize_file_part(submission_id)
    pdf_file_name = f"{safe_worker_id}_EXP_{month_key}_{safe_sub_id}.pdf"
    workbook_file_name = f"{safe_worker_id}_EXP_{month_key}_{safe_sub_id}.xlsx"
    pdf_path = current_app.config["PDF_DIR"] / pdf_file_name
    workbook_path = current_app.config["WORKBOOK_DIR"] / workbook_file_name
    form_ori_dir = current_app.config["FORM_ORI_DIR"]

    try:
        pdf_service.generate_expense(
            template_path=form_ori_dir / "expenses claim form baru.xlsx",
            workbook_path=workbook_path,
            pdf_path=pdf_path,
            worker=worker,
            supervisor_name=supervisor_name,
            site=site,
            month_label=month_label,
            items=items,
            advances=advances,
        )
    except Exception as exc:
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    total_amount = round(sum(float(item.get("total") or 0) for item in items), 2)
    expense_data = {
        "claimMonth": month_key,
        "claimMonthEnd": month_end_start.strftime("%Y-%m") if month_end_start else None,
        "site": site,
        "supervisorName": supervisor_name,
        "advances": advances,
        "totalAmount": total_amount,
        "amountToReimburse": round(total_amount - advances, 2),
        "items": items,
    }
    worker_snapshot = {
        "workerId": worker.get("workerId"),
        "name": worker.get("name"),
        "designation": worker.get("designation"),
        "department": worker.get("department"),
        "evaluatorName": worker.get("evaluatorName"),
    }
    start_iso = min(item["date"] for item in items)
    end_iso = max(item["date"] for item in items)

    execute(
        """INSERT INTO submissions
           (id, worker_id, form_type, form_name, start_date, end_date,
            duration_days, affects_al, al_days_applied, reason, kpi_month,
            application_date, kpi_data, worker_snapshot, pdf_file_name, workbook_file_name, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (submission_id, g.worker_id, "EXP", "Expense Claim",
         start_iso, end_iso, len(items), False, 0, f"{month_key} expense claim",
         month_key, application_iso, json.dumps(expense_data), json.dumps(worker_snapshot),
         pdf_file_name, workbook_file_name, created_at),
    )

    row = query_one("SELECT * FROM submissions WHERE id = %s", (submission_id,))
    return jsonify({"submission": _row_to_submission(row)}), 201
