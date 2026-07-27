from __future__ import annotations

import re
from datetime import date, datetime, timedelta


LEAVE_TYPES = {
    "annual": {
        "code": "AL",
        "name": "Annual Leave",
        "defaultReason": "Annual Leave",
    },
    "unpaid": {
        "code": "UNPAID",
        "name": "Unpaid Leave",
        "defaultReason": "",
    },
    "emergency": {
        "code": "EL",
        "name": "Emergency Leave",
        "defaultReason": "",
    },
    "other": {
        "code": "OTHER",
        "name": "Others",
        "defaultReason": "",
    },
}

AL_DEDUCTING_LEAVE_TYPES = {"annual", "emergency"}

KPI_SCORE_CELLS = {
    "knowledge": ["H16", "H17", "H18", "H19", "H20"],
    "quality": ["H24", "H25", "H26", "H27", "H28"],
    "problemSolving": ["H32", "H33", "H34", "H35", "H36"],
    "communication": ["H40", "H41", "H42", "H43", "H44"],
    "teamwork": ["H48", "H49", "H50", "H51", "H52"],
    "initiative": ["H56", "H57", "H58", "H59", "H60"],
    "continuousLearning": ["H64", "H65", "H66", "H67", "H68"],
}

KPI_COMMENT_CELLS = {
    "knowledge": "B21",
    "quality": "B29",
    "problemSolving": "B37",
    "communication": "B45",
    "teamwork": "B53",
    "initiative": "B61",
    "continuousLearning": "B69",
}

KPI_OPTION_FIELDS = {
    "breakfastMeeting": {"cell": "F85", "options": {"Hadir", "Tidak Hadir"}},
    "emergencyLeaveAttendance": {"cell": "F86", "options": {"Tiada", "0.5 Hari", "1 Hari", "1.5 Hari", "2 Hari", "2.5 Hari", "Lebih 3 Hari"}},
    "medicalLeaveAttendance": {"cell": "F87", "options": {"Tiada", "1 Hari", "2 Hari", "3 Hari", "4 Hari", "5 Hari", "Lebih 6 Hari"}},
    "biroAgama": {"cell": "F90", "options": {"1", "2", "Tiada"}},
    "biroSukan": {"cell": "F91", "options": {"1", "2", "Tiada"}},
    "trainingHours": {"cell": "F94", "options": {"Hadir", "Tiada"}},
    "committeeRole": {"cell": "F95", "options": {"Pengerusi", "Naib Pengerusi", "Setiausaha", "AJK", "Tiada"}},
    "eqariah": {"cell": "F98", "options": {"Ya", "Tiada"}},
}

EXPENSE_AMOUNT_FIELDS = (
    "totalKm",
    "parking",
    "toll",
    "hotel",
    "flight",
    "medical",
    "phone",
    "entertainment",
    "travelAllowance",
    "misc",
)
EXPENSE_TRANSPORT_RATES = {
    "car": 0.87,
    "motorcycle": 0.60,
}

OT_RATE_TYPES = {
    "normal": 1.5,
    "rest": 2.0,
    "holiday": 3.0,
}
OT_MAX_ITEMS = 17
OT_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3])[0-5]\d$")


def normalize_worker_id(worker_id: str | None) -> str:
    return (worker_id or "").strip().upper()


