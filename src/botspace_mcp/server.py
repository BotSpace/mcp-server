"""BotSpace MCP Server — Streamable HTTP + legacy SSE transport.

Endpoint: https://api.botspace.uz/mcp/
Authentication: Bearer token in Authorization header.
"""

from __future__ import annotations

import logging
import os
import uuid

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import StreamableHTTPServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

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
    register_tools(server)

    # Legacy SSE transport
    sse = SseServerTransport("/messages/")

    # ── Streamable HTTP (new MCP transport — single POST endpoint) ──

    async def handle_mcp(request: Request) -> Response:
        if request.method == "GET":
            # SSE stream initiation
            token = _extract_bearer(request)
            if not token:
                return JSONResponse({"error": "Bearer token required"}, status_code=401)
            async with sse.connect_sse(request.scope, request.receive, request._send) as (rs, ws):
                await server.run(rs, ws, server.create_initialization_options())
            return Response()

        if request.method == "POST":
            # Streamable HTTP or SSE message post
            accept = request.headers.get("accept", "")
            content_type = request.headers.get("content-type", "")

            # If it's an SSE message post (from legacy /messages/ path redirected here)
            # Check if this is a Streamable HTTP request (JSON-RPC over HTTP)
            if "application/json" in content_type:
                token = _extract_bearer(request)
                if not token:
                    return JSONResponse({"error": "Bearer token required"}, status_code=401)

                transport = StreamableHTTPServerTransport(
                    mcp_session_id=str(uuid.uuid4()),
                    is_stateless=True,
                )
                async with transport.connect() as (rs, ws):
                    import asyncio
                    run_task = asyncio.create_task(
                        server.run(rs, ws, server.create_initialization_options())
                    )
                    response = await transport.handle_request(
                        request.scope, request.receive, request._send
                    )
                    run_task.cancel()
                    try:
                        await run_task
                    except asyncio.CancelledError:
                        pass
                return response

            # Fallback: legacy SSE message post
            return await sse.handle_post_message(request.scope, request.receive, request._send)

        if request.method == "DELETE":
            return JSONResponse({"status": "session_terminated"})

        return JSONResponse({"error": "Method not allowed"}, status_code=405)

    async def handle_messages(request: Request) -> Response:
        return await sse.handle_post_message(request.scope, request.receive, request._send)

    async def handle_health(request: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "botspace-mcp", "version": "0.3.0"})

    app = Starlette(
        routes=[
            Route("/health", handle_health),
            Route("/", handle_mcp, methods=["GET", "POST", "DELETE"]),
            Route("/sse", handle_mcp, methods=["GET", "POST", "DELETE"]),
            Route("/messages/", handle_messages, methods=["POST"]),
        ],
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
