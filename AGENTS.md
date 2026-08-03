# officeForm Agent Guide

This document gives future coding sessions the current working context for this repo.

## Current Architecture

- This project uses the new modular Flask backend in `app/`.
- The old single-file backend `app.py` has been removed.
- The active entry point is `app_entry.py`.
- `npm start` is configured to run `python app_entry.py`.
- Frontend files live in `public/`.
- MySQL is the active storage backend. Old JSON files, if present, are migration/backup inputs only.
- PDF generation now primarily uses LibreOffice headless through `scripts/libreoffice_export.py` and `scripts/libreoffice_uno_bridge.py`.
- KPI PDF generation first tries Microsoft Excel COM automation through `pywin32`, then falls back to LibreOffice plus `pypdf` page imposition.
- Docker runs the Flask app through Gunicorn with LibreOffice installed and does not include `pywin32`.
- Docker images include `formOri/` so PDF templates are available without a host template mount in K3s. Development Compose still mounts the local directory read-only for immediate template testing.

## Run Commands

From `C:\Homelab\officeForm`:

```powershell
.\.venv\Scripts\activate
python app_entry.py
```

Or:

```powershell
npm start
```

Open:

```text
http://127.0.0.1:3000
```

Validation:

```powershell
npm run check
node --check public\app.js
```

Docker:

```powershell
docker compose up --build
```

Docker Compose starts `web` against local Windows MySQL by default using `host.docker.internal:3306`. The `db` service is opt-in through the `docker-db` profile.

## Current Docker Image

- Docker Compose project name: `officeform`.
- Compose service: `web`.
- Because `docker-compose.yml` has `build: .` and no explicit `image:` setting, Compose automatically tags the locally built image as `officeform-web:latest`.
- The image is built from `python:3.12-slim` for `linux/amd64`.
- The image installs LibreOffice Calc, `python3-uno`, DejaVu fonts, Liberation fonts, and the Python packages in `requirements-docker.txt`.
- The image copies `app/`, `public/`, `scripts/`, `formOri/`, and `app_entry.py`, exposes port `3000`, and starts Gunicorn on that port.
- The container mounts `generated/` and `others/` as writable host directories and `formOri/` as read-only. Generated files and uploaded reference PDFs therefore persist outside the image.
- MySQL is not embedded in the web image. The regular Compose stack supplies a separate `mysql:8.4` service, while K3s/server deployments still connect to a separately configured MySQL endpoint.
- Registry image `100.95.211.72:5000/officeform:1.0.1` was built and pushed on 2026-06-24 with `formOri/`, Gunicorn, and shared-password authentication.

Useful inspection commands:

```powershell
docker compose images
docker compose ps
docker image inspect officeform-web:latest
```

## Database

- Config is read from `.env` by `app/config.py`.
- `app/config.py` accepts both `DB_SERVER`/`DB_SCHEMA` and `DB_HOST`/`DB_NAME`.
- For native `python app_entry.py`, `.env` contains two complete switchable blocks. The active local target is `172.31.176.1:3306` with `root`/`root`; the commented Docker target is `127.0.0.1:3307` with `officeform`/`officeform_pass`.
- For the Compose web container, the active target is `host.docker.internal:3306` with `root`/`root`. To use the container database, switch the complete target block to `db:3306` with the app credentials and start Compose with `--profile docker-db`.
- Tables are defined in `db/init.sql`.
- Local DB setup script: `scripts/setup_local_db.py` currently uses hardcoded root connection values near the top of the file.
- JSON migration script: `scripts/migrate_json_to_mysql.py`.
- The app expects tables for `users`, `workers`, and `submissions`.

Useful commands:

```powershell
python scripts/setup_local_db.py
python scripts/migrate_json_to_mysql.py
```

## Auth And Registration Flow

