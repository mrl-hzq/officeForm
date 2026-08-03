from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import hmac
import threading
import time
from typing import Any

import jwt
import requests

from .config import Config


_current_worker_id: ContextVar[str | None] = ContextVar("mcp_worker_id", default=None)
_default_manager: AuthManager | None = None


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class _TokenEntry:
    token: str
    exp_epoch: float
    role: str | None


def set_current_worker_id(worker_id: str):
    return _current_worker_id.set(worker_id)


def reset_current_worker_id(token) -> None:
    _current_worker_id.reset(token)


def current_worker_id() -> str | None:
    return _current_worker_id.get()


class AuthManager:
    def __init__(self, config: Config):
        self.config = config
        self._session = requests.Session()
        self._tokens: dict[str, _TokenEntry] = {}
        self._lock = threading.RLock()

    def resolve_worker_id(self, request) -> str:
        api_key = request.headers.get("X-Api-Key", "")
        requested_worker_id = request.headers.get("X-Worker-Id", "").strip().upper()
        bound_worker_id = self.config.api_keys.get(api_key)
        if not bound_worker_id or not requested_worker_id or not hmac.compare_digest(
            bound_worker_id, requested_worker_id
        ):
            raise AuthError("Invalid MCP API key or worker identity.", 401)
        return bound_worker_id

    def get_jwt(self, worker_id: str) -> str:
        now = time.time()
        entry = self._tokens.get(worker_id)
        if entry and entry.exp_epoch - now > 60:
            return entry.token

        with self._lock:
            now = time.time()
            entry = self._tokens.get(worker_id)
            if entry and entry.exp_epoch - now > 60:
                return entry.token
            new_entry = self._service_login(worker_id)
            self._tokens[worker_id] = new_entry
            return new_entry.token

    def get_role(self, worker_id: str) -> str | None:
        with self._lock:
            entry = self._tokens.get(worker_id)
            return entry.role if entry else None

    def invalidate(self, worker_id: str) -> None:
        with self._lock:
            self._tokens.pop(worker_id, None)

    def _service_login(self, worker_id: str) -> _TokenEntry:
        try:
            response = self._session.post(
                f"{self.config.officeform_base_url}/api/auth/service-login",
                headers={"X-MCP-Service-Key": self.config.mcp_service_login_key},
                json={"workerId": worker_id},
                timeout=self.config.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise AuthError(f"Could not reach officeForm service-login: {exc}", 502) from exc

        payload = _json_payload(response)
        if response.status_code < 200 or response.status_code >= 300:
            self.invalidate(worker_id)
            raise AuthError(_error_message(payload, "Service login failed."), response.status_code)

        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise AuthError("Service login response did not contain a token.", 502)

        try:
            claims: dict[str, Any] = jwt.decode(token, options={"verify_signature": False})
            exp_epoch = float(claims["exp"])
        except (KeyError, TypeError, ValueError, jwt.PyJWTError) as exc:
            raise AuthError("Service login returned an invalid token.", 502) from exc

        worker = payload.get("worker") if isinstance(payload, dict) else None
        role = worker.get("role") if isinstance(worker, dict) else None
        return _TokenEntry(token=token, exp_epoch=exp_epoch, role=role)


def configure(config: Config) -> AuthManager:
    global _default_manager
    _default_manager = AuthManager(config)
    return _default_manager


def _manager() -> AuthManager:
    if _default_manager is None:
        raise RuntimeError("MCP authentication has not been configured.")
    return _default_manager


def resolve_worker_id(request) -> str:
    return _manager().resolve_worker_id(request)


def get_jwt(worker_id: str) -> str:
    return _manager().get_jwt(worker_id)


def get_role(worker_id: str) -> str | None:
    return _manager().get_role(worker_id)


def invalidate(worker_id: str) -> None:
    _manager().invalidate(worker_id)


def _json_payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"error": response.text or "Empty response from officeForm."}


def _error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return fallback
