from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import uvicorn

from .api_client import ApiClient
from .auth import AuthError, AuthManager, configure, reset_current_worker_id, set_current_worker_id
from .config import Config, load_config
from .tools_read import register_read_tools


class WorkerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, auth: AuthManager):
        super().__init__(app)
        self.auth = auth

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/healthz":
            return await call_next(request)
        try:
            worker_id = self.auth.resolve_worker_id(request)
        except AuthError as exc:
            return JSONResponse({"error": exc.message}, status_code=exc.status_code)

        request.state.worker_id = worker_id
        context_token = set_current_worker_id(worker_id)
        try:
            return await call_next(request)
        finally:
            reset_current_worker_id(context_token)


def build_app(config: Config):
    auth = configure(config)
    api = ApiClient(config.officeform_base_url, config.request_timeout_seconds, auth)
    mcp = FastMCP(
        "officeForm",
        instructions="Read-only officeForm tools for the authenticated worker.",
        host=config.mcp_host,
        port=config.mcp_port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        log_level=config.log_level,
    )
    register_read_tools(mcp, api)

    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> Response:
        return JSONResponse({"ok": True})

    app = mcp.streamable_http_app()
    app.add_middleware(WorkerAuthMiddleware, auth=auth)
    return app


def main() -> None:
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger(__name__).info(
        "officeForm MCP listening on %s:%s", config.mcp_host, config.mcp_port
    )
    uvicorn.run(
        build_app(config),
        host=config.mcp_host,
        port=config.mcp_port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
