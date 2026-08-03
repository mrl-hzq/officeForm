# officeForm MCP Server Plan

Goal: let an agent (OpenClaw, Hermes, etc.) use officeForm features — submit leave, check
the shared calendar, look up history, generate PDFs — by talking to its own bot in natural
language, without opening the web UI.

---

## Part 1 — How MCP Actually Works (Teaching Section)

### Your mental model, corrected

You said "MCP is basically API but with context for LLM." Close, but the precise version is:

> **MCP (Model Context Protocol) is a standard "socket" that lets an LLM agent discover and
> call capabilities that a server exposes — without the agent knowing anything about your
> app beforehand.**

Your existing Flask REST API is a contract written for **your frontend** (`public/app.js`).
The JavaScript was hand-coded to know every URL, every field name, every header. An LLM
agent doesn't have that. MCP solves this by making the server **self-describing**:

1. The agent connects and asks: *"what can you do?"*
2. The MCP server replies with a **tool list** — each tool has a name, a plain-English
   description, and a JSON Schema for its arguments.
3. The LLM reads those descriptions and decides **on its own** which tool to call and with
   what arguments, based on the user's request.
4. The tool executes, returns structured data (or text), and the LLM turns that into a
   natural-language answer.

So the flow isn't "API + context" — it's **API + discovery + schemas + a protocol the
agent already speaks**.

### The three things an MCP server can expose

| Primitive | What it is | officeForm example |
|---|---|---|
| **Tools** | Functions the agent can call (like POST endpoints) | `submit_al_leave`, `get_calendar`, `get_leave_balance` |
| **Resources** | Read-only data the agent can fetch (like GET endpoints) | `officeform://submissions/HAZIQ`, `officeform://others/expense-policy.pdf` |
| **Prompts** | Reusable prompt templates | "Draft my MC reason for today" |

For officeForm, **Tools** are 95% of the value. Resources are optional. Prompts are
skip-able for v1.

### The wire protocol

MCP is just **JSON-RPC 2.0** messages. Every message is one of: `request`, `response`,
`notification`. The core handshake:

```text
AGENT (client)                                MCP SERVER
     |  1. initialize  --------------------->  |  "hi, I speak MCP, version X"
     |  <--------------------- server info + capabilities
     |  2. tools/list  --------------------->  |  "what tools do you have?"
     |  <--------------------- [{name, description, inputSchema}, ...]
     |  3. tools/call  --------------------->  |  "call submit_al_leave with {...}"
     |  <--------------------- result (JSON/text)
```

The LLM never writes HTTP requests. It sees the tool descriptions in its context and
emits a structured "tool call" that the agent runtime translates into the JSON-RPC above.

### Transports (how the bytes move)

| Transport | How it works | When to use |
|---|---|---|
| **stdio** | Agent launches the MCP server as a child process; they talk over stdin/stdout | Server on the **same machine** as the agent. Simplest, no network, no auth needed beyond OS user. |
| **Streamable HTTP** | MCP server is an HTTP service (POST endpoint + optional SSE stream) | Server on a **different machine/container** — your case, since officeForm runs in Docker/K3s and the agent runs elsewhere on the tailnet. |

### Full example flow (what your agent conversation actually looks like)

You say to your OpenClaw bot:

> "Apply annual leave for me next Friday, family matter."

Under the hood:

```text
1. LLM decides it needs leave balance first.
   -> tools/call: get_leave_balance {}
   <- {"entitlement": 14, "taken": 5.5, "remaining": 8.5}

2. LLM checks the shared calendar for clashes.
   -> tools/call: get_calendar {"month": "2026-08"}
   <- [{date: "2026-08-07", name: "Haziq", formType: "AL"}, ...]

3. LLM submits the form.
   -> tools/call: submit_al_leave {
        "startDate": "2026-08-07",
        "endDate": "2026-08-07",
        "reason": "Family matter"
      }
   <- {"submissionId": "...", "pdfUrl": "http://.../generated/pdfs/AL_....pdf",
       "leaveRemaining": 7.5}

4. LLM replies to you:
   "Done — AL submitted for Fri 7 Aug (family matter). PDF: <link>.
    You'll have 7.5 days left after this. No one else is on leave that day."
```

The PDF generation, MySQL insert, and Google Sheets sync all happen exactly as they do
today, because the MCP tool calls the same backend logic.

---

## Part 2 — Architecture Options

### Option A: Thin MCP wrapper over the existing REST API (recommended)

A new standalone Python process (`mcp_server/`) that:
- logs in to `POST /api/auth/login` with configured worker credentials to get a JWT,
- exposes MCP tools that internally `requests.post(...)` to the Flask API,
- speaks **Streamable HTTP** so remote agents can connect.

```
Agent (OpenClaw/Hermes)
   |  MCP (JSON-RPC over HTTP)
   v
mcp_server/  (new, ~200 lines, official `mcp` Python SDK, FastMCP)
   |  REST (JWT Bearer)
   v
Flask app (app_entry.py, unchanged)
   |  PyMySQL
   v
MySQL
```

**Pros:** zero changes to the Flask app, all business rules (leave balance math, PDF
naming, Sheets sync) stay in one place, MCP layer is disposable/rewriteable, can run in
its own container.
**Cons:** one extra HTTP hop; JWT expiry (8h) means the wrapper must re-login.

### Option B: In-process MCP inside Flask

Mount a FastMCP streamable-HTTP app alongside Flask routes in the same process, calling
`app/` modules directly instead of HTTP.

**Pros:** no JWT hop, direct function calls, single container.
**Cons:** couples MCP lifecycle to the web app; Gunicorn multi-worker + SSE streams can be
fiddly; a bug in MCP code can take down the web UI.

### Option C: MCP server that talks straight to MySQL

**Don't.** You'd duplicate leave-balance math, PDF generation triggers, and Sheets sync.

