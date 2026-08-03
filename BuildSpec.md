# officeForm MCP Server — Build Spec

This is the single, self-contained spec for implementing the officeForm MCP server. It is
grounded in the actual backend API (verified by reading `app/`). An executing agent
should NOT need to read `MCP_PLAN.md` or the Flask source to build this; everything
required is below. If anything here contradicts the Flask source, **the Flask source
wins** — stop and flag it.

## 0. Goal & architecture

Build a standalone Python process (`mcp_server/`) that exposes officeForm features to an
LLM agent (Hermes/OpenClaw) as MCP tools, so a worker can apply leave, check the shared
calendar, look up history, and generate PDFs by talking to their bot in natural language
— without the web UI.

Architecture: **thin MCP wrapper over the existing REST API** (do not touch the Flask app).

```
Hermes agent (homelab)
   |  MCP (JSON-RPC over Streamable HTTP)   headers: X-Api-Key, X-Worker-Id
   v
mcp_server/  (NEW, on the office server host, port 3001, bound 127.0.0.1)
   |  resolve X-Api-Key -> workerId (secrets/mcp_api_keys.json)
   |  POST /api/auth/service-login  (X-MCP-Service-Key + workerId -> JWT)
   |  REST (Bearer JWT, retry-on-401)
   v
Flask app (app_entry.py, + ONE new endpoint: /api/auth/service-login)  -> http://127.0.0.1:80
   |  PyMySQL
   v
MySQL (pre-existing container, published 3306 on the host; officeform/myadmin)
```

The MCP server reaches the worker over the homelab->office-laptop SSH tunnel:
homelab Hermes points at `http://127.0.0.1:13001/mcp`; the tunnel forwards to the office
server `192.168.4.236:3001`.

### Decisions already locked (from MCP_PLAN.md Part 8)

- **D1 — Credential source:** the MCP server calls a **new** Flask endpoint
  `POST /api/auth/service-login` with a service secret (`MCP_SERVICE_LOGIN_KEY`) + the
  resolved `workerId`; Flask mints a JWT for that worker. **No worker passwords are stored
  anywhere in the MCP server.** Workers never tell the admin their password. The
  endpoint's spec is in section 9 below; the one allowed Flask change is adding it to
  `app/auth.py`. This is the single exception to hard constraint #1.
- **D2 — workerId binding:** each agent sends `X-Worker-Id: <WORKER_ID>` and a per-worker
  `X-Api-Key` in its MCP config headers. The MCP server keeps a server-side map
  `secrets/mcp_api_keys.json` of `{ apiKey -> workerId }` and rejects any request whose
  `X-Worker-Id` doesn't match its key's worker (blocks impersonation). The LLM never sees
  or sets the worker ID.
- **D3 — Network:** MCP server runs on the office host (`MCP_HOST=127.0.0.1`,
  `MCP_PORT=3001`), reached over an SSH tunnel from the homelab through the office laptop.
- **D4 — Phase 1 scope:** all five read-only tools ship first.
- **D5 — Write gating:** every write tool requires explicit user confirmation via a
  `confirm: bool` arg (default `false`) plus a description that tells the LLM to ask first.

## 1. Hard constraints (do not violate)

1. **The ONLY Flask change allowed is adding `POST /api/auth/service-login` to
   `app/auth.py` (spec in section 9).** Do not modify any other Flask file, route, or
   behavior. Do not touch `app_entry.py`, `scripts/`, `public/`, or any other endpoint.
   The new endpoint must reuse the existing `_make_token` and `_get_auth_worker` helpers
   so its JWT and `worker` response are byte-identical to `/api/auth/login`.
2. **Do not put any worker password, the shared backdoor, `MCP_SERVICE_LOGIN_KEY`,
   `JWT_SECRET_KEY`, or API keys in tool arguments, tool descriptions, source code, or
   git.** All secrets come from `.env` / `secrets/` at runtime. The `secrets/` files and
   `.env` MUST be gitignored.
3. **Never use `AUTH_SHARED_PASSWORD` for MCP.** Service-login does NOT check passwords;
   it checks the service secret. Workers' personal passwords are irrelevant to the agent.
4. **Every write tool requires user confirmation** (D5): a `confirm: bool` arg defaulting
   to `false`, plus a description that tells the LLM to ask first.
5. **Per-worker identity via `X-Worker-Id` header, bound to `X-Api-Key`** (D2). No
   `workerId` tool argument.
6. **Use the official `mcp` Python SDK with FastMCP + Streamable HTTP transport.** Don't
   hand-roll JSON-RPC. Target `python -m mcp_server` on port `3001`.
7. **Bind `MCP_HOST=127.0.0.1`.** Never `0.0.0.0` in this deployment (the SSH tunnel
   targets localhost). Reaching the wider LAN is out of scope.
8. **The MCP server does NOT connect to MySQL and does NOT store worker passwords.**
   It has no DB access. JWTs come from `/api/auth/service-login`. Do not add `pymysql`,
   a `db.py`, `mcp_credentials.json`, or any `DB_*` env vars to the MCP server.

## 2. Repo layout to create