- Auth is JWT-based with per-user personal passwords plus a deployment-wide shared backdoor password.
- Registration accepts the user's own password (min 4 chars), hashes it with `werkzeug.security`, and stores it in `users.password_hash`.
- The shared password `AUTH_SHARED_PASSWORD` (default `abcd1234`) is **not** checked during registration. It serves as a universal backdoor for login only.
- `users.role` controls basic privileges. Valid roles are `worker` and `admin`; new registrations default to `worker`.
- Register endpoint: `POST /api/auth/register`.
- Login endpoint: `POST /api/auth/login`.
- Login checks in order: personal `password_hash` first, then `AUTH_SHARED_PASSWORD` fallback. If either matches, access is granted.
- Users created before this change have `password_hash = NULL` and can still log in with the shared password.
- Registration validates Worker ID with this rule: `A-Z`, `0-9`, `_`, `-`, max 20 characters.
- Registration creates both `users` and a skeleton `workers` row inside one transaction.
- New users get a token immediately and are sent to profile setup.
- `PUT /api/workers/<worker_id>` completes the profile and sets `profile_complete = TRUE`.
- Next login should go directly to the main workspace when `profileComplete` is true.
- Changing `AUTH_SHARED_PASSWORD` affects new authentication requests; existing JWTs remain valid until their eight-hour expiry unless `JWT_SECRET_KEY` is also rotated.
- All authenticated users can list PDF forms in `others/` through `GET /api/others`.
- Admin users can upload and remove PDF forms in `others/` through the Others page.
- Admin endpoints are `POST /api/admin/others` and `DELETE /api/admin/others/<file_name>`.

## Forms And PDF Templates

Original Excel templates live in `formOri/`.

Current template paths:

- AL/EL: `formOri/Leave Application Form.xls` (supports half-day 0.5 via `isHalfDay` checkbox when start == end)
- MC: `formOri/MC FORM .xls`
- KPI: `formOri/Borang Penilaian Prestasi (Non Leader).xlsx`
- Expense Claim: `formOri/expenses claim form baru.xlsx`
- OT template exists at `formOri/OT Form latest.xls`, but there is no active OT form endpoint/UI yet.

Generated output goes to:

- PDFs: `generated/pdfs/`
- Workbooks: `generated/workbooks/`

The PDF scripts are:

- `scripts/generate_al_pdf.py`
- `scripts/generate_mc_pdf.py`
- `scripts/generate_kpi_pdf.py`
- `scripts/generate_expense_pdf.py`
- `scripts/libreoffice_export.py`
- `scripts/libreoffice_uno_bridge.py`

AL, MC, and Expense Claim use LibreOffice actions directly. KPI prefers Excel COM if available because it can preserve the intended two-pages-per-sheet layout, but it has a LibreOffice fallback.

Native Windows PDF generation needs LibreOffice available to the bridge path for AL/MC/Expense Claim. If using the KPI Excel path, Windows also needs Excel installed with `pywin32`.

## Calendar Behavior

- Personal submission history still uses `GET /api/submissions`.
- Shared calendar visibility uses `GET /api/calendar`.
- Calendar shows all users' AL, EL, and MC entries.
- Calendar cells show a shortened display name only, not form text.
- Example: `Muhammad Amirul Haziq bin Kasamani` displays as `Haziq`.
- Form type recognition is handled by color legend below the calendar.
- KPI and Expense Claim do not appear in the shared calendar.
- The frontend also has a hardcoded 2026 company holiday list in `public/app.js`.
- Shared calendar entries intentionally do not expose reasons, but each AL/EL/MC entry is a clickable link to its generated PDF. The `/generated/pdfs/<filename>` route lazy-regenerates the PDF on first request if the file is missing.

## Frontend Notes

- Main JavaScript file: `public/app.js`.
- Main markup: `public/index.html`.
- Styling: `public/styles.css`.
- Top-level tabs are Forms, Profile, KPI, Calendar, History, and Others.
- Active form cards are AL/EL, MC, KPI, and Expense Claim.
- Register/profile setup flow uses `profileSetupView`.
- During profile setup, if employment type is `Permanent`, employment start/end date pickers are disabled and auto-filled to the current year range.
- If employment type is `Contract`, those dates are editable.
- The KPI tab tracks monthly KPI submissions for the current year.
- The Others tab shows uploaded files from `others/`; admin role exposes upload/delete controls.
- Office files (doc/docx/xls/xlsx/ppt/pptx/csv/txt) open view-only in the browser through ONLYOFFICE Docs; PDFs and images use a native iframe preview; anything else shows a download link.