**Recommendation: Option A**, with B as a later optimization if latency ever matters
(it won't for form submissions).

---

## Part 3 — Tool Surface (mapped to your real endpoints)

Phase 1: read-only (safe to ship first, no confirmation needed)

| MCP tool | Wraps | Notes |
|---|---|---|
| `get_profile` | `GET /api/workers/<id>` | Includes leave balance enrichment |
| `get_leave_balance` | same, trimmed | Small focused answer for the LLM |
| `get_calendar` | `GET /api/calendar` | Add optional month filter client-side |
| `list_my_submissions` | `GET /api/submissions` | Personal history |
| `list_reference_forms` | `GET /api/others` | The Others tab |

Phase 2: writes (agent should confirm with the user before calling)

| MCP tool | Wraps | Notes |
|---|---|---|
| `submit_al_leave` | `POST /api/submissions/al` | Supports half-day; returns PDF URL + new balance |
| `submit_mc` | `POST /api/submissions/mc` | |
| `submit_kpi` | `POST /api/submissions/kpi` | Complex body; LLM fills scores/comments dict |
| `submit_expense_claim` | `POST /api/submissions/expenses` | Line items array |
| `update_submission` | `PUT /api/submissions/<id>` | Edit own submission |
| `delete_submission` | `DELETE /api/submissions/<id>` | Recommend requiring explicit user confirmation |
| `update_profile` | `PUT /api/workers/<id>` | |

Phase 3 (admin, optional, separate credential): `upload_reference_pdf`,
`delete_reference_pdf`.

### Tool design rules that make LLMs reliable

1. **One tool = one user intent.** `submit_al_leave` beats a generic `submit_form`.
2. **Descriptions are the prompt.** Write them like instructions to a new employee:
   mention defaults ("use today's date if not specified"), constraints, and what the
   return value contains.
3. **Return rich, structured results.** Include `pdfUrl`, `submissionId`, and the
   updated leave balance so the LLM can answer follow-ups without another call.
4. **Fail loudly with plain-English errors.** Your API already returns
   `{"error": "..."}` — pass that string through verbatim; the LLM will explain it.

---

## Part 4 — Authentication Design

The hard question: **who is the agent acting as?** Your API is per-worker JWT.

Simplest viable design for a homelab:

- `.env` for the MCP server holds `OFFICEFORM_WORKER_ID` + `OFFICEFORM_PASSWORD`
  (the worker's personal password — the shared backdoor works too, but prefer personal).
- On startup (and on any `401`), the MCP server calls `/api/auth/login`, caches the JWT,
  and refreshes before its 8-hour expiry.
- Consequence: **each MCP server instance = one worker identity.** "Submit my leave" is
  unambiguous, and your existing per-worker permissions/history just work.

If you later want one MCP server for the whole team, add a `workerId` argument per tool
plus a server-side map of worker→credential, and require the agent user to state who they
are — but don't build that until needed.

Network security: since this sits on your tailnet, bind the MCP HTTP listener to the
Tailscale interface and/or put a shared `MCP_API_KEY` header check in front of it. The
MCP transport itself has no built-in auth — treat it like any private API.

---

## Part 5 — Implementation Plan

```
Phase 0  Skeleton          mcp_server/ with FastMCP, streamable HTTP, health tool,
                           config from .env. Agent can connect and list tools.
Phase 1  Read-only tools   get_profile, get_leave_balance, get_calendar,
                           list_my_submissions, list_reference_forms.
                           Test end-to-end from your agent.
Phase 2  Write tools       submit_al_leave first (highest value), then mc, kpi,
                           expense. Add confirmation flow in agent config.
Phase 3  Polish            update/delete tools, PDF download resource, Docker
                           service for mcp_server, docs for agent-side config.
```

### Concrete build notes (Phase 0–1)

- Use the official Python SDK: `pip install mcp` (provides `FastMcp`, streamable HTTP
  transport). Run standalone: `python -m mcp_server` on port e.g. `3001`.
- Each tool is a ~10-line function: build payload → `requests` call with `Authorization:
  Bearer <jwt>` → on 401 re-login and retry once → return JSON.
- Config: `OFFICEFORM_BASE_URL` (default `http://127.0.0.1:3000`), credentials,
  listen host/port.
- Agent-side config example (OpenClaw/Hermes style):
  ```json
  {
    "mcpServers": {
      "officeform": {
        "url": "http://100.x.y.z:3001/mcp",
        "headers": { "X-Api-Key": "..." }
      }
    }
  }
  ```
- Later: add a `mcp` service to `docker-compose.yml` so it deploys with the stack.

### Testing without an agent

- `npx @modelcontextprotocol/inspector` — the official inspector gives you a web UI to
  call each tool and see raw JSON-RPC. Perfect for Phase 1 verification before involving
  OpenClaw/Hermes.

---

## Part 6 — Risks & Gotchas

- **JWT expiry:** 8h token means long-running MCP server must handle re-login; trivial
  retry-on-401 wrapper solves it.
- **Half-day AL rule:** only valid when start == end. Encode this in the tool schema
  description, or the LLM will produce invalid combos.
- **PDF generation latency:** KPI via LibreOffice can take many seconds. Make sure the
  MCP client timeout on the agent side is generous (60s+), or return the submission ID
  immediately and let the lazy-regeneration route serve the PDF link later.
- **Deletes are destructive:** gate `delete_submission` behind an explicit confirm, and
  consider shipping Phase 2 without it.
- **Sheets sync is best-effort:** a successful tool call can still have unsynced calendar
  lines; mention `sync_google_sheets_backlog.py` in the docs, don't try to surface it
  through MCP.
- **Don't expose the shared backdoor password to the LLM.** Credentials live in the MCP
  server's `.env`, never in tool arguments.

---

## Part 7 — Q&A / Decisions Log

### Q1. What is JSON-RPC 2.0?

JSON-RPC 2.0 is a **stateless, transport-agnostic remote procedure call protocol**. It
defines how to ask someone to run a function and how they hand back the result or an
error — using plain JSON objects. MCP is built on top of it.

A JSON-RPC 2.0 message is **exactly one** of three shapes:

**1. Request** (someone wants to call a function)
```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": { "name": "submit_al_leave", "arguments": { "startDate": "2026-08-07" } }
}
```
- `jsonrpc`: always `"2.0"`.
- `id`: a string or number chosen by the caller. Used to match the reply to this request.
- `method`: the name of the remote function (MCP uses things like `tools/list`,
  `tools/call`, `initialize`).
- `params`: the arguments, as a structured object or an array. Optional.

**2. Response** (the result of a request)
```json
{ "jsonrpc": "2.0", "id": 7, "result": { "submissionId": "AL-2026-08-07-..." } }
```
On error:
```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "error": { "code": -32602, "message": "Invalid params", "data": { "detail": "..." } }
}
```
- The response reuses the caller's `id` so the caller knows which request it answers.
- A response has **either** `result` **or** `error`, never both.

**3. Notification** (one-way message, no reply expected)
```json
{ "jsonrpc": "2.0", "method": "notifications/initialized" }
```
- A notification is just a request **without an `id`**. The receiver MUST NOT reply.

The standard error codes MCP/JSON-RPC use:

| Code | Meaning |
|---|---|
| `-32700` | Parse error (bad JSON) |
| `-32600` | Invalid request (not a valid JSON-RPC object) |
| `-32601` | Method not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |
| `-32000…-32099` | Server-defined errors (MCP uses this range) |

Key rules that make it "2.0":
- Every request has an `id`; every response echoes that `id`.
- Notifications have **no** `id` and get **no** response.
- Errors are structured (`code` + `message` + optional `data`), not just strings.
- It is stateless: the server does not track session between calls. (MCP adds a tiny
  bit of state — an `initialize` handshake — but each message is still self-contained.)

In the MCP streamable-HTTP transport, each of these JSON-RPC messages is sent as the body
of a `POST` request to the `/mcp` endpoint (or as an SSE stream for long responses). So
"JSON-RPC 2.0 over HTTP" is just: **each HTTP POST body is one JSON-RPC message**, and the
HTTP response body is the matching JSON-RPC response. That's the entire wire format your
Hermes agent and the MCP server speak to each other.

---

### Q2. Can I just give my Hermes agent my username + password and let it use those when talking to the MCP server?

Short answer: **No, not directly — and you should not.** Here is why, and what to do instead.

**Why not (two separate problems):**

1. **The MCP transport itself has no built-in auth.** Streamable HTTP is just JSON-RPC
   over HTTP. There is no "log in" step in the MCP protocol. So if your MCP server is
   reachable, anyone with the URL can call every tool. Credentials must live in a header
   or some wrapper you add yourself.

2. **The officeForm API uses JWT, not username/password per call.** A worker logs in once
   via `POST /api/auth/login` to get a JWT, then sends `Authorization: Bearer <jwt>` on
   every later call. The JWT expires after 8 hours. So even if Hermes had your password,
   it would have to perform the login dance and refresh tokens itself — that's app logic,
   not something MCP gives you for free.

**The recommended split (one identity per MCP server instance):**

- The **MCP server** holds `OFFICEFORM_WORKER_ID` + `OFFICEFORM_PASSWORD` in its own
  `.env` (NOT the LLM, NOT the agent config). On startup it calls `/api/auth/login`,
  caches the JWT, and re-logs-in on any `401` or before the 8-hour expiry.
- The **agent (Hermes)** authenticates to the **MCP server** with a separate, simple
  shared secret — e.g. an `X-Api-Key` header set in the agent's MCP config. This proves
  "this request is allowed to talk to my MCP server," it is NOT your officeForm password.
- So there are **two credentials in two places**, on purpose:
  - officeForm worker password → MCP server's `.env` (used to get JWTs).
  - MCP API key → agent's config (used to talk to the MCP server).

```
Hermes agent
  --[X-Api-Key header]-->  MCP server  --[Bearer JWT]-->  Flask app
   (knows api key only)     (knows worker pw)            (verifies JWT)
```

**Why not hand the worker password to the LLM:**
- Anything in the agent's config or prompt can leak (logs, context, tool-call traces).
  Your officeForm password is also your login to the web UI — don't expose it.
- The shared backdoor password (`AUTH_SHARED_PASSWORD`) especially must never reach the
  LLM; it logs in as anyone.
- Keeping identity on the server side means "submit my leave" is unambiguous and your
  existing per-worker history/permissions/PDFs all keep working with zero changes.

**If you truly want per-user identity later:** keep the MCP server as one worker, OR add
a `workerId` argument per tool plus a server-side map of `{workerId → password}` and have
the agent state who it is acting as. Don't build that until you actually need multiple
people using the same MCP server.

---

### Q3. Network: officeForm is in the office, Hermes agent is at home — how do they connect?

You need a VPN between your homelab and your office network so the MCP server (in the
office) and Hermes (at home) can reach each other on a private IP. Practical notes:

**The pieces, by location:**

```
[ Home / homelab ]                       [ Office server ]
  Hermes agent  ──(tailnet/VPN)──►  officeForm web (Flask :3000)
                                   MCP server          (:3001)  ← new
                                   (optional) ONLYOFFICE (:9980)
```

**Step 1 — establish the VPN.**
- If you already use Tailscale on both ends, just join the office machine and the home
  machine to the same tailnet. The office box gets a stable `100.x.y.z` address; your
  Hermes host can reach it directly. WireGuard/Nebula/ZeroTier all work the same way.
- Make sure the office firewall allows the inbound VPN port, and the office server's
  internal firewall allows the tailnet interface to reach ports 3000/3001.
- Verify with: from home, `curl http://<office-tailnet-ip>:3000/api/others` (with a JWT)
  should return JSON.

**Step 2 — where to run the MCP server.**
- Run the MCP server **on the office server** (same machine or network as the Flask app,
  so `OFFICEFORM_BASE_URL` can be `http://127.0.0.1:3000` — fast, no VPN hop for
  server→app traffic).
- Bind the MCP HTTP listener to the office server's **tailnet IP only** (e.g.
  `0.0.0.0:3001` behind a firewall, or specifically the tailnet interface). Do NOT expose
  3001 to the public internet.
- Hermes at home points its MCP config at `http://<office-tailnet-ip>:3001/mcp`.

**Step 3 — lock it down.**
- Add the `X-Api-Key` check in front of the MCP server (Part 6 / Q2). Even on a tailnet,
  other devices on the tailnet could reach it.
- TLS: tailnet already encrypts traffic end-to-end, so plain HTTP on 3001 is acceptable
  inside tailnet. If you ever expose 3001 over the raw internet, put it behind a reverse
  proxy with TLS and client-cert or basic-auth.
- Latency: form submission triggers PDF generation (LibreOffice, can take seconds). Set
  the MCP client / Hermes tool timeout to 60s+ so it doesn't time out mid-generation.

**Step 4 — what you tell Hermes.**
```json
{
  "mcpServers": {
    "officeform": {
      "url": "http://100.<office-tailnet-ip>:3001/mcp",
      "headers": { "X-Api-Key": "<long-random-secret>" }
    }
  }
}
```
- The `100.x.y.z` address is your office machine's tailnet IP.
- The `X-Api-Key` is the secret shared between Hermes and the MCP server only.
- No officeForm password anywhere in the agent config.

**Operational checklist:**
- [ ] Both machines on the same tailnet/VPN.
- [ ] From home you can `curl` the office Flask app and get a response.
- [ ] MCP server running on the office box, bound to tailnet IP, listening on 3001.
- [ ] `X-Api-Key` check enabled; Hermes config has the matching key.
- [ ] MCP server `.env` has `OFFICEFORM_WORKER_ID` + `OFFICEFORM_PASSWORD` + `OFFICEFORM_BASE_URL=http://127.0.0.1:3000`.
- [ ] Hermes MCP client timeout ≥ 60s.
- [ ] Test from home with the MCP inspector first (`npx @modelcontextprotocol/inspector`)
      before pointing the real agent at it.

---

### Q4. Per-worker identity: many workers, each with their own agent — how to map an agent to a Worker ID?

You're right that this changes the design from Part 4. With multiple workers each running
their own Hermes agent, "who is `me`?" is no longer fixed at the server. You need each
agent to **declare which Worker ID it acts as**, and the MCP server must **prove** that
declaration (otherwise any agent could claim to be any worker).

The clean way to do this: **one credential pair per worker, looked up by Worker ID.**

**Design: server-side worker→password map**

The MCP server holds a small table (env vars, a JSON file, or a tiny DB table):

```
WORKER_HAZIQ=HaziqPersonalPassword123
WORKER_AMIRUL=AmirulSecret456
WORKER_SITI=SitiPass789
...
```

or a `mcp_credentials.json`:
```json
{
  "HAZIQ":   { "password": "HaziqPersonalPassword123" },
  "AMIRUL":  { "password": "AmirulSecret456" },
  "SITI":    { "password": "SitiPass789" }
}
```

Each tool gains a required `workerId` argument (or the agent sends it in a header / per-
session handshake — see options below). The flow:

```
Hermes (Haziq's agent)
  calls submit_al_leave { workerId: "HAZIQ", startDate: ... }
        │  X-Api-Key: <mcp-api-key>
        ▼
MCP server
  1. Check X-Api-Key  → is this agent allowed to talk to me at all?
  2. Look up WORKER_HAZIQ password
  3. POST /api/auth/login { workerId: "HAZIQ", password: <that> }
       → cache JWT per workerId (with expiry)
  4. POST /api/submissions/al  Authorization: Bearer <HAZIQ jwt>
  5. Return result to Hermes
```

Now the JWT is always the correct worker's, history goes to the right worker, leave
balance is the right worker's, and the PDF is named after the right worker.

**Where does `workerId` come from? Three options, pick one:**

| Option | How | Pros | Cons |
|---|---|---|---|
| **A. As a tool argument** | Every tool takes `workerId: str` | Simplest, stateless, LLM sees it | LLM must pass it every call; LLM could lie |
| **B. In a header / MCP session** | Agent sends `X-Worker-Id: HAZIQ` on every request | LLM never sees it; one declaration per agent | Needs the agent config to set headers; per-request check |
| **C. Login-as step at connect** | A custom `login` tool that returns a session the rest reuse | Feels like a real session | MCP is stateless-ish; adds protocol complexity |

**Recommended: Option B (header) for binding + Option A as a safety net.**
- Each worker configures their own Hermes with their `workerId` in the headers block.
  Their agent never needs to think about who it is.
- The MCP server reads `X-Worker-Id` from the header, looks up the password, logs that
  worker in, caches the JWT keyed by `workerId`.
- The `X-Api-Key` still gates "is this agent allowed at all." You can even tie it together:
  one API key per worker, and the key→workerId map is on the server, so a worker can't
  claim another worker's ID.

```json
// Haziq's Hermes config
{
  "mcpServers": {
    "officeform": {
      "url": "http://100.<office-ip>:3001/mcp",
      "headers": {
        "X-Api-Key": "<haziq-mcp-key>",
        "X-Worker-Id": "HAZIQ"
      }
    }
  }
}
```

**Server-side credential table (recommended shape):**
```json
{
  "HAZIQ":   { "apiKey": "key_haziq_...",  "password": "HaziqPersonalPassword123" },
  "AMIRUL":  { "apiKey": "key_amirul_...", "password": "AmirulSecret456" },
  "SITI":    { "apiKey": "key_siti_...",   "password": "SitiPass789" }
}
```
- On each request: check `X-Api-Key` is valid → look up the `workerId` it belongs to →
  if the request's `X-Worker-Id` does not match that key's worker, reject. This stops a
  worker from impersonating another worker just by changing the header.
- Cache `{ workerId → (jwt, expiresAt) }` in memory. Re-login on 401 or near expiry.
  One login per worker per 8 hours, regardless of how many tool calls they make.

**Security notes specific to multi-worker:**
- The shared backdoor password (`AUTH_SHARED_PASSWORD`) should **not** be in this table.
  Put each worker's **personal** password there. That way losing one credential only
  compromises one worker, and you get clean per-worker audit in `submissions`.
- Rotate: change the worker's password in the web UI (or DB), update the MCP table,
  restart the MCP server. Existing JWTs die on their own in ≤8h.
- Don't store this table in the repo. Keep it in `secrets/` (gitignored) or load from the
  same MySQL `users` table directly (the MCP server can query `users.password_hash` and
  verify with `werkzeug.security.check_password_hash` — then you don't maintain a second
  copy at all).

**Even simpler if you trust the workers (homelab case): skip the second table.**
Let the MCP server log in to officeForm directly by reading `users` from MySQL itself:
```python
# in the MCP server, for the requested workerId:
row = mysql("SELECT password_hash FROM users WHERE worker_id=%s", workerId)
if not check_password_hash(row.password_hash, supplied_or_per_worker_secret):
    reject
jwt = login(workerId, password)
```
That avoids keeping passwords in a second place. The `X-Api-Key` still gates agent access.

**Bottom line for your case:** add `workerId` (via header, per-agent config), keep a
per-worker credential map on the MCP server (or read straight from MySQL `users`), cache
JWTs per `workerId`, and tie each `X-Api-Key` to exactly one `workerId` so impersonation
is blocked. One MCP server instance now correctly serves all workers.

---

### Q5. Network: homelab + office laptop have Tailscale, but the office server hosting officeForm does NOT — how to route?

You have a split:

```
[ Home / homelab ]          [ Office LAN ]                              [ Office LAN ]
  Hermes agent  ──tailnet──►  office laptop (tailscale ON)  ──LAN──►  office server (no tailscale)
                                                                          officeForm :3000
                                                                          (MCP server :3001 would go here too)
```

The office server can't join the tailnet, but the office laptop can. So the laptop becomes
your **relay / jump host**. Three concrete options, simplest first:

**Option 1 — SSH tunnel through the laptop (recommended, zero new services)**

From your homelab, open an SSH tunnel that forwards a local port to the office server's
3000/3001, tunneled through the laptop:

```
# run this on the homelab machine (or wherever Hermes runs)
ssh -N -L 13000:<office-server-lan-ip>:3000 \
       -L 13001:<office-server-lan-ip>:3001 \
       <user>@<office-laptop-tailnet-ip>
```
- `<office-laptop-tailnet-ip>` = the laptop's `100.x.y.z` (reachable from home via tailnet).
- `<office-server-lan-ip>` = the office server's private LAN IP as seen by the laptop
  (e.g. `192.168.1.50`). The laptop must be able to reach it on the office LAN.
- `-N` = no shell, just forward.
- Now `http://127.0.0.1:13000` on the homelab = officeForm on the server, and
  `http://127.0.0.1:13001` = the MCP server on the server.
- Point Hermes at `http://127.0.0.1:13001/mcp`.
- Keep the tunnel alive with `autossh` or a systemd unit if you want it persistent.

Pros: no install on the locked-down server, no new daemon, works today. Cons: laptop must
stay on; one tunnel per homelab client.

**Option 2 — Tailscale subnet router on the laptop**

Make the office laptop advertise the office LAN (including the server) into the tailnet:

```
# on the office laptop (needs admin)
tailscale up --advertise-routes=192.168.1.0/24
```
- Replace `192.168.1.0/24` with your office LAN subnet.
- In the Tailscale admin console, **approve** the route and enable it for your tailnet.
- On the homelab side, accept routes (`tailscale up --accept-routes`).
- Now from home you can reach `http://<office-server-lan-ip>:3000` **directly** — Tailscale
  routes your packets through the laptop onto the office LAN.

Pros: one setup, every home device can reach the office LAN; no manual tunnels. Cons:
requires admin approval in the tailnet console; some corporate networks block this; the
laptop must stay online as the router.

**Option 3 — Run the MCP server ON the laptop instead of the server**

Since the laptop already has tailscale and can reach the office server on the LAN, run the
MCP server on the laptop:
- `OFFICEFORM_BASE_URL=http://<office-server-lan-ip>:3000`
- MCP server listens on the laptop's tailnet IP `:3001`.
- Hermes at home → `http://<office-laptop-tailnet-ip>:3001/mcp`.
- Laptop→server traffic stays on the office LAN (no VPN needed for that leg).

Pros: MCP server has tailnet access "for free"; server stays untouched. Cons: MCP server
runs on a laptop (power/uptime); the office server still hosts only the Flask app.

**Recommendation for your setup:** start with **Option 1 (SSH tunnel)** — it's the least
invasive, needs nothing on the server, and you can switch to Option 2 (subnet router)
later if you want it to feel like "the office LAN is just part of my tailnet."

**Whichever you pick, the security bits from Q2/Q3 still apply:**
- Bind the MCP server to the interface only the tunnel/router reaches, not the public
  internet.
- Keep the `X-Api-Key` + per-worker credential map (Q4) in front of it.
- TLS is optional inside tailnet/SSH; mandatory if you ever expose 3001 over raw internet.
- Set Hermes tool timeout ≥ 60s for PDF generation latency.

**Concrete end-to-end with Option 1:**
```
Homelab:  Hermes ──► 127.0.0.1:13001  (ssh tunnel)
                         │
                      tailnet
                         ▼
Office laptop:  sshd ──► forward to <office-server-lan-ip>:3001
                                       │
                                    office LAN
                                       ▼
Office server:  MCP server :3001  ──►  Flask :3000  (via 127.0.0.1 or LAN IP)
```
- Haziq's Hermes config:
```json
{
  "mcpServers": {
    "officeform": {
      "url": "http://127.0.0.1:13001/mcp",
      "headers": { "X-Api-Key": "key_haziq_...", "X-Worker-Id": "HAZIQ" }
    }
  }
}
```
- One ssh tunnel command keeps it alive; autossh makes it survive reboots.

---

## Part 8 — Decisions Log (answered)

These are the locked-in design choices for this build. Each ties back to the Q&A above.

### D1. Credential source: new Flask `POST /api/auth/service-login` endpoint

**Decision:** Add one new endpoint to the Flask app — `POST /api/auth/service-login` —
that accepts a **service secret** + a `workerId` and mints a JWT for that worker. The MCP
server calls this instead of `/api/auth/login`. **No worker passwords are stored anywhere
in the MCP server.** Workers never tell the admin their password.

Rationale: the previous two drafts both broke down:
- "Read `users.password_hash` from MySQL" was impossible — `app/auth.py:141-157` needs a
  plaintext password and a hash is one-way.
- "Store plaintext worker passwords in `secrets/mcp_credentials.json`" required the admin
  to know every worker's personal password — but workers set their own passwords in the
  web UI and the admin should not know them.

The service-login endpoint cuts the knot: the MCP server proves it is the trusted MCP
service (via a single service secret), names the worker to act as, and Flask mints a JWT
for that worker. Worker passwords stay out of the picture entirely.

**Trust model:**
- The MCP server holds: `secrets/mcp_api_keys.json` (apiKey → workerId, D2) and
  `MCP_SERVICE_LOGIN_KEY` (the service secret).
- Flask holds: `MCP_SERVICE_LOGIN_KEY` (same value, in its env).
- The agent (Hermes) holds: `X-Api-Key` (per worker).
- The worker holds: nothing new — just their normal web UI login password, which is now
  irrelevant to the agent.

Flow:
```
1. Hermes → MCP server  (X-Api-Key + X-Worker-Id)
2. MCP server: resolve apiKey → workerId (D2 impersonation check)
3. MCP server → Flask: POST /api/auth/service-login
     header: X-MCP-Service-Key: <MCP_SERVICE_LOGIN_KEY>
     body:   { "workerId": "HAZIQ" }
4. Flask: constant-time compare the key; look up users.worker_id; mint JWT via the
   existing _make_token(worker_id); return { "token", "worker": _get_auth_worker(...) }
5. MCP server caches the JWT (8h) keyed by workerId; uses it for /api/* calls; retries
   on 401 by calling service-login again.
```

**The one allowed Flask change:** add `POST /api/auth/service-login` to `app/auth.py`.
Reuse the existing `_make_token` and `_get_auth_worker` helpers so the JWT and the
returned `worker` object (including `role`) are byte-identical to what
`/api/auth/login` produces. No other Flask file, route, or behavior changes. This is the
single, well-scoped exception to the "don't touch Flask" rule.

**Endpoint spec (for the Flask side):**
- Method/path: `POST /api/auth/service-login`.
- Auth: a request header `X-MCP-Service-Key` that must equal `MCP_SERVICE_LOGIN_KEY` (a
  new env var read by `app/config.py`, default empty). Constant-time compare. Missing or
  mismatched → 401 `{"error": "Service key required."}`.
- Body: `{ "workerId": "<id>" }`. Normalize with the existing `normalize_worker_id`
  (uppercase, `^[A-Z0-9_-]{1,20}$`). Invalid/missing → 400.
- Look up `users WHERE worker_id = %s`. Not found → 404 (same message as login:
  `"No account found for this Worker ID. Please register first."`).
- **No password check.** The service secret IS the auth. Do NOT check `password_hash`
  or `AUTH_SHARED_PASSWORD` here.
- Defense-in-depth (recommended): reject the request unless `request.remote_addr` is
  `127.0.0.1` (the MCP server runs on the same host). Log every call with the resolved
  `worker_id` and the client IP for audit.
- Response: 200 `{ "token": <jwt>, "worker": <enriched, with role> }` — identical shape
  to `/api/auth/login`.

**Security notes:**
- `MCP_SERVICE_LOGIN_KEY` is a long random secret. Protect it like `JWT_SECRET_KEY`: in
  `.env` / `docker-compose.yml` env, gitignored, never in source. If it leaks, anyone who
  can reach `/api/auth/service-login` can mint a JWT for any worker — same blast radius as
  leaking `JWT_SECRET_KEY`.
- The `127.0.0.1` remote-addr check means the endpoint is only callable from the office
  host itself (where the MCP server runs). Even if the secret leaks to the tailnet, an
  external caller cannot reach it. This is the single most effective mitigation.
- Bonus over Option 1: legacy workers with `password_hash IS NULL` (who never set a
  personal password) CAN now use the agent — service-login doesn't check the password,
  only that the `users` row exists.
- Rotation: change `MCP_SERVICE_LOGIN_KEY` in both `.env` (Flask) and the MCP server's
  config, restart both. Existing JWTs die in ≤8h.

**Why not just let the MCP server sign JWTs with `JWT_SECRET_KEY`?** That would also
remove the password problem, but it expands the MCP server into a JWT authority and
puts the master signing key in a second place. The service-login endpoint keeps
`JWT_SECRET_KEY` only in Flask; the MCP server holds a narrower secret that can only
trigger Flask to mint (and Flask can rate-limit / audit / revoke the service key
independently). Slightly more code, much better separation.

### D2. workerId binding: `X-Worker-Id` header in each agent's config

**Decision:** Each worker configures their own Hermes with `X-Worker-Id: <WORKER_ID>` in
the `headers` block of their MCP server entry. The LLM never sees or sets the worker ID.

Rationale: stateless, one declaration per agent, keeps identity out of the LLM's context
and tool arguments (so the LLM can't mis-set or forget it).

Impersonation protection: pair `X-Worker-Id` with a per-worker `X-Api-Key`, and keep a
server-side map `{ apiKey → workerId }` (env or a small `mcp_api_keys.json` in `secrets/`).
On every request:
1. Reject if `X-Api-Key` is unknown.
2. Reject if the bound `workerId` for that key ≠ the request's `X-Worker-Id`.
3. Otherwise proceed with the resolved `workerId`.

So a worker changing their Hermes header to another worker's ID is rejected by the key
mismatch. A worker losing their `X-Api-Key` only affects them.

Hermes config shape (per worker):
```json
{
  "mcpServers": {
    "officeform": {
      "url": "http://127.0.0.1:13001/mcp",
      "headers": {
        "X-Api-Key": "key_haziq_<random>",
        "X-Worker-Id": "HAZIQ"
      }
    }
  }
}
```

### D3. Network: SSH tunnel through the office laptop (Option 1)

**Decision:** Reach the office server (no tailscale) from the homelab via an SSH tunnel
through the office laptop (which has tailscale). The MCP server runs ON the office
server alongside Flask; the tunnel exposes it as a local port on the homelab.

**Concrete office server details (validated against `docker-compose.yml`):**
- Office server LAN IP: `192.168.4.236` (this is what the office LAN browses to).
- Flask is served from the `web` Compose service with host port **80 → container 3000**
  (the repo's `docker-compose.yml` has `80:3000` commented and `3000:3000` active; the
  office deployment enables the `80:3000` mapping so `http://192.168.4.236/` works on
  port 80). So from the office server host, Flask is reachable at `http://127.0.0.1:80`
  (or `http://192.168.4.236`).
- The officeForm database is a **pre-existing MySQL container** (already set up
  independently; the Compose `docker-db` profile is left disabled). The `web` container
  reaches it at `db:3306` with `officeform`/`myadmin`; the DB container publishes `3306`
  to the host, so the MCP server on the host reaches the same DB at `127.0.0.1:3306`
  with the same `officeform`/`myadmin` credentials.

```
Homelab Hermes ──► 127.0.0.1:13001 ──ssh tunnel──► office laptop (tailnet) ──LAN──► office server 192.168.4.236 :3001 (MCP) ──► :80 (Flask in container)
```

Persistent tunnel command (homelab side, via `autossh`):
```
autossh -M 0 -N \
  -o "ServerAliveInterval=30" -o "ServerAliveCountMax=3" \
  -L 13080:192.168.4.236:80 \
  -L 13001:192.168.4.236:3001 \
  <user>@<office-laptop-tailnet-ip>
```
- `13080` → Flask on the office server (port 80). Handy for direct API testing from home
  (`curl http://127.0.0.1:13080/api/others -H "Authorization: Bearer <jwt>"`).
- `13001` → MCP server (what Hermes points at).
- Upgrade path: if SSH tunnels get tedious, switch to a Tailscale subnet router on the
  laptop (Q5 Option 2) — no client-side change to Hermes, just point at the server's LAN
  IP instead of `127.0.0.1:13001`.

MCP server `.env` (on the office server, running on the host — not in a container):
```
OFFICEFORM_BASE_URL=http://127.0.0.1:80     # published Flask port on the host
MCP_HOST=127.0.0.1                           # only the server itself / tunnel target reach it
MCP_PORT=3001
MCP_API_KEYS_FILE=secrets/mcp_api_keys.json
DB_HOST=127.0.0.1                            # pre-existing MySQL container's published port
DB_PORT=3306
DB_NAME=officeform
DB_USER=officeform                           # app user, NOT root
DB_PASSWORD=myadmin
```
- `DB_HOST=127.0.0.1` reaches the **pre-existing MySQL container** (set up separately;
  the Compose `docker-db` profile is left disabled) through its published `3306` on the
  Windows host. Credentials are the app user `officeform`/`myadmin` (matching Option B in
  `docker-compose.yml`). The Flask `web` container uses `DB_SERVER=db` from inside the
  Compose network; from the host you use `127.0.0.1` because the `db` hostname only
  resolves inside the Compose network.
Bind `MCP_HOST=127.0.0.1` because the SSH tunnel targets `127.0.0.1` on the server side;
nothing on the LAN or internet can reach 3001 directly. (If you move the tunnel to a LAN
IP target, set `MCP_HOST` to that interface instead.)

**Two options for where the MCP server lives (pick later):**
1. **On the host** (recommended start): a standalone `python -m mcp_server` process on
   the office server host, talking to Flask at `http://127.0.0.1:80` and MySQL at
   `127.0.0.1:3306`. No container changes.
2. **In the Compose stack**: add an `mcp` service that talks to `http://web:3000`
   (container-internal port, not the published 80) and to `db` or `host.docker.internal`
   for MySQL. Cleaner for production but couples it to the stack.

### D4. Phase 1 scope: all five read-only tools

**Decision:** Phase 1 ships every read-only tool, in this order (each verified end-to-end
before the next):

1. `get_leave_balance` — focused leave balance answer for the LLM (entitlement / taken /
   remaining). Highest signal-to-noise, easiest to verify against the Profile tab.
2. `get_profile` — full worker profile incl. leave enrichment (superset of #1; reuse the
   same `/api/workers/<id>` call).
3. `get_calendar` — shared AL/EL/MC calendar, optional `month` filter (`YYYY-MM`) applied
   client-side over `/api/calendar`.
4. `list_my_submissions` — personal history via `/api/submissions`.
5. `list_reference_forms` — Others tab listing via `/api/others`.

All Phase 1 tools are safe: no confirmation needed, no DB writes, no PDF generation,
fast (<1s each over the tunnel). Phase 1 is the gate: until these five work cleanly from a
real Hermes config through the SSH tunnel, do not start Phase 2.

### D5. Write gating: require user confirmation for ALL writes

**Decision:** Every Phase 2 write tool — `submit_al_leave`, `submit_mc`, `submit_kpi`,
`submit_expense_claim`, `update_submission`, `delete_submission` — must obtain explicit
user confirmation before the MCP server executes it. No auto-run on LLM decision alone.

Rationale: form submissions create PDFs, insert MySQL rows, trigger Google Sheets sync,
and decrement leave balances — real side effects. Destructive ops (`delete`) especially.

Implementation:
- Surface this in the tool **description** so the LLM knows to ask: "This tool has side
  effects. Tell the user exactly what you're about to submit (form type, dates, reason,
  amount) and wait for explicit yes/no before calling."
- Add a `confirm: bool` argument to each write tool, default `false`; the MCP server
  returns `{ "error": "confirmation required" }` if `confirm` is not `true`. This is a
  second line of defense behind the LLM asking.
- `delete_submission` additionally returns a preview of what will be deleted before
  accepting `confirm=true`.
- Phase 2 ships `submit_al_leave` first (highest value), then `submit_mc`, then
  `submit_kpi`, then `submit_expense_claim`. `update_submission` and `delete_submission`
  come last and may be deferred past Phase 2 entirely.

---

## Part 9 — Build Spec (handoff to an executing agent)

This section is the single source of truth for implementation. It is grounded in the
actual backend API (verified by reading `app/`). An executing agent should NOT need to
re-read the Flask source to build this; everything required is below. If anything here
contradicts the Flask source, **the Flask source wins** — stop and flag it.

### 9.0 Hard constraints (do not violate)

1. **Do not modify the Flask app (`app/`, `app_entry.py`, `scripts/`, `public/`).** The
   MCP server is a separate process that talks to the existing REST API over HTTP. The
   only files you create go under a new top-level `mcp_server/` directory plus a new
   `requirements-mcp.txt` and a `secrets/mcp_api_keys.json` (gitignored). Nothing else.
2. **Do not put any worker password, the shared backdoor, JWT secrets, or API keys in
   tool arguments, tool descriptions, source code, or git.** All secrets come from `.env`
   / `secrets/` at runtime.
3. **Never use `AUTH_SHARED_PASSWORD` for MCP logins.** Use each worker's personal
   `password_hash` only (D1). Workers with `password_hash IS NULL` get a clear error.
4. **Every write tool requires user confirmation** (D5): a `confirm: bool` arg defaulting
   to `false`, plus a description that tells the LLM to ask first.
5. **Per-worker identity via `X-Worker-Id` header, bound to `X-Api-Key`** (D2). No
   `workerId` tool argument.
6. **Use the official `mcp` Python SDK with FastMCP + Streamable HTTP transport.** Don't
   hand-roll JSON-RPC. Target `python -m mcp_server` on port `3001`.
7. **Bind `MCP_HOST=127.0.0.1`.** Never `0.0.0.0` in this deployment (the SSH tunnel
   targets localhost). Reaching the wider LAN is out of scope.

### 9.1 Repo layout to create

```
mcp_server/
  __init__.py
  __main__.py            # entry: load config, build FastMCP app, run uvicorn
  config.py             # env + secrets loading
  auth.py                # X-Api-Key -> workerId resolution, JWT cache, login flow
  db.py                  # PyMySQL read-only helper to read users.password_hash
  api_client.py          # requests-based wrapper around the Flask API, retry-on-401
  tools_read.py          # Phase 1 read-only tools
  tools_write.py         # Phase 2 write tools (with confirmation gating)
  tools_admin.py         # Phase 3 admin tools (optional, deferred)
  schemas.py             # JSON Schema dicts + pydantic-free type hints (or pydantic v2)
requirements-mcp.txt     # mcp, requests, pymysql, werkzeug, python-dotenv, uvicorn
secrets/
  mcp_api_keys.json      # { "<apiKey>": { "workerId": "HAZIQ" } }   (gitignored)
.env                     # append MCP_* / DB_* keys to the existing .env (do not duplicate DB block)
.gitignore              # add: mcp_server secrets/mcp_api_keys.json  (if not already ignored)
```

Note on `.env`: the existing `.env` already has a `DB_*` block for the Flask app. The MCP
server reuses those exact vars (`DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`) — do NOT add
a second DB block. Only append the new `MCP_*` and `OFFICEFORM_BASE_URL` keys. The MCP
server's DB connection is read-only (only ever `SELECT password_hash FROM users`).

### 9.2 Dependencies (`requirements-mcp.txt`)

Pin to current stable versions; these are the minimums:

```
mcp>=1.2.0
requests>=2.31
pymysql>=1.1
werkzeug>=3.0
python-dotenv>=1.0
uvicorn[standard]>=0.30
```

`werkzeug` is needed for `check_password_hash` (must match how the Flask app hashed the
passwords — it uses `werkzeug.security.generate_password_hash`, so `check_password_hash`
is the correct verifier). Install into a separate venv or the existing `.venv` — the
executing agent should ask the user which; default to the existing `.venv` so `python -m
mcp_server` works from the repo root after `.\.venv\Scripts\activate`.

### 9.3 Config (`mcp_server/config.py`)

Load from `.env` (python-dotenv) and `secrets/mcp_api_keys.json`. Expose a `Config`
object with:

| Var | Required | Default | Notes |
|---|---|---|---|
| `OFFICEFORM_BASE_URL` | yes | — | `http://127.0.0.1:80` on the office host. **No trailing slash.** |
| `MCP_HOST` | no | `127.0.0.1` | Bind address for the streamable-HTTP server. |
| `MCP_PORT` | no | `3001` | |
| `MCP_API_KEYS_FILE` | no | `secrets/mcp_api_keys.json` | Path to the api-key→workerId map. |
| `DB_HOST` | yes | — | Reuse existing `.env` DB block. `127.0.0.1` on the host. |
| `DB_PORT` | no | `3306` | |
| `DB_NAME` | no | `officeform` | |
| `DB_USER` | yes | — | `officeform` (app user). |
| `DB_PASSWORD` | yes | — | `myadmin`. |
| `REQUEST_TIMEOUT_SECONDS` | no | `90` | Per-call HTTP timeout to Flask. Must exceed LibreOffice PDF gen time for KPI/EXP. |
| `LOG_LEVEL` | no | `INFO` | |

Also compute `OFFICEFORM_BASE_URL` with the trailing `/` stripped (mirrors `app/config.py`).

`secrets/mcp_api_keys.json` shape:
```json
{
  "key_haziq_<random>":   { "workerId": "HAZIQ" },
  "key_amirul_<random>":  { "workerId": "AMIRUL" },
  "key_siti_<random>":    { "workerId": "SITI" }
}
```
Load once at startup. If the file is missing or empty, the server still starts but every
authenticated request fails closed. The map is **apiKey → workerId**; there is no
password here (the password lives in MySQL `users.password_hash`).

### 9.4 DB read helper (`mcp_server/db.py`)

A thin PyMySQL wrapper that opens a fresh connection per call (or a small pooled
connection). It only needs ONE function:

```python
def get_password_hash(worker_id: str) -> str | None:
    """Return users.password_hash for worker_id, or None if the user doesn't exist."""
```

- Use `pymysql.connect(host, port, user, password, db, cursorclass=DictCursor,
  autocommit=True)`. Always close in `finally`.
- This module is **read-only by design** — it never writes. Do not add a generic
  `query()` escape hatch; keep it to `get_password_hash`.
- Normalize `worker_id` the same way the Flask app does: uppercase, regex
  `^[A-Z0-9_-]{1,20}$` (see `app/auth.py:18`). Reject early if invalid — it's a cheap
  400-equivalent before any DB call.

### 9.5 Auth resolution + JWT cache (`mcp_server/auth.py`)

This is the heart of the multi-worker design. It does three things per request:

**Step A — resolve the request to a workerId.** Read `X-Api-Key` and `X-Worker-Id` from
the incoming HTTP headers (FastMCP gives you access via the request context / Starlette
`Request`). Look up the api key in the in-memory map; if missing → reject 401. If the
map's `workerId` ≠ the `X-Worker-Id` header → reject 401 (impersonation attempt). On
success, the resolved `worker_id` is fixed for this request and is the ONLY identity used
downstream. Never trust a `workerId` from tool arguments.

**Step B — get or refresh a JWT for that worker_id.** Maintain an in-memory dict
`{ worker_id: (jwt: str, exp_epoch: float) }`. For a given worker_id:
- If cached and `exp_epoch - now > 60s`, reuse it.
- Otherwise, fetch the worker's password: `get_password_hash(worker_id)` from MySQL.
  - If `None` → return a clear error: `"Worker <id> not found."`
  - If the hash is `NULL`/empty → return a clear error:
    `"Worker <id> has no personal password set. Set one in the officeForm web UI first;
    MCP login cannot use the shared password."` (D1).
- Call `POST {OFFICEFORM_BASE_URL}/api/auth/login` with JSON `{ "workerId": worker_id,
  "password": <plain password> }`. On 200, parse `token` (the field is named **`token`**,
  not `jwt` — see API ref §2) and cache it. Decode the JWT `exp` claim to set
  `exp_epoch` (HS256; you do NOT need `JWT_SECRET_KEY` to decode — just base64-decode the
  payload to read `exp`; the server already verified it).
- On 401 from login → clear the cache entry and return the login error verbatim (the
  Flask app returns `{"error": "Invalid credentials."}`).

**Step C — retry-on-401 wrapper** for all downstream API calls: when the api_client gets
a 401 from any `/api/*` call, invalidate that worker_id's cache entry, re-run Step B once,
and retry the original call once. A second 401 returns the error as-is.

Expose:
```python
def resolve_worker_id(request) -> str          # raises AuthError on failure
def get_jwt(worker_id: str) -> str             # raises AuthError on failure (does login)
class AuthError(Exception): ...                # carry message + suggested http status
```

### 9.6 API client (`mcp_server/api_client.py`)

A small `requests.Session`-based client. One method per HTTP verb, all returning parsed
JSON (or raising `ApiError` carrying the Flask `error` string):

```python
class ApiClient:
    def __init__(self, base_url: str, timeout: float): ...
    def get(self, worker_id, path): ...
    def post(self, worker_id, path, json_body): ...
    def put(self, worker_id, path, json_body): ...
    def delete(self, worker_id, path): ...
```

- Each call: `get_jwt(worker_id)` → set `Authorization: Bearer <jwt>` → `requests.request`.
- On 401: `auth.invalidate(worker_id)`, `get_jwt(worker_id)` again, retry once.
- On any non-2xx: raise `ApiError(status, payload)` where `payload` is the parsed JSON.
  If the body has an `error` field, surface that string verbatim (the LLM will explain it).
- `base_url` has no trailing slash; `path` starts with `/api/...`.
- For Phase 3 admin upload (`POST /api/admin/others`), add a `post_multipart(worker_id,
  path, file_field, file_path)` method — this endpoint is `multipart/form-data`, the only
  non-JSON POST in the API (API ref §16).

### 9.7 Tool definitions — exact schemas

All tool functions get the resolved `worker_id` injected from the request context (do not
take it as an LLM arg). The JSON Schema `inputSchema` for each tool is what the LLM sees —
descriptions must be plain-English and include constraints from the API ref.

**Phase 1 — read-only (no confirmation):**

`get_leave_balance(worker_id)` → `GET /api/workers/<id>`
- Input: `{}` (no args).
- Returns: `{ "workerId", "entitlement", "taken", "remaining", "employmentType",
  "periodStart", "periodEnd" }` — derived from `worker.annualLeaveEntitlement`,
  `worker.annualLeaveTaken`, `worker.annualLeaveBalance`, `worker.employmentType`,
  `worker.employmentStartDate`, `worker.employmentEndDate` (API ref §2).
- Description: "Get the authenticated worker's current annual-leave balance: total
  entitlement, days already taken, and days remaining. Use this before applying leave."

`get_profile(worker_id)` → `GET /api/workers/<id>`
- Input: `{}`.
- Returns: the full enriched `worker` object as-is (API ref §2), with `role` included.
- Description: "Get the authenticated worker's full profile (name, designation,
  department, evaluator, leave entitlement/taken/balance, employment type and period)."