```
mcp_server/
  __init__.py
  __main__.py            # entry: load config, build FastMCP app, run uvicorn
  config.py             # env + secrets loading
  auth.py               # X-Api-Key -> workerId resolution, JWT cache, service-login
  api_client.py         # requests-based wrapper around the Flask API, retry-on-401
  tools_read.py         # Phase 1 read-only tools
  tools_write.py        # Phase 2 write tools (with confirmation gating)
  tools_admin.py        # Phase 3 admin tools (optional, deferred / stub)
  schemas.py            # JSON Schema dicts (and pydantic v2 models if convenient)
requirements-mcp.txt    # mcp, requests, python-dotenv, uvicorn
secrets/
  mcp_api_keys.json     # { "<apiKey>": { "workerId": "HAZIQ" } }   (gitignored, 0600)
.env                    # append MCP_* / OFFICEFORM_BASE_URL keys. NO DB_* block for MCP.
.gitignore              # `secrets/` is ALREADY gitignored (line 8) — confirm; no edit needed.
```

Note on `.env`: the existing `.env` already has a `DB_*` block for the Flask app — the
MCP server does NOT use it (hard constraint 8). Only append the new `MCP_*` and
`OFFICEFORM_BASE_URL` keys. There is NO `mcp_credentials.json` — service-login replaces it.

## 3. Dependencies (`requirements-mcp.txt`)

Pin to current stable versions; these are the minimums:

```
mcp>=1.2.0
requests>=2.31
python-dotenv>=1.0
uvicorn[standard]>=0.30
```

No `pymysql` or `werkzeug` — the MCP server does not touch MySQL and does not verify
passwords itself (the Flask login endpoint does the verification). Install into the
existing `.venv` so `python -m mcp_server` works from the repo root after
`.\.venv\Scripts\activate` (confirm with the user before choosing a separate venv).

## 4. Config (`mcp_server/config.py`)

Load from `.env` (python-dotenv) and `secrets/mcp_api_keys.json`. Expose a `Config`
object with:

| Var | Required | Default | Notes |
|---|---|---|---|
| `OFFICEFORM_BASE_URL` | yes | — | `http://127.0.0.1:80` on the office host. **No trailing slash.** |
| `MCP_HOST` | no | `127.0.0.1` | Bind address for the streamable-HTTP server. |
| `MCP_PORT` | no | `3001` | |
| `MCP_API_KEYS_FILE` | no | `secrets/mcp_api_keys.json` | Path to the apiKey->workerId map. |
| `MCP_SERVICE_LOGIN_KEY` | yes | — | Shared secret for `POST /api/auth/service-login`. MUST equal the Flask side's `MCP_SERVICE_LOGIN_KEY`. Long random string. |
| `REQUEST_TIMEOUT_SECONDS` | no | `90` | Per-call HTTP timeout to Flask. Must exceed LibreOffice PDF gen time for KPI/EXP. |
| `LOG_LEVEL` | no | `INFO` | |

Strip the trailing `/` from `OFFICEFORM_BASE_URL` (mirrors `app/config.py`). **No `DB_*`
vars** — the MCP server has no DB access (hard constraint 8). **No `MCP_CREDENTIALS_FILE`**
— service-login replaces the credentials store.

`secrets/mcp_api_keys.json` shape:
```json
{
  "key_haziq_<random>":   { "workerId": "HAZIQ" },
  "key_amirul_<random>":  { "workerId": "AMIRUL" },
  "key_siti_<random>":    { "workerId": "SITI" }
}
```
Load once at startup into memory. If the file is missing or empty, the server still
starts but every authenticated request fails closed. The map is **apiKey -> workerId**.
There is NO password file. `MCP_SERVICE_LOGIN_KEY` lives in `.env` (not in `secrets/`),
since it is a single shared secret, not per-worker.

## 5. (No DB helper or credentials file — removed)

The MCP server does not connect to MySQL and does not store worker passwords. JWTs
come from `/api/auth/service-login` (section 9). There is no `mcp_server/db.py` and no
`mcp_credentials.json`. (This section is intentionally blank so the old specs are clearly
gone.)

## 6. Auth resolution + JWT cache (`mcp_server/auth.py`)

This is the heart of the multi-worker design. It does three things per request:

**Step A — resolve the request to a workerId.** Read `X-Api-Key` and `X-Worker-Id` from
the incoming HTTP headers (FastMCP/Starlette `Request`). Look up the api key in the
in-memory map; if missing -> reject 401. If the map's `workerId` != the `X-Worker-Id`
header -> reject 401 (impersonation attempt). On success, the resolved `worker_id` is
fixed for this request and is the ONLY identity used downstream. Never trust a
`workerId` from tool arguments.

