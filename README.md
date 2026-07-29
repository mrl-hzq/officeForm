# Office Form PDF System

Web-based office form system for Worker ID registration/login, profile setup, AL/EL/MC/KPI/Expense submission, PDF output, saved records, and shared calendar visibility.

## Tech Stack

- Frontend: plain HTML, CSS, and JavaScript in `public/`
- Backend: modular Flask app in `app/`
- Entry point: `app_entry.py`
- Database: MySQL via PyMySQL
- Auth: JWT with Worker ID plus a deployment-wide shared password
- Template filling: LibreOffice headless UNO actions for AL/MC/Expense/OT; KPI tries Excel COM first and falls back to LibreOffice
- PDF output: Excel-template export to PDF using mapped workbook templates
- Generated files: `generated/pdfs/` and `generated/workbooks/`

## Run

Prerequisites:

- Python 3
- LibreOffice installed on the machine running the app for AL/MC/Expense PDF export
- Microsoft Excel with `pywin32` is optional for the KPI preferred export path; KPI falls back to LibreOffice
- MySQL configured from `.env`
- Python packages from `requirements.txt`

Set `AUTH_SHARED_PASSWORD` in `.env` before exposing the application. Login and
registration both require this shared password; it defaults to `abcd1234` only
for initial setup and should be changed for deployment.

### Switching local database targets

When running `python app_entry.py`, `.env` selects the database. Uncomment all
five lines in exactly one target block because the targets use different hosts,
ports, and credentials:

```dotenv
# Local MySQL
DB_HOST=172.31.176.1
DB_PORT=3306
DB_NAME=officeform
DB_USER=root
DB_PASSWORD=root

# Docker MySQL published by docker-compose.yml
# DB_HOST=127.0.0.1
# DB_PORT=3307
# DB_NAME=officeform
# DB_USER=officeform
# DB_PASSWORD=officeform_pass
```

```powershell
.\.venv\Scripts\activate
python app_entry.py
```

Or:

```powershell
npm start
```

Then open:

```text
http://127.0.0.1:3000
```

## Run With Docker Compose

By default this starts the web app against local Windows MySQL through
`host.docker.internal:3306`.

```powershell
docker compose up --build
```

Then open:

```text
http://127.0.0.1:3000
```

The Docker web image includes LibreOffice headless for Excel-template PDF export,
so it does not require Microsoft Excel, `pywin32`, or a separate Windows PDF
worker.

To use the Docker MySQL service, comment the complete
`DB_SERVER=host.docker.internal` target block, uncomment the complete
`DB_SERVER=db` target block, and start its profile:

```powershell
docker compose --profile docker-db up --build
```

The Docker database is published to Windows as `127.0.0.1:3307`.


## Database

Create local tables:

```powershell
python scripts/setup_local_db.py
```

Migrate old JSON data into MySQL if needed:

```powershell
python scripts/migrate_json_to_mysql.py
```

The old JSON files in `data/` are migration/backup inputs, not the active backend storage.

## Current Scope

- Users register with Worker ID and the shared access password, then complete profile setup.
- After profile setup, login opens the main workspace.
- AL/EL leave form, MC form, KPI form, Expense Claim form, and Overtime Claim form are ready for testing.
- AL and EL reduce annual leave balance. Unpaid, Other, and MC do not.
- KPI submissions are tracked by month in the Profile tab for the current year.
- Personal generated records are saved in MySQL and shown in History.
- Calendar shows shared AL/EL/MC visibility across users.
- Others shows shared uploaded PDFs, with upload/delete controls for admin users.

## Google Sheets Calendar Sync

Successful AL/EL/MC submissions best-effort append a labeled line into the worker's
day cell of the shared Google Spreadsheet calendar tab (`2026` by default). KPI, OT,
and Expense Claim are not synced. Sync is opt-in via `GOOGLE_SHEETS_ENABLED=1` plus
`GOOGLE_CREDENTIALS_PATH`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_TAB` in `.env`. See
`AGENTS.md` for the full setup (service-account credentials, sheet sharing, schema).

Existing DBs need a one-time column:

```sql
ALTER TABLE submissions ADD COLUMN sheets_synced_at DATETIME NULL;
```

### Backlog and verify

`scripts/sync_google_sheets_backlog.py` reconciles the spreadsheet against the DB.
It is idempotent (cell-level exact-line dedup) and safe to re-run.

Native:

```powershell
python scripts/sync_google_sheets_backlog.py --dry-run
python scripts/sync_google_sheets_backlog.py
```

Docker:

```bash
sudo docker exec officeform-web-1 python scripts/sync_google_sheets_backlog.py --dry-run
sudo docker exec officeform-web-1 python scripts/sync_google_sheets_backlog.py
```

Modes and flags:

| Command | What it does |
|---|---|
| `--dry-run` | Report planned writes / missing lines without applying |
| `--worker-id <id>` | Restrict to one Worker ID |
| `--since YYYY-MM-DD` | Only submissions with `start_date >=` that date |
| `--verify` | Re-check EVERY AL/EL/MC submission against the sheet and re-write missing lines (reconciles manual edits/deletions). Ignores `sheets_synced_at`. |
| `--verify --dry-run` | Detect missing lines without writing |

Use the default (no `--verify`) to catch rows that never synced. Use `--verify` when
the dry-run reports nothing unsynced but lines are missing from the sheet (e.g. someone
deleted or edited a line manually).

Per-worker sync status:

```bash
sudo docker exec officeform-db-1 mysql -uroot -proot officeform -e "SELECT worker_id, MAX(sheets_synced_at) AS last_synced, COUNT(*) AS synced_count FROM submissions WHERE sheets_synced_at IS NOT NULL GROUP BY worker_id ORDER BY last_synced DESC;"
```

Unsynced rows per worker:

```bash
sudo docker exec officeform-db-1 mysql -uroot -proot officeform -e "SELECT worker_id, COUNT(*) AS unsynced FROM submissions WHERE form_type IN ('AL','EL','MC') AND sheets_synced_at IS NULL GROUP BY worker_id;"
```
