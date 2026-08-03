from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    officeform_base_url: str
    mcp_host: str
    mcp_port: int
    mcp_api_keys_file: Path
    mcp_service_login_key: str
    request_timeout_seconds: float
    log_level: str
    api_keys: Mapping[str, str]


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set.")
    return value


def _load_api_keys(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        logger.warning("MCP API-key file does not exist: %s", path)
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load MCP API-key file %s: %s", path, exc)
        return {}

    if not isinstance(raw, dict):
        logger.warning("MCP API-key file must contain an object: %s", path)
        return {}

    result: dict[str, str] = {}
    for api_key, entry in raw.items():
        if not isinstance(api_key, str) or not api_key or not isinstance(entry, dict):
            continue
        worker_id = entry.get("workerId")
        if isinstance(worker_id, str) and worker_id.strip():
            result[api_key] = worker_id.strip().upper()
    return result


def load_config() -> Config:
    load_dotenv()
    api_keys_file = Path(os.environ.get("MCP_API_KEYS_FILE", "secrets/mcp_api_keys.json"))
    mcp_host = os.environ.get("MCP_HOST", "127.0.0.1")
    if mcp_host != "127.0.0.1":
        raise RuntimeError("MCP_HOST must be 127.0.0.1 for the SSH-tunnel deployment.")
    return Config(
        officeform_base_url=_required_env("OFFICEFORM_BASE_URL").rstrip("/"),
        mcp_host=mcp_host,
        mcp_port=int(os.environ.get("MCP_PORT", "3001")),
        mcp_api_keys_file=api_keys_file,
        mcp_service_login_key=_required_env("MCP_SERVICE_LOGIN_KEY"),
        request_timeout_seconds=float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "90")),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        api_keys=_load_api_keys(api_keys_file),
    )