`get_calendar(worker_id)` → `GET /api/calendar`
- Input: `{ "month"?: string }` — optional `YYYY-MM` filter applied **client-side**
  (the backend ignores query params and returns all entries; filter by `calendarStart`).
- Returns: an array of `{ "date", "workerName", "formType", "isOwn", "pdfUrl",
  "isHalfDay", "halfDayPeriod" }` for the month (or all if no month). Map from the calendar
  entries (API ref §11): `date = calendarStart`, `workerName = calendarName ?? workerName`.
- Description: "Show the shared team calendar of AL/EL/MC leave. Optional `month`
  (`YYYY-MM`) restricts to one month; omit it to get the full year. Each entry shows who
  is on which leave and a link to the generated PDF. Other people's reasons are never
  exposed. Entries where `isOwn=true` belong to the current worker."

`list_my_submissions(worker_id)` → `GET /api/submissions`
- Input: `{ "formType"?: string, "limit"?: int }` — `formType` filters client-side on
  `submission.formType` (one of `AL`,`EL`,`UNPAID`,`OTHER`,`MC`,`KPI`,`EXP`,`OT`); `limit`
  truncates the DESC-by-`createdAt` list.
- Returns: array of trimmed submission objects: `{ "id", "formType", "formName",
  "startDate", "endDate", "durationDays", "isHalfDay", "halfDayPeriod", "reason",
  "kpiMonth", "pdfUrl", "createdAt" }` (drop `workerSnapshot`, `leaveSummary`,
  `kpiData`, `expenseData`, `otData` — too noisy for the LLM).