**Step B — get or refresh a JWT for that worker_id.** Maintain an in-memory dict
`{ worker_id: (jwt: str, exp_epoch: float, role: str | None) }`. For a given worker_id:
- If cached and `exp_epoch - now > 60s`, reuse it.
- Otherwise call `POST {OFFICEFORM_BASE_URL}/api/auth/service-login` with:
  - header `X-MCP-Service-Key: <MCP_SERVICE_LOGIN_KEY>`
  - JSON body `{ "workerId": worker_id }`
  - This is the endpoint you add to Flask (section 9). It does NOT check a worker
    password; it checks the service secret and mints a JWT for the named worker.
  - On 200, parse `token` (the field is named **`token`**, not `jwt`) and cache it.
    Decode the JWT `exp` claim to set `exp_epoch` (HS256; you do NOT need
    `JWT_SECRET_KEY` to decode — just base64-decode the payload to read `exp`; the
    server already verified it). Cache `role` too — it comes from `worker.role` on the
    response (for Phase 3 admin gating).
  - On 401 from service-login (bad/missing service key) -> clear the cache entry and
    return a clear, non-retriable error: `"MCP service-login rejected by Flask (bad
    MCP_SERVICE_LOGIN_KEY). Check .env on both sides."` Do NOT retry.
  - On 404 (worker not found) -> surface Flask's message verbatim:
    `"No account found for this Worker ID. Please register first."`
- Note: there is NO "no credential configured" error anymore — if the worker_id resolved
  from the api-key map (Step A) but doesn't exist in `users`, Flask returns 404 here. If
  the api-key map itself is missing the worker, that's caught in Step A.

**Step C — retry-on-401 wrapper** for all downstream `/api/*` calls: when the api_client
gets a 401 from a regular `/api/*` call (e.g. an expired JWT), invalidate that
worker_id's cache entry, re-run Step B once (service-login again), and retry the
original call once. A second 401 returns the error as-is. (A 401 from service-login
itself is NOT retried — see Step B.)

Expose:
```python
def resolve_worker_id(request) -> str          # raises AuthError on failure
def get_jwt(worker_id: str) -> str            # raises AuthError on failure (does login)
def get_role(worker_id: str) -> str | None    # cached from login response
def invalidate(worker_id: str) -> None        # called by api_client on 401
class AuthError(Exception): ...                # carry message + suggested http status
```

## 7. API client (`mcp_server/api_client.py`)

A small `requests.Session`-based client. One method per HTTP verb, all returning parsed
JSON (or raising `ApiError` carrying the Flask `error` string):

```python
class ApiClient:
    def __init__(self, base_url: str, timeout: float): ...
    def get(self, worker_id, path): ...
    def post(self, worker_id, path, json_body): ...
    def put(self, worker_id, path, json_body): ...
    def delete(self, worker_id, path): ...
    def post_multipart(self, worker_id, path, file_field, file_path): ...  # admin upload only
```

- Each call: `get_jwt(worker_id)` -> set `Authorization: Bearer <jwt>` -> `requests.request`.
- On 401: `auth.invalidate(worker_id)`, `get_jwt(worker_id)` again, retry once.
- On any non-2xx: raise `ApiError(status, payload)` where `payload` is the parsed JSON.
  If the body has an `error` field, surface that string verbatim (the LLM will explain it).
- `base_url` has no trailing slash; `path` starts with `/api/...`.
- `post_multipart` is for `POST /api/admin/others` which is `multipart/form-data` with a
  field named `file` (the only non-JSON POST in the API).

## 8. Tool definitions — exact schemas

All tool functions get the resolved `worker_id` injected from the request context (do
not take it as an LLM arg). The JSON Schema `inputSchema` for each tool is what the LLM
sees — descriptions must be plain-English and include the constraints below.

### 8.1 Phase 1 — read-only (no confirmation)

`get_leave_balance(worker_id)` -> `GET /api/workers/<id>`
- Input: `{}` (no args).
- Returns: `{ "workerId", "entitlement", "taken", "remaining", "employmentType",
  "periodStart", "periodEnd" }` — derived from `worker.annualLeaveEntitlement`,
  `worker.annualLeaveTaken`, `worker.annualLeaveBalance`, `worker.employmentType`,
  `worker.employmentStartDate`, `worker.employmentEndDate`.
- Description: "Get the authenticated worker's current annual-leave balance: total
  entitlement, days already taken, and days remaining. Use this before applying leave."

`get_profile(worker_id)` -> `GET /api/workers/<id>`
- Input: `{}`.
- Returns: the full enriched `worker` object as-is, with `role` included.
- Description: "Get the authenticated worker's full profile (name, designation,
  department, evaluator, leave entitlement/taken/balance, employment type and period)."

`get_calendar(worker_id)` -> `GET /api/calendar`
- Input: `{ "month"?: string }` — optional `YYYY-MM` filter applied **client-side** (the
  backend ignores query params and returns all entries; filter by `calendarStart`).
- Returns: an array of `{ "date", "workerName", "formType", "isOwn", "pdfUrl",
  "isHalfDay", "halfDayPeriod" }` for the month (or all if no month). Map from calendar
  entries: `date = calendarStart`, `workerName = calendarName ?? workerName`.
- Description: "Show the shared team calendar of AL/EL/MC leave. Optional `month`
  (`YYYY-MM`) restricts to one month; omit it to get the full year. Each entry shows who
  is on which leave and a link to the generated PDF. Other people's reasons are never
  exposed. Entries where `isOwn=true` belong to the current worker."

