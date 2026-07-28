from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

from flask import current_app

logger = logging.getLogger(__name__)

_client_cache = threading.local()

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_CONNECTORS = {"bin", "binti", "bt", "a/l", "a/p"}


def build_calendar_label(form_type: str, display_name: str, is_half_day: bool, half_day_period: str | None) -> str:
    """Build the '<Name> (<Form>)' line written into calendar cells."""
    if form_type == "MC":
        return f"{display_name} (MC)"
    code = "AL" if form_type == "AL" else "EL"
    if is_half_day:
        period = (half_day_period or "").upper() or "AM"
        return f"{display_name} ({code} {period})"
    return f"{display_name} ({code})"


def calendar_display_name(name: str | None, worker_id: str | None = "", calendar_name: str | None = None) -> str:
    """If `calendar_name` is set, use it. Otherwise port of public/app.js getCalendarDisplayName:
    token before bin/binti connector, else first token."""
    if calendar_name:
        cleaned = str(calendar_name).strip()
        if cleaned:
            return cleaned
    parts = [p for p in str(name or worker_id or "").strip().split() if p]
    if not parts:
        return "-"
    for i, token in enumerate(parts):
        if token.lower() in _CONNECTORS and i > 0:
            return parts[i - 1]
    return parts[0]


def _client():
    import gspread  # lazy import so a missing dep never crashes app boot
    if not getattr(_client_cache, "gc", None):
        path = current_app.config["GOOGLE_CREDENTIALS_PATH"]
        _client_cache.gc = gspread.service_account(filename=path)
    return _client_cache.gc


def _column_letter(gspread_col: int) -> str:
    # gspread_col 1 -> A, 2 -> B, 8 -> H
    result = ""
    n = gspread_col
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord("A") + rem) + result
    return result


def _locate_target_cell(sh, target: date) -> str | None:
    """Find the content cell A1 address for `target` in the 2-row-week month block layout.

    Layout (your 2026 tab): col A is an empty margin; month title in col B (row R),
    weekday headers Mon..Sun in cols B..H, day numbers and content in the same cols.
    """
    title = f"{_MONTH_NAMES[target.month - 1]} {target.year}"
    try:
        cell = sh.find(title, in_column=2)
    except Exception as exc:
        logger.warning("Google Sheets: month-title lookup failed for %s: %s", title, exc)
        return None
    if not cell:
        logger.warning("Google Sheets: month block %s not found in tab", title)
        return None
    first_number_row = cell.row + 2

    day_one_col_idx = None  # 0..6 = Mon..Sun
    for col_idx in range(7):
        try:
            val = sh.cell(first_number_row, col_idx + 2).value  # cols B..H = gspread 2..8
        except Exception:
            continue
        if val is not None and str(val).strip() == "1":
            day_one_col_idx = col_idx
            break
    if day_one_col_idx is None:
        logger.warning("Google Sheets: could not find day-1 cell for %s", title)
        return None

    weekday_mon0 = target.weekday()
    week = (target.day - 1 + day_one_col_idx) // 7
    content_row = cell.row + 3 + 2 * week
    col_gspread = weekday_mon0 + 2  # Mon -> col 2 (B), Sun -> col 8 (H)
    return f"{_column_letter(col_gspread)}{content_row}"


def _read_cell(sh, a1: str) -> str:
    try:
        return sh.acell(a1, value_render_option="FORMULA").value or ""
    except Exception:
        return sh.acell(a1).value or ""


def _write_cell(sh, a1: str, value: str) -> None:
    sh.update_acell(a1, value)


def append_calendar_entry(target_date: date, label: str) -> bool:
    """Append `label` as a new line in the target day cell. Idempotent on exact full-line match.

    Returns True if written, False if skipped (already present / disabled / not found).
    Never raises.
    """
    cfg = current_app.config
    if not cfg.get("GOOGLE_SHEETS_ENABLED"):
        return False
    if not cfg.get("GOOGLE_CREDENTIALS_PATH") or not cfg.get("GOOGLE_SHEET_ID"):
        logger.warning("Google Sheets sync skipped: credentials or sheet id not configured")
        return False

    try:
        gc = _client()
        sh = gc.open_by_key(cfg["GOOGLE_SHEET_ID"]).worksheet(cfg["GOOGLE_SHEET_TAB"])
        a1 = _locate_target_cell(sh, target_date)
        if not a1:
            return False
        existing = _read_cell(sh, a1)
        lines = [ln.strip() for ln in existing.split("\n")]
        if label in lines:
            return False
        new_value = (existing + "\n" + label) if existing else label
        _write_cell(sh, a1, new_value)
        return True
    except Exception as exc:
        logger.warning("Google Sheets sync failed for %s (%s): %s", target_date, label, exc)
        return False


def remove_calendar_line(target_date: date, label: str) -> bool:
    """Remove `label` (exact full-line match) from the target day cell. Idempotent.

    Returns True if a line was removed, False otherwise (absent / disabled / not found).
    Never raises. Legacy hand-entered rows never match the `<Name> (<Form>)` format
    and are left untouched.
    """
    cfg = current_app.config
    if not cfg.get("GOOGLE_SHEETS_ENABLED"):
        return False
    if not cfg.get("GOOGLE_CREDENTIALS_PATH") or not cfg.get("GOOGLE_SHEET_ID"):
        logger.warning("Google Sheets sync skipped: credentials or sheet id not configured")
        return False

    try:
        gc = _client()
        sh = gc.open_by_key(cfg["GOOGLE_SHEET_ID"]).worksheet(cfg["GOOGLE_SHEET_TAB"])
        a1 = _locate_target_cell(sh, target_date)
        if not a1:
            return False
        existing = _read_cell(sh, a1)
        lines = existing.split("\n")
        stripped = [ln.strip() for ln in lines]
        if label not in stripped:
            return False
        kept = [ln for ln in lines if ln.strip() != label]
        new_value = "\n".join(kept)
        _write_cell(sh, a1, new_value)
        return True
    except Exception as exc:
        logger.warning("Google Sheets removal failed for %s (%s): %s", target_date, label, exc)
        return False


def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def replace_calendar_line(target_date: date, old_label: str, new_label: str) -> bool:
    """Rename an exact full-line match from `old_label` to `new_label` in the target day cell.

    Idempotent: if `old_label` is absent, no-op. Legacy hand-entered rows never match and are
    left untouched. Returns True if a line was replaced. Never raises.
    """
    cfg = current_app.config
    if not cfg.get("GOOGLE_SHEETS_ENABLED"):
        return False
    if not cfg.get("GOOGLE_CREDENTIALS_PATH") or not cfg.get("GOOGLE_SHEET_ID"):
        logger.warning("Google Sheets sync skipped: credentials or sheet id not configured")
        return False

    try:
        gc = _client()
        sh = gc.open_by_key(cfg["GOOGLE_SHEET_ID"]).worksheet(cfg["GOOGLE_SHEET_TAB"])
        a1 = _locate_target_cell(sh, target_date)
        if not a1:
            return False
        existing = _read_cell(sh, a1)
        lines = existing.split("\n")
        found = False
        new_lines = []
        for ln in lines:
            if ln.strip() == old_label:
                new_lines.append(new_label)
                found = True
            else:
                new_lines.append(ln)
        if not found:
            return False
        _write_cell(sh, a1, "\n".join(new_lines))
        return True
    except Exception as exc:
        logger.warning("Google Sheets rename failed for %s (%s -> %s): %s", target_date, old_label, new_label, exc)
        return False