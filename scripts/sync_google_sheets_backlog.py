"""One-shot backlog sync of historical AL/EL/MC submissions into Google Sheets.

Idempotent: skips rows already synced (sheets_synced_at IS NOT NULL) and
skips cells already containing the exact planned label line. Re-runnable.

Usage:
    python scripts/sync_google_sheets_backlog.py                # sync all unsynced
    python scripts/sync_google_sheets_backlog.py --dry-run      # report only
    python scripts/sync_google_sheets_backlog.py --worker-id C0036
    python scripts/sync_google_sheets_backlog.py --since 2026-01-01

Verify mode (reconcile manual sheet edits / deletions):
    python scripts/sync_google_sheets_backlog.py --verify
    python scripts/sync_google_sheets_backlog.py --verify --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.db import query
from app.google_sheets import calendar_display_name, append_calendar_entry, cell_has_line, date_range, build_calendar_label


def _sheets_label(form_type: str, display_name: str, is_half_day: bool, half_day_period: str | None) -> str:
    return build_calendar_label(form_type, display_name, is_half_day, half_day_period)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backlog-sync AL/EL/MC submissions to Google Sheets")
    parser.add_argument("--dry-run", action="store_true", help="Report planned writes without applying")
    parser.add_argument("--worker-id", default="", help="Restrict to one Worker ID")
    parser.add_argument("--since", default="", help="Only submissions with start_date >= YYYY-MM-DD")
    parser.add_argument("--verify", action="store_true",
                        help="Re-check EVERY AL/EL/MC submission against the sheet and re-write missing lines "
                             "(reconciles manual edits/deletions). Ignores sheets_synced_at.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        sql = """SELECT s.*, w.calendar_name AS worker_calendar_name, w.name AS worker_name
                 FROM submissions s
                 LEFT JOIN workers w ON w.worker_id = s.worker_id
                 WHERE s.form_type IN ('AL','EL','MC')"""
        if not args.verify:
            sql += " AND s.sheets_synced_at IS NULL"
        params: list = []
        if args.worker_id:
            sql += " AND s.worker_id = %s"
            params.append(args.worker_id)
        if args.since:
            sql += " AND s.start_date >= %s"
            params.append(args.since)
        sql += " ORDER BY s.start_date ASC, s.created_at ASC"
        rows = query(sql, tuple(params))

        mode = "verify" if args.verify else "unsynced"
        print(f"Found {len(rows)} AL/EL/MC submissions ({mode}).")
        total_written = 0
        total_skipped = 0
        total_errors = 0
        total_missing = 0
        for row in rows:
            snap_raw = row.get("worker_snapshot")
            snap = json.loads(snap_raw) if isinstance(snap_raw, str) else (snap_raw or {})
            worker_override = {
                "name": row.get("worker_name") or snap.get("name"),
                "calendarName": row.get("worker_calendar_name") or snap.get("calendarName"),
            }
            display_name = calendar_display_name(worker_override["name"], row.get("worker_id"), worker_override["calendarName"])
            label = _sheets_label(row["form_type"], display_name, bool(row.get("is_half_day")), row.get("half_day_period"))
            start_d = row["start_date"] if isinstance(row["start_date"], date) else datetime.fromisoformat(str(row["start_date"])).date()
            end_d = row["end_date"] if isinstance(row["end_date"], date) else datetime.fromisoformat(str(row["end_date"])).date()
            row_written = 0
            row_skipped = 0
            row_errors = 0
            row_missing = 0
            for d in date_range(start_d, end_d):
                if args.dry_run:
                    if args.verify:
                        present = cell_has_line(d, label)
                        if present is False:
                            print(f"  [dry-run][missing] {d.isoformat()}  {label}  ({row['id']})")
                            row_missing += 1
                        elif present is True:
                            row_skipped += 1
                        else:
                            print(f"  [dry-run][unreachable] {d.isoformat()}  {label}  ({row['id']})", file=sys.stderr)
                            row_errors += 1
                    else:
                        print(f"  [dry-run] {d.isoformat()}  {label}  ({row['id']})")
                        row_skipped += 1
                    continue
                try:
                    if append_calendar_entry(d, label):
                        print(f"  wrote  {d.isoformat()}  {label}  ({row['id']})")
                        row_written += 1
                    else:
                        row_skipped += 1
                except Exception as exc:
                    print(f"  ERROR  {d.isoformat()}  {label}  ({row['id']}): {exc}", file=sys.stderr)
                    row_errors += 1
            if not args.dry_run and row_written > 0 and row_errors == 0:
                from app.db import execute
                execute("UPDATE submissions SET sheets_synced_at = %s WHERE id = %s",
                        (datetime.now(timezone.utc).replace(microsecond=0), row["id"]))
            total_written += row_written
            total_skipped += row_skipped
            total_errors += row_errors
            total_missing += row_missing

        suffix = f" missing={total_missing}" if (args.verify and args.dry_run) else ""
        print(f"\nDone. written={total_written} skipped={total_skipped} errors={total_errors}{suffix}")
        return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())