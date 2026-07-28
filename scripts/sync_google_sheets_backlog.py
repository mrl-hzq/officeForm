"""One-shot backlog sync of historical AL/EL/MC submissions into Google Sheets.

Idempotent: skips rows already synced (sheets_synced_at IS NOT NULL) and
skips cells already containing the exact planned label line. Re-runnable.

Usage:
    python scripts/sync_google_sheets_backlog.py                # sync all unsynced
    python scripts/sync_google_sheets_backlog.py --dry-run      # report only
    python scripts/sync_google_sheets_backlog.py --worker-id C0036
    python scripts/sync_google_sheets_backlog.py --since 2026-01-01
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
from app.google_sheets import calendar_display_name, append_calendar_entry, date_range


def _sheets_label(form_type: str, display_name: str, is_half_day: bool, half_day_period: str | None) -> str:
    if form_type == "MC":
        return f"{display_name} (MC)"
    code = "AL" if form_type == "AL" else "EL"
    if is_half_day:
        period = (half_day_period or "").upper() or "AM"
        return f"{display_name} ({code} {period})"
    return f"{display_name} ({code})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backlog-sync AL/EL/MC submissions to Google Sheets")
    parser.add_argument("--dry-run", action="store_true", help="Report planned writes without applying")
    parser.add_argument("--worker-id", default="", help="Restrict to one Worker ID")
    parser.add_argument("--since", default="", help="Only submissions with start_date >= YYYY-MM-DD")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        sql = """SELECT * FROM submissions
                 WHERE form_type IN ('AL','EL','MC')
                   AND sheets_synced_at IS NULL"""
        params: list = []
        if args.worker_id:
            sql += " AND worker_id = %s"
            params.append(args.worker_id)
        if args.since:
            sql += " AND start_date >= %s"
            params.append(args.since)
        sql += " ORDER BY start_date ASC, created_at ASC"
        rows = query(sql, tuple(params))

        print(f"Found {len(rows)} unsynced AL/EL/MC submissions.")
        total_written = 0
        total_skipped = 0
        total_errors = 0
        for row in rows:
            snap_raw = row.get("worker_snapshot")
            snap = json.loads(snap_raw) if isinstance(snap_raw, str) else (snap_raw or {})
            display_name = calendar_display_name(snap.get("name"), row.get("worker_id"))
            label = _sheets_label(row["form_type"], display_name, bool(row.get("is_half_day")), row.get("half_day_period"))
            start_d = row["start_date"] if isinstance(row["start_date"], date) else datetime.fromisoformat(str(row["start_date"])).date()
            end_d = row["end_date"] if isinstance(row["end_date"], date) else datetime.fromisoformat(str(row["end_date"])).date()
            row_written = 0
            row_skipped = 0
            row_errors = 0
            for d in date_range(start_d, end_d):
                if args.dry_run:
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

        print(f"\nDone. written={total_written} skipped={total_skipped} errors={total_errors}")
        return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())