- Description: "List the authenticated worker's own submission history, newest first.
  Optional `formType` filter (AL, EL, MC, KPI, EXP, OT, UNPAID, OTHER). Optional `limit`."

`list_reference_forms(worker_id)` → `GET /api/others`
- Input: `{}`.
- Returns: array of `{ "name", "fileName", "url", "size", "updatedAt" }` (API ref §14).
- Description: "List the shared reference files in the Others tab (PDFs, images, Office
  docs) that the team can view."

**Phase 2 — writes (require `confirm: bool` arg, default false):**

`submit_al_leave(worker_id)` → `POST /api/submissions/al`
- Input (API ref §5):
  ```json
  {
    "startDate": "yyyy-mm-dd",        // required
    "endDate": "yyyy-mm-dd",           // optional, defaults to startDate
    "leaveType": "annual|unpaid|emergency|other",   // required; annual->AL, emergency->EL
    "reason": "string",                // required
    "isHalfDay": false,                // optional; ONLY valid when startDate==endDate
    "halfDayPeriod": "AM|PM",          // required iff isHalfDay true
    "confirm": false                   // MUST be true to execute
  }
  ```
- Validation before calling the API: if `isHalfDay && startDate != endDate` → return a
  plain-English error (the API would reject, but fail fast and clearly for the LLM).
