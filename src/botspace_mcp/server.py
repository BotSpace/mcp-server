"""BotSpace MCP Server — Streamable HTTP with OAuth login.

Users connect via: https://api.botspace.uz/mcp/
Auth: OAuth 2.1 — user clicks Authenticate in Claude, logs in on BotSpace, approves.
"""

from __future__ import annotations

import asyncio
import logging
import os

from mcp.server import Server
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.streamable_http import StreamableHTTPServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from pydantic import AnyHttpUrl

from .auth import BotSpaceOAuthProvider
from .tools import register_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("botspace-mcp")

MCP_BASE_URL: AnyHttpUrl = AnyHttpUrl(os.getenv("MCP_BASE_URL", "https://api.botspace.uz/mcp"))


def create_app() -> Starlette:
    server = Server("botspace-mcp")
    register_tools(server)

    provider = BotSpaceOAuthProvider()

    auth_routes = create_auth_routes(
        provider=provider,
        issuer_url=MCP_BASE_URL,
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=["botspace"]),
        revocation_options=RevocationOptions(enabled=True),
    )

    async def oauth_callback(request: Request) -> Response:
        code = request.query_params.get("code", "")
        api_token = request.query_params.get("api_token", "")
        state = request.query_params.get("state", "")
        if not code or not api_token:
            return JSONResponse({"error": "Missing code or api_token"}, status_code=400)
        try:
            redirect_url = await provider.handle_callback(code, api_token, state)
            return RedirectResponse(redirect_url)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def handle_mcp(request: Request) -> Response:
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None

        if request.method == "POST":
            if not token:
                return JSONResponse({"error": "Bearer token required"}, status_code=401)
            transport = StreamableHTTPServerTransport(
                mcp_session_id=None,
                is_json_response_enabled=True,
            )
            async with transport.connect() as (rs, ws):
                task = asyncio.create_task(
                    server.run(rs, ws, server.create_initialization_options())
                )
                response = await transport.handle_request(
                    request.scope, request.receive, request._send
                )
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            return response

        if request.method == "DELETE":
            return JSONResponse({"status": "session_terminated"})
        return JSONResponse({"error": "Method not allowed"}, status_code=405)

    async def handle_health(request: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "botspace-mcp", "version": "0.4.0"})

    all_routes = [
        Route("/health", handle_health),
        Route("/oauth/callback", oauth_callback),
        Route("/mcp", handle_mcp, methods=["POST", "DELETE", "OPTIONS"]),
    ] + auth_routes

    app = Starlette(
        routes=all_routes,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
                expose_headers=["mcp-session-id"],
            ),
        ],
    )
    return app


def main() -> None:
    import uvicorn

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8200"))
    logger.info(f"Starting BotSpace MCP Server on {host}:{port}")
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