`list_my_submissions(worker_id)` -> `GET /api/submissions`
- Input: `{ "formType"?: string, "limit"?: int }` — `formType` filters client-side on
  `submission.formType` (one of `AL`,`EL`,`UNPAID`,`OTHER`,`MC`,`KPI`,`EXP`,`OT`); `limit`
  truncates the DESC-by-`createdAt` list.
- Returns: array of trimmed submission objects: `{ "id", "formType", "formName",
  "startDate", "endDate", "durationDays", "isHalfDay", "halfDayPeriod", "reason",
  "kpiMonth", "pdfUrl", "createdAt" }` (drop `workerSnapshot`, `leaveSummary`,
  `kpiData`, `expenseData`, `otData` — too noisy for the LLM).
- Description: "List the authenticated worker's own submission history, newest first.
  Optional `formType` filter (AL, EL, MC, KPI, EXP, OT, UNPAID, OTHER). Optional `limit`."

`list_reference_forms(worker_id)` -> `GET /api/others`
- Input: `{}`.
- Returns: array of `{ "name", "fileName", "url", "size", "updatedAt" }`.
- Description: "List the shared reference files in the Others tab (PDFs, images, Office
  docs) that the team can view."

### 8.2 Phase 2 — writes (require `confirm: bool` arg, default false)

`submit_al_leave(worker_id)` -> `POST /api/submissions/al`
- Input:
  ```json
  {
    "startDate": "yyyy-mm-dd",                 // required
    "endDate": "yyyy-mm-dd",                    // optional, defaults to startDate
    "leaveType": "annual|unpaid|emergency|other", // required; annual->AL, emergency->EL
    "reason": "string",                          // required
    "isHalfDay": false,                          // optional; ONLY valid when startDate==endDate
    "halfDayPeriod": "AM|PM",                    // required iff isHalfDay true
    "confirm": false                             // MUST be true to execute
  }
  ```
- Validation before calling the API: if `isHalfDay && startDate != endDate` -> return a
  plain-English error (the API would reject, but fail fast and clearly for the LLM).
- Returns: `{ "submissionId", "formType", "pdfUrl", "startDate", "endDate",
  "durationDays", "leaveRemaining", "leaveSummary" }` pulled from the `submission`
  object. `leaveRemaining = submission.leaveSummary.balanceAfter`; `leaveSummary` passed
  through (keys: `entitlement`, `takenToDate`, `balanceBefore`, `balanceAfter`).
- Description: "Submit an Annual Leave (AL) or Emergency Leave (EL) form for the current
  worker. This has real side effects: it inserts a submission, generates a PDF, decrements
  the leave balance, and best-effort syncs the shared Google calendar. BEFORE calling, you
  MUST tell the user the exact leaveType, dates, and reason and get an explicit 'yes'. Set
  `confirm=true` only after that. Half-day (`isHalfDay=true`) is only valid when startDate
  equals endDate, with `halfDayPeriod` 'AM' or 'PM'. Returns the new submission id, PDF
  URL, and the updated leave balance. If `confirm` is not true, this tool returns an error
  without submitting."

`submit_mc(worker_id)` -> `POST /api/submissions/mc`
- Input: `{ "startDate", "endDate"?, "reason" or "sicknessReason", "confirm" }`.
- Returns: `{ "submissionId", "formType", "pdfUrl", "startDate", "endDate",
  "durationDays" }`. (MC has no leave summary / no half-day.)
- Description: confirmation preamble + "Submit a Medical Certificate (MC) form. MC does
  not reduce annual leave. Multi-day MC is allowed (endDate optional, defaults to
  startDate)."

`submit_kpi(worker_id)` -> `POST /api/submissions/kpi` (the complex one)
- Input:
  ```json
  {
    "kpiMonth": "yyyy-mm",                      // required
    "evaluatorName": "string",                   // required (fall back to worker.evaluatorName if user omitted)
    "taskList": "string",                         // required, free text
    "scores": {                                   // required; 7 sections, each array of exactly 5 ints 1..5
      "knowledge": [1..5,1..5,1..5,1..5,1..5],
      "quality": [...],
      "problemSolving": [...],
      "communication": [...],
      "teamwork": [...],
      "initiative": [...],
      "continuousLearning": [...]
    },
    "comments": {                                 // optional, same 7 keys, each a string
      "knowledge": "...", ...
    },
    "summaryOptions": {                            // required; all 8 keys with exact allowed values
      "breakfastMeeting": "Hadir|Tidak Hadir",
      "emergencyLeaveAttendance": "Tiada|0.5 Hari|1 Hari|1.5 Hari|2 Hari|2.5 Hari|Lebih 3 Hari",
      "medicalLeaveAttendance": "Tiada|1 Hari|2 Hari|3 Hari|4 Hari|5 Hari|Lebih 6 Hari",
      "biroAgama": "1|2|Tiada",
      "biroSukan": "1|2|Tiada",
      "trainingHours": "Hadir|Tiada",
      "committeeRole": "Pengerusi|Naib Pengerusi|Setiausaha|AJK|Tiada",
      "eqariah": "Ya|Tiada"
    },
    "workerFeedback": "string",                  // optional
    "trainingNeeds": "string",                    // optional
    "evaluatorFeedback": "string",               // optional
    "confirm": false                              // required true to execute
  }
  ```
  Encode the allowed `summaryOptions` values as JSON-schema `enum` per key so the LLM
  can't invent values. The `scores` section keys and per-array length 5 / range 1-5
  should also be in the schema (`items` with `minimum:1, maximum:5`).
