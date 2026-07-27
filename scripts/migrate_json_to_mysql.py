"""One-time migration: loads data/workers.json and data/submissions.json into MySQL.

Run from the project root with the .venv active:
    python scripts/migrate_json_to_mysql.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import pymysql
import pymysql.cursors
from app.config import Config

WORKERS_FILE = ROOT / "data" / "workers.json"
SUBMISSIONS_FILE = ROOT / "data" / "submissions.json"


def get_conn():
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def migrate_workers(cursor, workers: dict) -> int:
    count = 0
    for worker_id, w in workers.items():
        cursor.execute(
            """INSERT INTO workers
               (worker_id, name, designation, department, house_tel, other_tel,
                evaluator_name, annual_leave_entitlement, annual_leave_taken,
                employment_type, employment_start_date, employment_end_date, profile_complete)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                 name = VALUES(name),
                 designation = VALUES(designation),
                 department = VALUES(department),
                 house_tel = VALUES(house_tel),
                 other_tel = VALUES(other_tel),
                 evaluator_name = VALUES(evaluator_name),
                 annual_leave_entitlement = VALUES(annual_leave_entitlement),
                 employment_type = VALUES(employment_type),
                 employment_start_date = VALUES(employment_start_date),
                 employment_end_date = VALUES(employment_end_date),
                 profile_complete = VALUES(profile_complete)""",
            (
                worker_id,
                w.get("name", worker_id),
                w.get("designation"),
                w.get("department"),
                w.get("houseTel"),
                w.get("otherTel"),
                w.get("evaluatorName"),
                float(w.get("annualLeaveEntitlement") or 0),
                float(w.get("annualLeaveTaken") or 0),
                w.get("employmentType", "permanent"),
                w.get("employmentStartDate"),
                w.get("employmentEndDate"),
                True,  # existing workers have complete profiles
            ),
        )
        # Also create a users row so they can log in
        cursor.execute(
            "INSERT INTO users (worker_id) VALUES (%s) ON DUPLICATE KEY UPDATE worker_id = worker_id",
            (worker_id,),
        )
        count += 1
        print(f"  Worker: {worker_id} — {w.get('name')}")
    return count


def migrate_submissions(cursor, submissions: list) -> int:
    count = 0
    for s in submissions:
        sub_id = s.get("id")
        if not sub_id:
            continue
        worker_id = (s.get("workerId") or "").strip().upper()

        # Skip if worker doesn't exist in DB (referential integrity)
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = %s", (worker_id,))
        if not cursor.fetchone():
            print(f"  Skipping submission {sub_id}: worker {worker_id} not in DB")
            continue

        cursor.execute(
            """INSERT INTO submissions
               (id, worker_id, form_type, form_name, leave_type, start_date, end_date,
                duration_days, affects_al, al_days_applied, reason, kpi_month,
                application_date, kpi_data, worker_snapshot, leave_summary,
                pdf_file_name, workbook_file_name, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE id = id""",
            (
                sub_id,
                worker_id,
                s.get("formType"),
                s.get("formName"),
                s.get("leaveType"),
                s.get("startDate"),
                s.get("endDate"),
                s.get("durationDays"),
                bool(s.get("affectsAnnualLeave")),
                int(s.get("annualLeaveDaysApplied") or 0),
                s.get("reason"),
                s.get("kpiMonth"),
                s.get("applicationDate"),
                json.dumps(s.get("kpiData")) if s.get("kpiData") else None,
                json.dumps(s.get("workerSnapshot")) if s.get("workerSnapshot") else None,
                json.dumps(s.get("leaveSummary")) if s.get("leaveSummary") else None,
                s.get("pdfFileName"),
                s.get("workbookFileName"),
                s.get("createdAt", "").replace("Z", "").replace("T", " ")[:19] or None,
            ),
        )
        count += 1
        print(f"  Submission: {sub_id} ({s.get('formType')})")
    return count


def main():
    print("Connecting to MySQL...")
    conn = get_conn()
    cursor = conn.cursor()

    print("\nMigrating workers...")
    workers = json.loads(WORKERS_FILE.read_text(encoding="utf-8-sig")) if WORKERS_FILE.exists() else {}
    w_count = migrate_workers(cursor, workers)
    print(f"  Done: {w_count} worker(s).")

    print("\nMigrating submissions...")
    submissions = json.loads(SUBMISSIONS_FILE.read_text(encoding="utf-8-sig")) if SUBMISSIONS_FILE.exists() else []
    s_count = migrate_submissions(cursor, submissions)
    print(f"  Done: {s_count} submission(s).")

    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
