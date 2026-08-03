from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from .auth import AuthManager, _manager


class ApiError(Exception):
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload
        super().__init__(_error_message(payload, f"officeForm API returned HTTP {status_code}."))


class ApiClient:
    def __init__(self, base_url: str, timeout: float, auth: AuthManager | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth = auth or _manager()
        self.session = requests.Session()

    def get(self, worker_id: str, path: str):
        return self._request("GET", worker_id, path)

    def post(self, worker_id: str, path: str, json_body: dict[str, Any]):
        return self._request("POST", worker_id, path, json_body=json_body)

    def put(self, worker_id: str, path: str, json_body: dict[str, Any]):
        return self._request("PUT", worker_id, path, json_body=json_body)

    def delete(self, worker_id: str, path: str):
        return self._request("DELETE", worker_id, path)

    def post_multipart(self, worker_id: str, path: str, file_field: str, file_path: str | Path):
        for attempt in range(2):
            token = self.auth.get_jwt(worker_id)
            try:
                with Path(file_path).open("rb") as handle:
                    response = self.session.post(
                        self._url(path),
                        headers={"Authorization": f"Bearer {token}"},
                        files={file_field: handle},
                        timeout=self.timeout,
                    )
            except OSError as exc:
                raise ApiError(400, {"error": f"Could not read upload file: {exc}"}) from exc
            except requests.RequestException as exc:
                raise ApiError(502, {"error": f"Could not reach officeForm API: {exc}"}) from exc
            if response.status_code == 401 and attempt == 0:
                self.auth.invalidate(worker_id)
                continue
            return self._finish(response)
        raise AssertionError("unreachable")

    def _request(
        self,
        method: str,
        worker_id: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ):
        for attempt in range(2):
            token = self.auth.get_jwt(worker_id)
            try:
                response = self.session.request(
                    method,
                    self._url(path),
                    headers={"Authorization": f"Bearer {token}"},
                    json=json_body,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise ApiError(502, {"error": f"Could not reach officeForm API: {exc}"}) from exc
            if response.status_code == 401 and attempt == 0:
                self.auth.invalidate(worker_id)
                continue
            return self._finish(response)
        raise AssertionError("unreachable")

    def _url(self, path: str) -> str:
        if not path.startswith("/api/"):
            raise ValueError("API paths must start with /api/.")
        return f"{self.base_url}{path}"

    @staticmethod
    def _finish(response: requests.Response):
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": response.text or "Empty response from officeForm."}
        if response.status_code < 200 or response.status_code >= 300:
            raise ApiError(response.status_code, payload)
        return payload


def worker_path(worker_id: str) -> str:
    return f"/api/workers/{quote(worker_id, safe='')}"


def _error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return fallback