def sanitize_file_part(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", str(value or ""))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:80] or "file"


def parse_iso_date(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must use yyyy-mm-dd format.") from exc


def to_iso_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_year_month(value: str | None, field_name: str) -> date:
    try:
        return datetime.strptime(str(value or ""), "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use yyyy-mm format.") from exc


def end_of_month(start_of_month: date) -> date:
    if start_of_month.month == 12:
        return date(start_of_month.year, 12, 31)
    return date(start_of_month.year, start_of_month.month + 1, 1) - timedelta(days=1)


def format_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def current_year_bounds() -> tuple[date, date]:
    year = date.today().year
    return date(year, 1, 1), date(year, 12, 31)


def get_leave_period(worker: dict) -> tuple[str, date, date]:
    employment_type = str(worker.get("employmentType") or "permanent").strip().lower()
    if employment_type not in {"permanent", "contract"}:
        employment_type = "permanent"

    year_start, year_end = current_year_bounds()
    if employment_type == "permanent":
        return employment_type, year_start, year_end

    start = parse_optional_date(worker.get("employmentStartDate")) or year_start
    end = parse_optional_date(worker.get("employmentEndDate")) or year_end
    if end < start:
        start, end = year_start, year_end
    return employment_type, start, end


def affects_annual_leave(submission: dict) -> bool:
    leave_type = str(submission.get("leaveType") or "").strip().lower()
    if leave_type:
        return leave_type in AL_DEDUCTING_LEAVE_TYPES

    if "affectsAnnualLeave" in submission:
        return submission.get("affectsAnnualLeave") is True

    form_type = str(submission.get("formType") or "").strip().upper()
    form_text = " ".join(
        str(submission.get(field) or "")
        for field in ("formName", "leaveTypeLabel", "id", "pdfFileName", "workbookFileName")
    ).lower()
    if any(keyword in form_text for keyword in ("unpaid", "other")):
        return False
    if any(keyword in form_text for keyword in ("emergency", "_el_", "el-")):
        return True

    return form_type in {"AL", "EL"}


def count_al_taken_from_list(worker_id: str, period_start: date, period_end: date, submissions: list[dict]) -> float:
    total = 0.0
    normalized = normalize_worker_id(worker_id)
    for item in submissions:
        if normalize_worker_id(item.get("workerId")) != normalized:
            continue
        if not affects_annual_leave(item):
            continue
        duration = item.get("durationDays")
        if duration is not None:
            total += float(duration)
            continue
        start = parse_optional_date(item.get("calendarStart") or item.get("startDate"))
        end = parse_optional_date(item.get("calendarEnd") or item.get("endDate"))
        if not start or not end:
            continue
        overlap_start = max(start, period_start)
        overlap_end = min(end, period_end)
        if overlap_end >= overlap_start:
            total += float((overlap_end - overlap_start).days + 1)
    return total


def enrich_worker(worker: dict, taken_to_date: float = 0.0) -> dict:
    enriched = dict(worker)
    employment_type, period_start, period_end = get_leave_period(enriched)
    entitlement = float(enriched.get("annualLeaveEntitlement") or 0)
    balance = max(entitlement - taken_to_date, 0)

    enriched["employmentType"] = employment_type
    enriched["employmentStartDate"] = period_start.isoformat()
    enriched["employmentEndDate"] = period_end.isoformat()
    enriched["annualLeaveEntitlement"] = format_number(entitlement)
    enriched["annualLeaveTaken"] = format_number(taken_to_date)
    enriched["annualLeaveBalance"] = format_number(balance)
    return enriched


def get_leave_summary(worker: dict, duration_days: float) -> dict:
    entitlement = float(worker.get("annualLeaveEntitlement") or 0)
    taken_to_date = float(worker.get("annualLeaveTaken") or 0)
    applied_days = max(float(duration_days or 0), 0)
    balance_before = max(entitlement - taken_to_date, 0)
    balance_after = max(entitlement - taken_to_date - applied_days, 0)
    return {
        "entitlement": format_number(entitlement),
        "takenToDate": format_number(taken_to_date),
        "balanceBefore": format_number(balance_before),
        "balanceAfter": format_number(balance_after),
    }


def clean_profile_value(value) -> str:
    return str(value or "").strip()


NAME_PARTICLES = {"bin", "binti", "bt", "ibn", "al", "a/l", "a/p"}
PROFILE_TEXT_ACRONYMS = {
    "AL",
    "CEO",
    "CFO",
    "COO",
    "CTO",
    "DB",
    "EL",
    "HR",
    "HSE",
    "IT",
    "KPI",
    "MC",
    "PDF",
    "QA",
    "QC",
    "R&D",
    "SQL",
}


def _standardize_profile_token(token: str, *, is_name: bool, is_first: bool = False) -> str:
    lower_token = token.lower()
    upper_token = token.upper()
    if is_name and not is_first and lower_token in NAME_PARTICLES:
        return lower_token
    if upper_token in PROFILE_TEXT_ACRONYMS:
        return upper_token

    parts = re.split(r"([-/'&])", lower_token)
    return "".join(
        part.upper() if part.upper() in PROFILE_TEXT_ACRONYMS
        else part.capitalize() if part and part not in "-/'&"
        else part
        for part in parts
    )


def standardize_profile_text(value, *, is_name: bool = False) -> str:
    cleaned = re.sub(r"\s+", " ", clean_profile_value(value))
    if not cleaned:
        return ""

    tokens = cleaned.split(" ")
    return " ".join(
        _standardize_profile_token(token, is_name=is_name, is_first=index == 0)
        for index, token in enumerate(tokens)
    )


def parse_non_negative_number(value, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number.") from exc
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def parse_optional_non_negative_number(value, field_name: str) -> float:
    if value in (None, ""):
        return 0.0
    return parse_non_negative_number(value, field_name)


def normalize_leave_type(value: str | None) -> str:
    leave_type = str(value or "").strip().lower()
    if leave_type not in LEAVE_TYPES:
        raise ValueError("Select one leave type.")
    return leave_type


def parse_kpi_score(value, field_name: str) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a whole number from 1 to 5.") from exc
    if score < 1 or score > 5:
        raise ValueError(f"{field_name} must be a whole number from 1 to 5.")
    return score


def parse_kpi_option(value, field_name: str, options: set) -> str:
    normalized = clean_profile_value(value)
    if normalized not in options:
        raise ValueError(f"{field_name} must be one of: {', '.join(sorted(options))}.")
    return normalized


def parse_kpi_scores(body: dict) -> dict:
    scores = {}
    for section_key, cells in KPI_SCORE_CELLS.items():
        values = body.get("scores", {}).get(section_key)
        if not isinstance(values, list) or len(values) != len(cells):
            raise ValueError(f"{section_key} scores are required.")
        scores[section_key] = [
            parse_kpi_score(value, f"{section_key} score {index + 1}")
            for index, value in enumerate(values)
        ]
    return scores


def parse_kpi_comments(body: dict) -> dict:
    return {
        section_key: clean_profile_value(body.get("comments", {}).get(section_key))
        for section_key in KPI_COMMENT_CELLS
    }


def parse_kpi_options(body: dict) -> dict:
    options = {}
    for field_key, config in KPI_OPTION_FIELDS.items():
        options[field_key] = parse_kpi_option(
            body.get("summaryOptions", {}).get(field_key),
            field_key,
            config["options"],
        )
    return options


def format_kpi_month_label(month_start: date) -> str:
    return month_start.strftime("%B %Y").upper()


def _ot_hours(time_from: str, time_to: str) -> float:
    start_minutes = int(time_from[:2]) * 60 + int(time_from[2:])
    end_minutes = int(time_to[:2]) * 60 + int(time_to[2:])
    minutes = end_minutes - start_minutes
    if minutes <= 0:
        minutes += 24 * 60
    return round(minutes / 60, 2)


def _ot_day_label(parsed_date: datetime, overnight: bool) -> str:
    if overnight:
        next_day = parsed_date + timedelta(days=1)
        return f"{parsed_date.strftime('%a')} - {next_day.strftime('%a')}"
    return parsed_date.strftime("%A")


def parse_ot_items(body: dict) -> list[dict]:
    raw_items = body.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Overtime items are required.")

    items = []
    for index, raw_item in enumerate(raw_items[:OT_MAX_ITEMS], start=1):
        if not isinstance(raw_item, dict):
            continue

        date_value = clean_profile_value(raw_item.get("date"))
        time_from = clean_profile_value(raw_item.get("timeFrom"))
        time_to = clean_profile_value(raw_item.get("timeTo"))
        description = clean_profile_value(raw_item.get("description"))
        rate_type = clean_profile_value(raw_item.get("rateType")).lower() or "normal"

        if not date_value and not time_from and not time_to and not description:
            continue

        if rate_type not in OT_RATE_TYPES:
            raise ValueError(f"row {index} rate type is invalid.")
        parsed_date = parse_iso_date(date_value, f"row {index} date")
        if not OT_TIME_PATTERN.match(time_from):
            raise ValueError(f"row {index} time from must use 24-hour HHMM format (e.g. 1800).")
        if not OT_TIME_PATTERN.match(time_to):
            raise ValueError(f"row {index} time to must use 24-hour HHMM format (e.g. 2200).")
        if time_to == time_from:
            raise ValueError(f"row {index} time to cannot equal time from.")
        if not description:
            raise ValueError(f"row {index} description is required.")

        hours = _ot_hours(time_from, time_to)
        overnight = time_to < time_from
        items.append({
            "date": to_iso_date(parsed_date),
            "dayLabel": _ot_day_label(parsed_date, overnight),
            "timeFrom": time_from,
            "timeTo": time_to,
            "rateType": rate_type,
            "hours": format_number(hours),
            "description": description,
        })

    if not items:
        raise ValueError("Add at least one overtime item.")
    return items


def parse_expense_items(body: dict) -> list[dict]:
    raw_items = body.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Expense items are required.")

    items = []
    for index, raw_item in enumerate(raw_items[:13], start=1):
        if not isinstance(raw_item, dict):
            continue

        date_value = clean_profile_value(raw_item.get("date"))
        description = clean_profile_value(raw_item.get("description"))
        project = clean_profile_value(raw_item.get("project"))
        transport_mode = clean_profile_value(raw_item.get("transportMode")).lower() or "car"
        if transport_mode not in EXPENSE_TRANSPORT_RATES:
            raise ValueError(f"row {index} transport mode is invalid.")
        amount_values = {
            field_key: parse_optional_non_negative_number(raw_item.get(field_key), f"row {index} {field_key}")
            for field_key in EXPENSE_AMOUNT_FIELDS
        }
        has_amount = any(value > 0 for value in amount_values.values())
        has_text = bool(date_value or description or project)
        if not has_text and not has_amount:
            continue

        parsed_date = parse_iso_date(date_value, f"row {index} date")
        if not description:
            raise ValueError(f"row {index} description is required.")

        mileage = amount_values["totalKm"] * EXPENSE_TRANSPORT_RATES[transport_mode]
        total = mileage + sum(
            amount_values[field_key]
            for field_key in EXPENSE_AMOUNT_FIELDS
            if field_key != "totalKm"
        )
        items.append({
            "date": to_iso_date(parsed_date),
            "description": description,
            "project": project,
            "transportMode": transport_mode,
            **{field_key: format_number(value) for field_key, value in amount_values.items()},
            "mileage": round(mileage, 2),
            "total": round(total, 2),
        })

    if not items:
        raise ValueError("Add at least one expense item.")
    return items