- Returns: `{ "submissionId", "formType", "pdfUrl", "startDate", "endDate",
  "durationDays", "leaveRemaining", "leaveSummary" }` pulled from the `submission` object
  (API ref §5/§10). `leaveRemaining = submission.leaveSummary.balanceAfter`;
  `leaveSummary` passed through (keys: `entitlement`, `takenToDate`, `balanceBefore`,
  `balanceAfter`).
- Description (write the schema description to instruct the LLM):
  "Submit an Annual Leave (AL) or Emergency Leave (EL) form for the current worker. This
  has real side effects: it inserts a submission, generates a PDF, decrements the leave
  balance, and best-effort syncs the shared Google calendar. BEFORE calling, you MUST
  tell the user the exact leaveType, dates, and reason and get an explicit 'yes'. Set
  `confirm=true` only after that. Half-day (`isHalfDay=true`) is only valid when
  startDate equals endDate, with `halfDayPeriod` 'AM' or 'PM'. Returns the new
  submission id, PDF URL, and the updated leave balance. If `confirm` is not true, this
  tool returns an error without submitting."

`submit_mc(worker_id)` → `POST /api/submissions/mc`
- Input (API ref §6): `{ "startDate", "endDate"?, "reason" or "sicknessReason", "confirm" }`.
- Returns: `{ "submissionId", "formType", "pdfUrl", "startDate", "endDate",
  "durationDays" }`. (MC has no leave summary / no half-day.)
