from __future__ import annotations

from datetime import datetime, timezone, timedelta
from functools import wraps
import hmac
import re

import jwt
import pymysql
from flask import Blueprint, jsonify, request, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash

from .db import get_db, query_one
from .utils import normalize_worker_id

bp = Blueprint("auth", __name__)

WORKER_ID_PATTERN = re.compile(r"^[A-Z0-9_-]{1,20}$")


def _validate_worker_id(worker_id: str) -> str | None:
    if WORKER_ID_PATTERN.fullmatch(worker_id):
        return None
    return "Worker ID must be 1-20 characters and use only letters, numbers, underscore, or dash."


def _shared_password_is_valid(password: object) -> bool:
    expected = current_app.config["AUTH_SHARED_PASSWORD"]
    return isinstance(password, str) and hmac.compare_digest(password, expected)


def _personal_password_is_valid(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return check_password_hash(password_hash, password)


def _make_token(worker_id: str) -> str:
    secret = current_app.config["JWT_SECRET_KEY"]
    expiry = current_app.config["JWT_EXPIRY_HOURS"]
    payload = {
        "sub": worker_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=expiry),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _get_user_role(worker_id: str) -> str:
    try:
        row = query_one("SELECT role FROM users WHERE worker_id = %s", (worker_id,))
    except pymysql.err.OperationalError as exc:
        if exc.args and exc.args[0] == 1054:
            return "worker"
        raise
    if not row:
        return "worker"
    return row.get("role") or "worker"


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header."}), 401
        token = auth_header[len("Bearer "):]
        try:
            secret = current_app.config["JWT_SECRET_KEY"]
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            g.worker_id = payload["sub"]
            g.user_role = _get_user_role(g.worker_id)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired. Please log in again."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token."}), 401
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if getattr(g, "user_role", "worker") != "admin":
            return jsonify({"error": "Admin access required."}), 403
        return f(*args, **kwargs)
    return decorated


@bp.post("/api/auth/register")
def register():
    body = request.get_json(silent=True) or {}
    worker_id = normalize_worker_id(body.get("workerId"))
    if not worker_id:
        return jsonify({"error": "Worker ID is required."}), 400
    validation_error = _validate_worker_id(worker_id)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    raw_password = body.get("password")
    if not raw_password or not isinstance(raw_password, str) or len(raw_password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    existing = query_one("SELECT id FROM users WHERE worker_id = %s", (worker_id,))
    if existing:
        return jsonify({"error": "An account with this Worker ID already exists."}), 409

    pw_hash = generate_password_hash(raw_password)

    db = get_db()
    try:
        db.begin()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO users (worker_id, password_hash) VALUES (%s, %s)",
            (worker_id, pw_hash),
        )
        cursor.execute(
            "INSERT INTO workers (worker_id, name) VALUES (%s, %s)",
            (worker_id, worker_id),
        )
        db.commit()
    except pymysql.err.IntegrityError:
        db.rollback()
        return jsonify({"error": "An account with this Worker ID already exists."}), 409
    except Exception:
        db.rollback()
        raise

    token = _make_token(worker_id)
    return jsonify({"token": token, "worker": _get_auth_worker(worker_id)}), 201


@bp.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    worker_id = normalize_worker_id(body.get("workerId"))
    if not worker_id:
        return jsonify({"error": "Worker ID is required."}), 400

    raw_password = body.get("password")
    if not isinstance(raw_password, str) or not raw_password:
        return jsonify({"error": "Password is required."}), 400

    user = query_one(
        "SELECT id, password_hash FROM users WHERE worker_id = %s",
        (worker_id,),
    )
    if not user:
        return jsonify({"error": "No account found for this Worker ID. Please register first."}), 404

    stored_hash = user.get("password_hash")
    personal_ok = _personal_password_is_valid(raw_password, stored_hash)
    shared_ok = _shared_password_is_valid(raw_password)

    if not personal_ok and not shared_ok:
        return jsonify({"error": "Invalid password."}), 401

    token = _make_token(worker_id)
    return jsonify({"token": token, "worker": _get_auth_worker(worker_id)})


def _get_auth_worker(worker_id: str) -> dict:
    from .workers import _get_worker_enriched

    worker = _get_worker_enriched(worker_id)
    if worker:
        worker["role"] = _get_user_role(worker_id)
        return worker

    row = query_one("SELECT * FROM workers WHERE worker_id = %s", (worker_id,))
    worker = _serialize_worker(row)
    worker["role"] = _get_user_role(worker_id)
    return worker


def _serialize_worker(row: dict | None) -> dict:
    if not row:
        return {}
    return {
        "workerId": row.get("worker_id"),
        "name": row.get("name"),
        "designation": row.get("designation"),
        "department": row.get("department"),
        "houseTel": row.get("house_tel"),
        "otherTel": row.get("other_tel"),
        "evaluatorName": row.get("evaluator_name"),
        "calendarName": row.get("calendar_name"),
        "annualLeaveEntitlement": float(row.get("annual_leave_entitlement") or 0),
        "annualLeaveTaken": float(row.get("annual_leave_taken") or 0),
        "employmentType": row.get("employment_type"),
        "employmentStartDate": row.get("employment_start_date").isoformat() if row.get("employment_start_date") else None,
        "employmentEndDate": row.get("employment_end_date").isoformat() if row.get("employment_end_date") else None,
        "profileComplete": bool(row.get("profile_complete")),
    }