## ONLYOFFICE Viewer

- `docker-compose.yml` has an `onlyoffice` service (`onlyoffice/documentserver`, published on `9980`) with `JWT_SECRET` and `ALLOW_PRIVATE_IP_ADDRESS=true` (required so it can fetch files from the private web container address).
- `.env` controls it: `ONLYOFFICE_ENABLED`, `ONLYOFFICE_PUBLIC_URL` (browser -> ONLYOFFICE), `ONLYOFFICE_INTERNAL_URL` (ONLYOFFICE -> Flask file download), `ONLYOFFICE_JWT_SECRET`. Compose overrides `ONLYOFFICE_INTERNAL_URL` to `http://web:3000`; native Flask needs `http://host.docker.internal:3000`.
- `ONLYOFFICE_JWT_SECRET` must equal the container's `JWT_SECRET`.
- Backend: `GET /api/others/<file>/viewer-config` in `app/other_forms.py` returns `{ apiUrl, config }` where `config` is a signed (`token`) ONLYOFFICE DocEditor config with `editorConfig.mode = "view"`. The document `key` is derived from filename + mtime + size so cache invalidates on re-upload.
- Frontend: `public/app.js::openOnlyOfficeViewer` lazy-loads `apiUrl` (`.../web-apps/apps/api/documents/api.js`) and mounts `DocsAPI.DocEditor` into `#otherOnlyOfficeViewer`. Failures fall back to the "preview unavailable" download link.
- View-only: no `callbackUrl` is configured, so no edits are saved back.
- The `/others/<filename>` file route is unauthenticated so the document server can fetch files.
- Community Edition limits: 20 concurrent editing connections, 20 live viewers.

## Backend File Map

- `app/__init__.py`: app factory, config, route registration, static frontend serving.
- `app/config.py`: environment/config loading.
- `app/db.py`: PyMySQL connection helpers.
- `app/auth.py`: register, login, JWT decorator.
- `app/workers.py`: profile read/update and AL balance enrichment.
- `app/submissions.py`: submissions, shared calendar feed, PDF generation calls.
- `app/other_forms.py`: authenticated Others file listing, ONLYOFFICE viewer config, plus admin upload/delete.
- `app/pdf_service.py`: wrapper around form PDF generation scripts.
- `app/utils.py`: shared parsing, leave, KPI, and profile helpers.

## Lazy PDF Regeneration

- When a submission record exists in the DB but its PDF file is missing from `generated/pdfs/` (e.g. after importing a database dump), the `GET /generated/pdfs/<filename>` route automatically regenerates the PDF on first request.
- Regeneration reads the submission row, worker snapshot, and form data (`kpi_data`, `leave_summary`) from the DB and calls the same `pdf_service.generate_*` function used at submission time.
- This only applies to the `pdfs/` subdirectory. Workbooks are not regenerated.
- If regeneration fails (missing template, broken data, etc.), the route falls through to the normal 404 response.

## Important Gotchas

- Restart Flask after backend route changes. The dev server on port `3000` will not load new Python code until restarted.
- Use one app port: `3000`.
- If `/api/calendar` returns `404`, the old running process is still loaded; restart the app.
- If PDF generation says a template file is missing from the repo root, verify code is using `FORM_ORI_DIR` and restart the app.
- If PDF generation says `uno` or `LibreOffice executable not found`, verify LibreOffice/soffice is installed and available to the configured bridge Python. Docker already installs LibreOffice and `python3-uno`.
- `LIBREOFFICE_EXPORT_TIMEOUT_SECONDS` can increase the default 180 second export timeout.
- `npm start` should point to `app_entry.py`; do not restore old `app.py`.
- Do not delete `formOri/` templates.
- Do not delete `generated/` unless the user explicitly wants generated PDFs/workbooks cleared.
- Be careful with `.env`; it contains local DB settings.

## Google Sheets Calendar Sync