- Description: same confirmation preamble; "Submit a Medical Certificate (MC) form. MC
  does not reduce annual leave. Multi-day MC is allowed (endDate optional, defaults to
  startDate)."

`submit_kpi(worker_id)` → `POST /api/submissions/kpi`
- Input (API ref §7) — the complex one. Schema:
  ```json
  {
    "kpiMonth": "yyyy-mm",            // required
    "evaluatorName": "string",        // required (falls back to worker's evaluatorName if omitted by user; still required field in API — fill from profile if empty)
    "taskList": "string",              // required, free text
    "scores": {                        // required; 7 sections, each array of exactly 5 ints 1..5
      "knowledge": [1..5,1..5,1..5,1..5,1..5],
      "quality": [...],
      "problemSolving": [...],
      "communication": [...],
      "teamwork": [...],
      "initiative": [...],
      "continuousLearning": [...]
    },
    "comments": {                      // optional, same 7 keys, each a string
      "knowledge": "...", ...
    },
    "summaryOptions": {                // required; all 8 keys with exact allowed values (see API ref §7)
      "breakfastMeeting": "Hadir|Tidak Hadir",
      "emergencyLeaveAttendance": "Tiada|0.5 Hari|1 Hari|1.5 Hari|2 Hari|2.5 Hari|Lebih 3 Hari",
      "medicalLeaveAttendance": "Tiada|1 Hari|2 Hari|3 Hari|4 Hari|5 Hari|Lebih 6 Hari",
      "biroAgama": "1|2|Tiada",
      "biroSukan": "1|2|Tiada",
      "trainingHours": "Hadir|Tiada",
      "committeeRole": "Pengerusu|Naib Pengerusu|Setiausaha|AJK|Tiada",
      "eqariah": "Ya|Tiada"
    },
    "workerFeedback": "string",        // optional
    "trainingNeeds": "string",          // optional
    "evaluatorFeedback": "string",     // optional
    "confirm": false                   // required true to execute
  }
  ```
  Encode the allowed `summaryOptions` values as JSON-schema `enum` per key so the LLM
  can't invent values. The `scores` section keys and the per-array length 5 / range 1-5
  should also be in the schema (use `items` with `minimum:1, maximum:5`).
