# Backend Refactor — Session Summary

## What Was Done

Refactored the officeForm app from a single-file Flask + JSON-file backend into a modular Flask app backed by MySQL, with JWT authentication and a multi-user registration flow.

---

## Stack Before → After

| | Before | After |
|---|---|---|
| Backend structure | Single `app.py` (829 lines) | `app/` package split into blueprints |
| Database | JSON flat files (`data/workers.json`, `data/submissions.json`) | MySQL 8.0 (local, `172.31.176.1:3306`) |
| Auth | None — Worker ID entry only | JWT (PyJWT), register + login endpoints |
| Password | Not implemented | Scaffolded (`password_hash` column, nullable — ready to enable) |
| Entry point | `app.py` | `app_entry.py` |
| Dependencies | Flask, pywin32 | + PyMySQL, PyJWT, flask-bcrypt, python-dotenv, cryptography |

---

## New File Structure

```
officeForm/
  app/
    __init__.py        — create_app() factory, registers blueprints, serves frontend
    config.py          — reads DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, JWT_SECRET_KEY from .env
    db.py              — PyMySQL connection pool, get_db() / query() / query_one() / execute()
    auth.py            — POST /api/auth/register, POST /api/auth/login, require_auth decorator
    workers.py         — GET/PUT /api/workers/<id> (auth-protected)
    submissions.py     — GET/DELETE/POST /api/submissions/* (auth-protected)
    pdf_service.py     — thin wrapper around scripts/generate_*.py
    utils.py           — pure helpers moved from app.py unchanged
  scripts/
    generate_al_pdf.py     — UNCHANGED
    generate_mc_pdf.py     — UNCHANGED
    generate_kpi_pdf.py    — UNCHANGED
    migrate_json_to_mysql.py — one-time migration from JSON files to MySQL
    setup_local_db.py      — creates officeform DB, user, and tables on local MySQL
  db/
    init.sql           — CREATE TABLE statements (used by Docker setup)
    my.cnf             — MySQL config (not active — local MySQL used instead)
  public/              — frontend (index.html, app.js, styles.css) — minimally updated
  app_entry.py         — NEW entry point: from app import create_app
  docker-compose.yml   — MySQL-only Docker setup (not active — local MySQL used)
  .env                 — DB credentials + JWT_SECRET_KEY (gitignored)
  .env.example         — template
```

---

## MySQL Schema

```
users       — id, worker_id (UNIQUE), password_hash (NULL, scaffolded), created_at
workers     — worker_id (PK), name, designation, department, house_tel, other_tel,
              evaluator_name, annual_leave_entitlement, annual_leave_taken,
              employment_type, employment_start_date, employment_end_date,
              profile_complete (BOOLEAN), updated_at
submissions — id (PK), worker_id (FK), form_type, form_name, leave_type,
              start_date, end_date, duration_days, affects_al, al_days_applied,
              reason, kpi_month, application_date, kpi_data (JSON),
              worker_snapshot (JSON), leave_summary (JSON),
              pdf_file_name, workbook_file_name, created_at
```

---

## Auth Flow

- **Register** — `POST /api/auth/register` with `{ workerId }`. Creates `users` + skeleton `workers` row. Returns JWT + worker object with `profileComplete: false`.
- **Profile setup** — `PUT /api/workers/<id>` with full profile fields. Sets `profile_complete = TRUE`.
- **Login** — `POST /api/auth/login` with `{ workerId }`. No password check yet (scaffolded). Returns JWT + worker object.
- **Frontend gate** — if `worker.profileComplete === false` after login, redirects to profile form before dashboard.
- **Token** — JWT, 8-hour expiry, stored in `localStorage`. All API calls send `Authorization: Bearer <token>`.
- **Password** — `password_hash` column exists and `flask-bcrypt` is installed. To enable: make the column NOT NULL and add the bcrypt check in `auth.py` (marked with `# TODO`).

---

## Frontend Changes (public/app.js + index.html)

- Added Register view, Profile Setup view alongside existing Login view
- `showView()` helper switches between login / register / profileSetup / workspace
- `clearAuth()` clears token from state and localStorage on logout or 401
- `api()` function now attaches `Authorization: Bearer` header on every request
- Auto-logout on 401 (expired token)
- Login calls `POST /api/auth/login` instead of `GET /api/workers/<id>`
- Submissions fetch no longer passes `?workerId=` — server reads from token
- Delete submission no longer passes `?workerId=` in query string

---

## PDF Generation

**Unchanged.** All three `scripts/generate_*.py` files use Windows COM automation (`win32com`/`pywin32`) and require Microsoft Excel installed locally. They cannot run inside a Linux Docker container. Flask runs natively on Windows; only MySQL is containerizable.

---

## Database Connection

- **Local MySQL 8.0** at `172.31.176.1:3306`
- Database: `officeform`, User: `officeform`, Password: `officeform_pass`
- To recreate from scratch: `python scripts/setup_local_db.py`
- To migrate existing JSON data: `python scripts/migrate_json_to_mysql.py`
- Docker MySQL alternative: `docker-compose up db` (uses port 3306, same credentials)

---

## How to Run

```
# Activate venv
.\.venv\Scripts\activate

# Start the app
python app_entry.py
# → http://127.0.0.1:3000
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/auth/register | No | Create account |
| POST | /api/auth/login | No | Login, get JWT |
| GET | /api/health | No | Health check |
| GET | /api/forms | No | List available forms |
| GET | /api/workers/\<id\> | Required | Get worker profile |
| PUT | /api/workers/\<id\> | Required | Update worker profile |
| GET | /api/submissions | Required | List own submissions |
| DELETE | /api/submissions/\<id\> | Required | Delete submission |
| POST | /api/submissions/al | Required | Submit AL/EL form |
| POST | /api/submissions/mc | Required | Submit MC form |
| POST | /api/submissions/kpi | Required | Submit KPI form |

---

## Known Issues / Next Steps

- **Password auth** is scaffolded but not enforced — login works with Worker ID only. Add bcrypt check in `auth.py` when ready.
- **Docker for Flask** is not implemented — blocked by Windows COM dependency in PDF scripts. Could be unblocked by moving PDF generation to a Windows host sidecar process.
- **`app.py`** (old entry point) has been removed. Use `app_entry.py` or `npm start`.
- **`docker-compose.yml`** is configured for MySQL-only. The `.env` `DB_HOST` is set to the local machine IP (`172.31.176.1`) — update this if deploying elsewhere.