- One KPI per `(worker, month)` — duplicates get a 400 from the API; surface it verbatim.
- Returns: `{ "submissionId", "kpiMonth", "pdfUrl" }`.
- Description: confirmation preamble + "Submit a monthly KPI evaluation. Exactly one per
  month per worker. `scores` has 7 sections each with exactly 5 integer scores 1-5.
  `summaryOptions` values must match the allowed enums exactly. Slow: PDF generation via
  LibreOffice can take many seconds."

`submit_expense_claim(worker_id)` -> `POST /api/submissions/expenses`
- Input:
  ```json
  {
    "claimMonth": "yyyy-mm",                    // required
    "claimMonthEnd": "yyyy-mm",                 // optional, >= claimMonth
    "supervisorName": "string",                 // required
    "site": "string",                           // optional
    "advances": 0,                              // optional, >=0
    "items": [                                  // required, max 13 rows
      {
        "date": "yyyy-mm-dd",                   // must fall within the claim month range
        "description": "string",                // required
        "project": "string",                   // optional
        "transportMode": "car|motorcycle",      // optional, default car
        "totalKm": 0, "parking": 0, "toll": 0, "hotel": 0, "flight": 0,
        "medical": 0, "phone": 0, "entertainment": 0, "travelAllowance": 0, "misc": 0
      }
    ],
    "confirm": false
  }
  ```
  The API computes `mileage = totalKm * rate` (car 0.87, motorcycle 0.60) and `total` per
  row server-side, so the LLM only supplies the raw amounts.
- Returns: `{ "submissionId", "claimMonth", "pdfUrl", "totalAmount", "amountToReimburse" }`
  pulled from `submission.expenseData` (note: EXP stores its payload in the `kpi_data`
  column but exposes it as `expenseData`).
- Description: confirmation preamble + "Submit an expense claim for a month range. Up to
  13 line items. Only supply raw amounts and km; the server computes mileage and totals.
  Slow (PDF generation)."

### 8.3 Phase 3 — admin (deferred; stub with NotImplementedError)

`upload_reference_form(worker_id)` -> `POST /api/admin/others` (multipart, field `file`)
`delete_reference_form(worker_id)` -> `DELETE /api/admin/others/<fileName>`
- The admin check: the MCP server must verify the resolved worker has `role == "admin"`.
  Cache `{ worker_id: role }` from the login response (`worker.role`). If a non-admin
  worker calls an admin tool, return a clear error without hitting the API.

## 9. Flask endpoint to add: `POST /api/auth/service-login`