- One KPI per `(worker, month)` — duplicates get a 400 from the API; surface it verbatim.
- Returns: `{ "submissionId", "kpiMonth", "pdfUrl" }`.
- Description: confirmation preamble + "Submit a monthly KPI evaluation. Exactly one per
  month per worker. `scores` has 7 sections each with exactly 5 integer scores 1-5.
  `summaryOptions` values must match the allowed enums exactly. Slow: PDF generation via
  LibreOffice can take many seconds."

`submit_expense_claim(worker_id)` → `POST /api/submissions/expenses`
- Input (API ref §8):
  ```json
  {
    "claimMonth": "yyyy-mm",          // required
    "claimMonthEnd": "yyyy-mm",       // optional, >= claimMonth
    "supervisorName": "string",       // required
    "site": "string",                 // optional
    "advances": 0,                    // optional, >=0
    "items": [                        // required, max 13 rows
      {
        "date": "yyyy-mm-dd",         // must fall within the claim month range
        "description": "string",      // required
        "project": "string",          // optional
        "transportMode": "car|motorcycle",   // optional, default car
        "totalKm": 0, "parking": 0, "toll": 0, "hotel": 0, "flight": 0,
        "medical": 0, "phone": 0, "entertainment": 0, "travelAllowance": 0, "misc": 0
      }
    ],
    "confirm": false
  }
  ```
  The API computes `mileage = totalKm * rate` (car 0.87, motorcycle 0.60) and `total`
  per row server-side, so the LLM only supplies the raw amounts.
