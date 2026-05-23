"""BotSpace MCP Server — HTTP+SSE transport with OAuth.

Runs as a standalone HTTP server. Users connect via:
  https://botspace.uz/mcp/sse

Authentication: Bearer token in Authorization header.
The token is the user's BotSpace access JWT (from dashboard login).
"""

from __future__ import annotations

import asyncio
import logging
import os

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from .tools import register_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("botspace-mcp")


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token")


def create_app() -> Starlette:
    server = Server("botspace-mcp")
    sse = SseServerTransport("/messages/")

    register_tools(server)

    async def handle_sse(request: Request) -> Response:
        token = _extract_bearer(request)
        if not token:
            return JSONResponse(
                {"error": "Missing Authorization header. Use: Bearer <your-botspace-token>"},
                status_code=401,
            )
        request.state.token = token
        async with sse.connect_sse(request.scope, request.receive, request._send) as (
            read_stream,
            write_stream,
        ):
            await server.run(read_stream, write_stream, server.create_initialization_options())
        return Response()

    async def handle_messages(request: Request) -> Response:
        return await sse.handle_post_message(request.scope, request.receive, request._send)

    async def handle_health(request: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "botspace-mcp", "version": "0.2.0"})

    app = Starlette(
        routes=[
            Route("/health", handle_health),
            Route("/sse", handle_sse),
            Route("/messages/", handle_messages, methods=["POST"]),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
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