This is the **only** Flask change (hard constraint #1). It goes in `app/auth.py` and
reuses the existing `_make_token` and `_get_auth_worker` helpers so its JWT and `worker`
response are byte-identical to `/api/auth/login`.

**Also required on the Flask side:** add `MCP_SERVICE_LOGIN_KEY` to `app/config.py` (read
from env, default `""`), and add the value to `.env` (and `docker-compose.yml` `web`
environment if running in Compose). The MCP server's `.env` must have the **same** value.

### Request

```
POST /api/auth/service-login
Header: X-MCP-Service-Key: <MCP_SERVICE_LOGIN_KEY>
Body:   { "workerId": "HAZIQ" }
```

### Logic (pseudocode mirroring `app/auth.py`)

```python
@bp.post("/api/auth/service-login")
def service_login():
    # 1. Service-secret check (constant-time).
    key = request.headers.get("X-MCP-Service-Key", "")
    if not key or not hmac.compare_digest(key, current_app.config["MCP_SERVICE_LOGIN_KEY"]):
        return jsonify({"error": "Service key required."}), 401

    # 2. Defense-in-depth: only allow calls from the local host (MCP server runs there).
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "Service login is local-only."}), 403

    # 3. Normalize + look up the worker.
    body = request.get_json(silent=True) or {}
    worker_id = normalize_worker_id(body.get("workerId"))
    if not worker_id:
        return jsonify({"error": "Worker ID is required."}), 400
    user = query_one("SELECT id FROM users WHERE worker_id = %s", (worker_id,))
    if not user:
        return jsonify({"error": "No account found for this Worker ID. Please register first."}), 404

    # 4. Mint a JWT for that worker. NO password check. NO AUTH_SHARED_PASSWORD.
    current_app.logger.warning("MCP service-login minted JWT for worker_id=%s from %s",
                                worker_id, request.remote_addr)
    token = _make_token(worker_id)
    return jsonify({"token": token, "worker": _get_auth_worker(worker_id)})
```

### Rules / gotchas for the Flask change

- **Reuse `_make_token` and `_get_auth_worker`** so the JWT and the `worker` object
  (including `role`) match `/api/auth/login` exactly. Do not duplicate JWT logic.
- **No password check, no `AUTH_SHARED_PASSWORD` fallback.** The service secret IS the
  auth. The whole point is to avoid storing/using worker passwords.
- **Constant-time compare** the service key (`hmac.compare_digest`).
- **Local-only** (`request.remote_addr in ("127.0.0.1","::1")`): the MCP server runs on
  the same host, so the only legit caller is localhost. This means even if
  `MCP_SERVICE_LOGIN_KEY` leaks to the tailnet, an external caller can't reach the
  endpoint. Keep this check.
- **Audit log** every call (worker_id + remote_addr) at WARNING level. This is the one
  endpoint that mints a JWT without a password, so it must be observable.
- **Config:** add `MCP_SERVICE_LOGIN_KEY = os.environ.get("MCP_SERVICE_LOGIN_KEY", "")`
  to `app/config.py`. If it is empty, the endpoint returns 401 for everyone (fail closed).
- **No other Flask change.** Do not touch `app_entry.py`, other routes, the DB schema,
  `scripts/`, or `public/`.

## 10. Confirmation gating (shared helper)

A single helper used by all write tools:
```python
def require_confirm(args: dict) -> str | None:
    if not args.get("confirm", False):
        return ("Confirmation required. This tool has side effects. Tell the user "
                "exactly what you will submit and call again with confirm=true only after "
                "an explicit yes.")
    return None
```
Each write tool: check `require_confirm(args)` first -> if non-None, return that as the
tool error (MCP `isError`). Only then call the API. This is the second line of defense
behind the LLM asking (D5).

## 11. FastMCP wiring (`mcp_server/__main__.py`)

- Build the FastMCP app with streamable HTTP on `host=MCP_HOST, port=MCP_PORT`.
- Mount the api-key middleware BEFORE the MCP handler: a Starlette middleware that reads
  `X-Api-Key` / `X-Worker-Id`, calls `auth.resolve_worker_id(request)`, and stashes the
  resolved `worker_id` in the request state for tools to read. Reject
  unknown/impersonating requests with 401 before they reach MCP. (FastMCP's streamable
  HTTP runs on Starlette, so standard Starlette middleware works.)
- Register all tool functions with `@mcp.tool()` and the JSON Schema from `schemas.py`.
- Run with `uvicorn` (the `mcp` SDK provides a runner; follow the SDK's current docs for
  the exact `run` call — do not assume the API; check the `mcp.server.fastmcp` import
  path at build time since the SDK is still evolving).
- Health: expose a plain `GET /healthz` (outside MCP) returning `{"ok": true}` for the
  SSH-tunnel smoke test.

## 12. Acceptance criteria per phase

**Flask side (must pass before any MCP work):**
- `POST /api/auth/service-login` exists in `app/auth.py`. With a correct
  `X-MCP-Service-Key` and a valid `workerId`, it returns 200 `{ "token", "worker" }`
  where the `token` is accepted by `GET /api/workers/<id>` as a Bearer JWT. (Verify:
  `curl -X POST http://127.0.0.1/api/auth/service-login -H "X-MCP-Service-Key: <key>"
  -H "Content-Type: application/json" -d '{"workerId":"HAZIQ"}'` then use the returned
  token on `GET /api/workers/HAZIQ`.)
- Wrong/missing service key -> 401 `{"error":"Service key required."}`.
- Call from a non-localhost remote_addr -> 403 `{"error":"Service login is local-only."}`
  (simulate by temporarily binding a test client to the LAN IP, or just trust the code
  path + a unit-style check).
- Unknown workerId -> 404 with the same message as `/api/auth/login`.
- No other Flask endpoint or behavior changed (diff is one new function + one config
  line). The web UI login, register, submissions, calendar, others all still work.

**Phase 0 — skeleton (must pass before any tool work):**
- `python -m mcp_server` starts and logs "listening on 127.0.0.1:3001".
- `curl http://127.0.0.1:3001/healthz` returns `{"ok":true}`.
- From the homelab through the SSH tunnel: `curl http://127.0.0.1:13001/healthz` returns
  `{"ok":true}`.
- `npx @modelcontextprotocol/inspector` connects to `http://127.0.0.1:13001/mcp` with a
  valid `X-Api-Key` + `X-Worker-Id` and lists **zero** tools (none registered yet) without
  error. An invalid/missing api key returns 401.
- A request with a valid key but `X-Worker-Id` != the key's worker returns 401.

**Phase 1 — read-only tools:**
- All five tools appear in `tools/list` with correct schemas.
- `get_leave_balance` returns the same `entitlement/taken/remaining` shown on the web
  Profile tab for that worker (spot-check one real worker).
- `get_profile` returns `role` and the same leave numbers as `get_leave_balance`.
- `get_calendar` with `month:"2026-08"` returns exactly the entries whose `calendarStart`
  is in August; `isOwn` is true for the current worker's entries.
- `list_my_submissions` returns only the current worker's submissions, newest first.
- `list_reference_forms` matches the Others tab file list.
- End-to-end from the real Hermes config (D2 headers) succeeds. This is the gate to
  Phase 2.

**Phase 2 — write tools:**
- Calling `submit_al_leave` with `confirm=false` returns the confirmation-required error
  and does NOT hit the Flask API (verify via logs: no `/api/submissions/al` request).
- Calling with `confirm=true` and a valid payload creates a submission; the returned
  `leaveRemaining` matches `balanceAfter` in the new submission's `leaveSummary`; the PDF
  URL is reachable and returns a PDF (lazy-regenerated if missing).
- `submit_al_leave` with `isHalfDay=true` and `startDate != endDate` returns a clear
  fast-fail error without calling the API.
- `submit_mc` creates an MC submission that appears in `get_calendar` and
  `list_my_submissions`.
- `submit_kpi` with an invalid `summaryOptions` enum value returns the API's 400 error
  verbatim. A valid call creates the KPI submission (note: slow — up to ~90s).
- `submit_expense_claim` with an out-of-range item `date` returns the API's 400 verbatim.
  A valid call returns `totalAmount`/`amountToReimburse`.
- JWT expiry: simulate by deleting the cached token -> the next call re-mints via
  `/api/auth/service-login` and succeeds (retry-on-401 path). Verify via logs showing one
  `service-login` then the original call.
- A worker_id resolved from `mcp_api_keys.json` but not present in `users` gets a clear
  404 error from service-login (surface verbatim); no `/api/*` data call is made.

**Phase 3 — admin (optional):**
- A non-admin worker calling an admin tool gets a clear 403-style error with no API call.
- An admin worker can upload and delete reference files; the result of
  `list_reference_forms` reflects the change.

## 13. Verification commands

Run from `C:\Homelab\officeForm` after `.\.venv\Scripts\activate`:

```powershell
# 1. Byte-compile sanity:
python -c "import mcp_server, mcp_server.__main__"

# 2. Start the MCP server (it must coexist with the already-running Flask on :80):
python -m mcp_server

# 3. In another shell, smoke test health through the tunnel:
curl http://127.0.0.1:13001/healthz

# 4. Run the official inspector (best UX for manual tool calls):
npx @modelcontextprotocol/inspector
#   -> Transport: Streamable HTTP
#   -> URL: http://127.0.0.1:13001/mcp
#   -> Headers: X-Api-Key: <test key>, X-Worker-Id: <test worker>
#   -> List Tools, then call each Phase 1 tool and inspect the JSON.
```

Do not commit changes. Leave the repo clean. Report back: which phases pass acceptance,
and any place where the Flask source contradicted this spec (it wins).

## 14. Known gotchas (from the verified API surface)

- The login/service-login response field is **`token`**, not `jwt`/`accessToken`.
- `/api/auth/login` (the existing endpoint, NOT used by MCP) returns 401
  **`"Invalid password."`** (`app/auth.py:157`) and 404 `"No account found for this
  Worker ID. Please register first."`. The new `/api/auth/service-login` (section 9)
  returns 401 `{"error":"Service key required."}`, 403 `{"error":"Service login is
  local-only."}`, and the same 404 message. Surface all verbatim.
- The new `/api/auth/service-login` must be **local-only** (`request.remote_addr` in
  `127.0.0.1`/`::1`) and **constant-time** compare the service key. Do not weaken either.
- All worker/submission JSON uses **camelCase**; DB columns are snake_case. The MCP
  server passes JSON through unchanged — do not rename. The MCP server does not touch
  the DB at all, so snake_case never appears in MCP code.
- `leaveSummary` keys are `entitlement`, `takenToDate`, `balanceBefore`, `balanceAfter`
  (camelCase) except the optional `remove_entitlement` flag (snake_case) — pass it through
  if present, don't "fix" it.
- `/api/submissions` and `/api/calendar` take **no query params** — any month/formType
  filtering is done client-side in the MCP server (section 8).
- `kpi_data` column is reused for KPI, Expense, AND OT payloads; the API exposes it as
  `kpiData`/`expenseData`/`otData` depending on `formType`. Don't assume `kpiData` is
  null for non-KPI — use the right field per `formType`.
- `formType` is uppercase (`AL`,`EL`,`MC`,`KPI`,`EXP`,`OT`,`UNPAID`,`OTHER`);
  `leaveType` is lowercase (`annual`,`emergency`,`unpaid`,`other`). Don't conflate.
- `annualLeaveTaken` in the `workers` table is stale — always use the computed
  `worker.annualLeaveTaken` from the GET-worker response.
- `role` is appended only at the auth/worker endpoints; it is reliably on the login,
  service-login, and GET-worker responses — cache it from service-login.
- `POST /api/admin/others` is **multipart/form-data** (field name `file`), the only
  non-JSON POST (section 7 needs a dedicated method).
- PDF generation (KPI/EXP especially) can take many seconds -> keep
  `REQUEST_TIMEOUT_SECONDS=90` and the Hermes client timeout >= 60s.
- Google Sheets sync is best-effort and happens server-side automatically on AL/EL/MC
  submit/update/delete. Do NOT attempt to surface Sheets sync status through MCP; if a
  user reports a missing calendar line, point them at `scripts/sync_google_sheets_backlog.py`.

## 15. Out of scope for the first deliverable

- `update_submission` (PUT) and `delete_submission` (DELETE) — defer past Phase 2.
- `submit_ot` (OT endpoint exists but has no active UI) — defer.
- In-process MCP (running inside Flask) — not now.
- Dockerizing the MCP server into the Compose stack — not now; run on the host first.
- Resources/Prompts MCP primitives — skip.
- Any change to the Flask app — forbidden (section 1.1).

## 16. Definition of done

The first deliverable is done when **Phase 0 and Phase 1 pass all acceptance criteria
end-to-end through the SSH tunnel from the homelab**, using a real worker's
`X-Api-Key`/`X-Worker-Id`, verified with the MCP inspector. Phase 2 is a follow-up
deliverable gated on Phase 1 sign-off. The executing agent should stop after Phase 1 and
report back before starting Phase 2.

## Appendix — API reference (the facts behind the schemas)

These are the exact endpoints and field names the MCP server wraps. All authenticated
endpoints require `Authorization: Bearer <jwt>`. The MCP server obtains that JWT from
`POST /api/auth/service-login` (below), not from `/api/auth/login`.

### Auth
- `POST /api/auth/service-login` — **NEW endpoint you add to `app/auth.py` (section 9).**
  Header `X-MCP-Service-Key: <MCP_SERVICE_LOGIN_KEY>`, body `{ "workerId" }`. Local-only
  (127.0.0.1/::1). No password check. -> 200 `{ "token": <jwt>, "worker": {...enriched...} }`
  identical to `/api/auth/login`. This is the endpoint the MCP server uses to get JWTs.
  401 `{"error":"Service key required."}` / 403 `{"error":"Service login is local-only."}`
  / 404 `"No account found for this Worker ID. Please register first."`.
- `POST /api/auth/login` — existing endpoint, body `{ "workerId", "password" }` -> 200
  `{ "token", "worker" }`. Personal `password_hash` checked first, then
  `AUTH_SHARED_PASSWORD` fallback. **NOT used by the MCP server** (it uses service-login
  instead). JWT expires in 8h.
- `POST /api/auth/register` — body `{ "workerId", "password" }` (min 4 chars); workerId
  regex `^[A-Z0-9_-]{1,20}$`. Not needed for MCP.

### Worker (`/api/workers/<id>` — must equal the JWT's worker_id)
- `GET` -> 200 `{ "worker": {...} }`. Worker object fields (all camelCase): `workerId`,
  `name`, `designation`, `department`, `houseTel`, `otherTel`, `evaluatorName`,
  `calendarName`, `annualLeaveEntitlement`, `annualLeaveTaken`, `annualLeaveBalance`
  (= entitlement - taken, min 0), `employmentType` (`permanent`|`contract`),
  `employmentStartDate`, `employmentEndDate`, `profileComplete`, `role` (`worker`|`admin`).
- `PUT` -> body with any of those fields; sets `profile_complete=TRUE`. Out of scope for
  Phase 1/2 unless a later `update_profile` tool is added.

### Submissions
- `GET /api/submissions` -> 200 `{ "submissions": [...] }`. No query params. Own worker's
  rows, `created_at` DESC.
- `GET /api/calendar` -> 200 `{ "entries": [...] }`. No query params. All AL/EL/MC across
  all workers. Entry fields: `id`, `workerId`, `workerName`, `calendarName`, `formType`,
  `leaveType`, `calendarStart`, `calendarEnd`, `durationDays`, `isHalfDay`,
  `halfDayPeriod`, `pdfUrl`, `isOwn`. `reason` is NOT exposed.
- `POST /api/submissions/al` — body: `startDate` (req, `yyyy-mm-dd`), `endDate` (opt,
  default startDate), `leaveType` (req, `annual|unpaid|emergency|other`), `reason` (req),
  `isHalfDay` (bool), `halfDayPeriod` (`AM`|`PM`, req iff half-day; half-day only when
  start==end), `removeEntitlement` (opt bool). -> 201 `{ "submission": {...} }`.
  Submission object includes `id`, `formType`, `pdfUrl` (`/generated/pdfs/<file>`),
  `leaveSummary` (`{entitlement, takenToDate, balanceBefore, balanceAfter[,
  remove_entitlement]}`), `annualLeaveDaysApplied`, `affectsAnnualLeave`.
- `POST /api/submissions/mc` — body: `startDate`, `endDate?`, `sicknessReason` or
  `reason`. No half-day. -> 201 `{ "submission": {...} }`.
- `POST /api/submissions/kpi` — body as in section 8.2; `summaryOptions` enums are strict.
  One per worker/month. -> 201 `{ "submission": {...} }`. Slow.
- `POST /api/submissions/expenses` — body as in section 8.2; max 13 items. -> 201
  `{ "submission": {...} }` with `expenseData`. Slow.
- `PUT /api/submissions/<id>` / `DELETE /api/submissions/<id>` — defer.

### Others
- `GET /api/others` -> 200 `{ "forms": [{ id, name, fileName, url, size, updatedAt }] }`.
- `POST /api/admin/others` — **multipart/form-data**, field `file`. Admin only.
- `DELETE /api/admin/others/<file_name>` — admin only. -> 200 `{ "deleted", "forms" }`.

### Unauthenticated (not used by MCP, noted for completeness)
- `GET /generated/pdfs/<filename>` — serves the PDF; lazy-regenerates if missing.
- `GET /others/<filename>` — raw file serving (used by ONLYOFFICE).
- `GET /api/health`, `GET /api/forms`.