- Returns: `{ "submissionId", "claimMonth", "pdfUrl", "totalAmount", "amountToReimburse" }`
  pulled from `submission.expenseData` (API ref §8 — note EXP stores its payload in the
  `kpi_data` column but exposes it as `expenseData`).
- Description: confirmation preamble + "Submit an expense claim for a month range. Up to
  13 line items. Only supply raw amounts and km; the server computes mileage and totals.
  Slow (PDF generation)."

**Phase 3 — admin (deferred; require the resolved worker to have `role == "admin"`):**

`upload_reference_form(worker_id)` → `POST /api/admin/others` (multipart)
`delete_reference_form(worker_id)` → `DELETE /api/admin/others/<fileName>`
- The admin check: the MCP server must fetch the worker's role. The login response
  includes `worker.role` (API ref §2). Cache `{ worker_id: role }` alongside the JWT. If a
  non-admin worker calls an admin tool, return a clear error without hitting the API.
- These are out of scope for the first deliverable; stub them with `NotImplementedError`.

### 9.8 Confirmation gating (shared helper)

A single helper used by all write tools:
```python
def require_confirm(args: dict) -> str | None:
    if not args.get("confirm", False):
        return ("Confirmation required. This tool has side effects. Tell the user "
                "exactly what you will submit and call again with confirm=true only after "
                "an explicit yes.")
    return None
```
Each write tool: check `require_confirm(args)` first → if non-None, return that as the tool
error (MCP `isError`). Only then call the API. This is the second line of defense behind
the LLM asking (D5).

### 9.9 FastMCP wiring (`mcp_server/__main__.py`)

- Build the FastMCP app with streamable HTTP on `host=MCP_HOST, port=MCP_PORT`.
- Mount the api-key middleware BEFORE the MCP handler: a Starlette middleware that reads
  `X-Api-Key` / `X-Worker-Id`, calls `auth.resolve_worker_id(request)`, and stashes the
  resolved `worker_id` in the request state for tools to read. Reject unknown/impersonating
  requests with 401 before they reach MCP. (FastMCP's streamable HTTP runs on Starlette, so
  standard Starlette middleware works.)
- Register all tool functions with `@mcp.tool()` and the JSON Schema from `schemas.py`.
- Run with `uvicorn` (the `mcp` SDK provides a runner; follow the SDK's current docs for
  the exact `run` call — do not assume the API; check `mcp.server.fastmcp` import path at
  build time since the SDK is still evolving).
- Health: expose a plain `GET /healthz` (outside MCP) returning `{"ok": true}` for the
  SSH-tunnel smoke test.

### 9.10 Acceptance criteria per phase

**Phase 0 — skeleton (must pass before any tool work):**
- `python -m mcp_server` starts and logs "listening on 127.0.0.1:3001".
- `curl http://127.0.0.1:3001/healthz` returns `{"ok":true}`.
- From the homelab through the SSH tunnel: `curl http://127.0.0.1:13001/healthz` returns
  `{"ok":true}`.
- `npx @modelcontextprotocol/inspector` connects to `http://127.0.0.1:13001/mcp` with a
  valid `X-Api-Key` + `X-Worker-Id` and lists **zero** tools (none registered yet) without
  error. An invalid/missing api key returns 401.
- A request with a valid key but `X-Worker-Id` ≠ the key's worker returns 401.

**Phase 1 — read-only tools:**
- All five tools appear in `tools/list` with correct schemas.
- `get_leave_balance` returns the same `entitlement/taken/remaining` shown on the web
  Profile tab for that worker (spot-check one real worker).
- `get_profile` returns `role` and the same leave numbers as `get_leave_balance`.
- `get_calendar` with `month:"2026-08"` returns exactly the entries whose `calendarStart`
  is in August; `isOwn` is true for the current worker's entries.
- `list_my_submissions` returns only the current worker's submissions, newest first.
- `list_reference_forms` matches the Others tab file list.
- End-to-end from the real Hermes config (Q4/D2 headers) succeeds. This is the gate to
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
- JWT expiry: simulate by deleting the cached token → the next call re-logs-in and
  succeeds (retry-on-401 path). Verify via logs showing one `/api/auth/login` then the
  original call.
- A worker with `password_hash IS NULL` gets the "set a personal password first" error on
  their first call.

**Phase 3 — admin (optional):**
- A non-admin worker calling an admin tool gets a clear 403-style error with no API call.
- An admin worker can upload and delete reference files; the result of
  `list_reference_forms` reflects the change.

### 9.11 Verification commands for the executing agent

Run from `C:\Homelab\officeForm` after `.\.venv\Scripts\activate`:

```powershell
# 1. Lint/type sanity (the repo has no strict typecheck; at least byte-compile):
python -c "import mcp_server, mcp_server.__main__"
node --check public\app.js      # only if you touched frontend (you should NOT)

# 2. Start the MCP server (it must coexist with the already-running Flask on :80):
python -m mcp_server

# 3. In another shell, smoke test health through the tunnel:
curl http://127.0.0.1:13001/healthz

# 4. Run the official inspector (best UX for manual tool calls):
npx @modelcontextprotocol/inspector
#   -> set Transport: Streamable HTTP
#   -> URL: http://127.0.0.1:13001/mcp
#   -> Headers: X-Api-Key: <test key>, X-Worker-Id: <test worker>
#   -> List Tools, then call each Phase 1 tool and inspect the JSON.
```

Do not commit changes. Leave the repo clean. Report back: which phases pass acceptance,
and any place where the Flask source contradicted this spec (it wins).

### 9.12 Known gotchas the executing agent must respect (from the API ref)

- The login response field is **`token`**, not `jwt`/`accessToken` (API ref §2/§21.1).
- All worker/submission JSON uses **camelCase**; DB columns are snake_case. The MCP server
  passes JSON through unchanged — do not rename. Only the DB read (`get_password_hash`)
  touches snake_case.
- `leaveSummary` keys are `entitlement`, `takenToDate`, `balanceBefore`, `balanceAfter`
  (camelCase) except the optional `remove_entitlement` flag (snake_case) — pass it
  through if present, don't "fix" it.
- `/api/submissions` and `/api/calendar` take **no query params** — any month/formType
  filtering is done client-side in the MCP server (§9.7).
- `kpi_data` column is reused for KPI, Expense, AND OT payloads; the API exposes it as
  `kpiData`/`expenseData`/`otData` depending on `formType`. Don't assume `kpiData` is null
  for non-KPI — use the right field per `formType`.
- `formType` is uppercase (`AL`,`EL`,`MC`,`KPI`,`EXP`,`OT`,`UNPAID`,`OTHER`);
  `leaveType` is lowercase (`annual`,`emergency`,`unpaid`,`other`). Don't conflate.
- `annualLeaveTaken` in the `workers` table is stale — always use the computed
  `worker.annualLeaveTaken` from the GET-worker response.
- `role` is appended only at the auth/worker endpoints; it is reliably on the login and
  GET-worker responses — cache it from login.
- `POST /api/admin/others` is **multipart/form-data** (field name `file`), the only
  non-JSON POST (§9.6 needs a dedicated method).
- PDF generation (KPI/EXP especially) can take many seconds → keep
  `REQUEST_TIMEOUT_SECONDS=90` and the Hermes client timeout ≥ 60s.
- Google Sheets sync is best-effort and happens server-side automatically on AL/EL/MC
  submit/update/delete. Do NOT attempt to surface Sheets sync status through MCP; if a
  user reports a missing calendar line, point them at `scripts/sync_google_sheets_backlog.py`.

### 9.13 Out of scope for the first deliverable

- `update_submission` (PUT) and `delete_submission` (DELETE) — defer past Phase 2.
- `submit_ot` (OT endpoint exists but AGENTS.md says no active UI) — defer.
- In-process MCP (Part 2 Option B) — not now.
- Dockerizing the MCP server into the Compose stack (D3 option 2) — not now; run on the
  host first.
- Resources/Prompts MCP primitives — skip (Part 1).
- Any change to the Flask app — forbidden (§9.0.1).

### 9.14 Definition of done

The first deliverable is done when **Phase 0 and Phase 1 pass all acceptance criteria
end-to-end through the SSH tunnel from the homelab**, using a real worker's
`X-Api-Key`/`X-Worker-Id`, verified with the MCP inspector. Phase 2 is a follow-up
deliverable gated on Phase 1 sign-off. The executing agent should stop after Phase 1 and
report back before starting Phase 2.