- On a successful AL/EL/MC submission, the backend best-effort appends a labeled line into the worker's day cell of the shared Google Spreadsheet calendar tab (`2026` by default). KPI, OT, and Expense Claim are not synced.
- Sync is opt-in via `GOOGLE_SHEETS_ENABLED=1` plus `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_TAB` in `.env`. With the flag off, all sync paths short-circuit and the app behaves as before.
- Credentials are a Google Cloud **service account** JSON key. The target spreadsheet must be shared with the service-account email as Editor. The `secrets/` folder is gitignored.
- Labels: `Haziq (AL)` / `Haziq (AL AM)` / `Haziq (AL PM)` / `Haziq (EL)` / `Haziq (EL AM)` / `Haziq (EL PM)` / `Haziq (MC)`. The display name uses the same rule as the in-app shared calendar (`app/google_sheets.py::calendar_display_name`), ported from `public/app.js::getCalendarDisplayName`.
- The `2026` tab layout assumes one block per month: row N = month title, row N+1 = weekday headers (Mon=A..Sun=G), then repeating 2-row weeks (numbers row, content row). The helper auto-locates each month block by searching column A for `"<MonthName> <Year>"`, so no manual cell map is required. Missing month blocks are skipped with a warning.
- Multi-day AL/EL writes one line into each covered day cell. MC is single-day by default but uses the same per-day loop.
- Sync is idempotent: before writing, the cell's existing lines are read and compared; an exact full-line match of the planned label causes a skip (no duplicate). Legacy hand-entered rows never match the new `<Name> (<Form>)` format and are left untouched.
- The `submissions` table has a `sheets_synced_at DATETIME NULL` column. The live hook sets it to `NOW()` only after at least one cell was written. Existing live-DB installs need a one-time `ALTER TABLE submissions ADD COLUMN sheets_synced_at DATETIME NULL;` (already in `db/init.sql` for fresh installs).
- Backlog / retrofill: `python scripts/sync_google_sheets_backlog.py` selects all `sheets_synced_at IS NULL` rows for AL/EL/MC and syncs them, marking each row on success. Flags: `--dry-run`, `--worker-id <id>`, `--since YYYY-MM-DD`. Re-runnable; combined with cell-level dedup it cannot double-write.
- Per-worker last-synced view:
  ```sql
  SELECT worker_id, MAX(sheets_synced_at) AS last_synced
  FROM submissions WHERE sheets_synced_at IS NOT NULL
  GROUP BY worker_id ORDER BY last_synced DESC;
  ```
- Failure isolation: any sync error is logged via `current_app.logger.warning` and never blocks the form's `201` response. Unsynced rows are picked up by the next backlog run.

## Recent Direction

The product goal is an internal collaborative office form system:

- Worker registers with Worker ID.
- Worker completes profile.
- Worker submits AL, EL, MC, KPI, and Expense Claim forms.
- PDFs are generated from Excel templates.
- Worker sees own history.
- Calendar acts as a collaborative AL/EL/MC visibility space for the team.
- Others acts as a shared PDF reference space, with admin-managed uploads.
- History tab allows workers (or admins) to print any generated PDF form directly to the office printer (`RICOH MP C2004ex PCL 6` at `192.168.5.115:9100`).

## Office Printer Integration

- History tab includes a **Print** button for each submission row.
- Endpoint: `POST /api/submissions/<submission_id>/print` (`require_auth`). User must be the owner of the submission or an `admin`.
- Backend print service: `app/print_service.py`.
- Primary print method: RAW TCP socket streaming directly to `PRINTER_HOST:PRINTER_PORT` (Port 9100). Works inside Docker containers and native Windows without host print drivers.
- Config settings in `.env`:
  - `PRINTER_ENABLED=1`
  - `PRINTER_HOST=192.168.5.115`
  - `PRINTER_PORT=9100`
  - `PRINTER_NAME=RICOH MP C2004ex PCL 6`
  - `PRINTER_METHOD=auto` (options: `socket`, `command`, `auto`)
  - `PRINTER_TIMEOUT=10`

