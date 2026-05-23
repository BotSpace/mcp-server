"""BotSpace OAuth provider for MCP server.

Flow:
1. Claude → GET /authorize → redirect to BotSpace login page
2. User logs in on BotSpace, approves → BotSpace redirects back with code
3. Claude → POST /token with code → gets access_token
4. Claude uses access_token as Bearer for MCP requests
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from pydantic import AnyHttpUrl

from mcp.server.auth.provider import (
    AuthorizationCodeT,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    OAuthClientInformationFull,
)

logger = logging.getLogger("botspace-mcp.auth")

BOTSPACE_URL = os.getenv("BOTSPACE_SITE_URL", "https://botspace.uz")
BOTSPACE_API_URL = os.getenv("BOTSPACE_API_URL", "https://api.botspace.uz")


class AuthCode:
    def __init__(self, code: str, client_id: str, redirect_uri: str, code_challenge: str, scopes: list[str]):
        self.code = code
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.code_challenge = code_challenge
        self.scopes = scopes
        self.created_at = time.time()
        self.api_token: str | None = None


class MCPAccessToken:
    def __init__(self, token: str, client_id: str, scopes: list[str], expires_at: int):
        self.token = token
        self.client_id = client_id
        self.scopes = scopes
        self.expires_at = expires_at
        self.jwt: str | None = None


class BotSpaceOAuthProvider:
    """OAuth 2.1 provider that delegates login to BotSpace dashboard."""

    def __init__(self):
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthCode] = {}
        self._tokens: dict[str, MCPAccessToken] = {}
        self._pending_auth: dict[str, AuthCode] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info.client_id = secrets.token_hex(16)
        if not client_info.client_secret:
            client_info.client_secret = secrets.token_hex(32)
        client_info.client_id_issued_at = int(time.time())
        client_info.client_secret_expires_at = 0
        self._clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        code = secrets.token_hex(32)
        auth_code = AuthCode(
            code=code,
            client_id=client.client_id or "",
            redirect_uri=str(params.redirect_uri),
            code_challenge=params.code_challenge,
            scopes=params.scopes or [],
        )
        self._auth_codes[code] = auth_code
        self._pending_auth[code] = auth_code

        callback_url = f"{BOTSPACE_API_URL}/mcp/oauth/callback"
        botspace_auth_url = f"{BOTSPACE_URL}/mcp-auth?" + urlencode({
            "code": code,
            "callback": callback_url,
            "redirect_uri": str(params.redirect_uri),
            "state": params.state or "",
        })
        return botspace_auth_url

    async def handle_callback(self, code: str, api_token: str, state: str) -> str:
        """Called by BotSpace after user approves — exchanges API token for auth code."""
        auth_code = self._pending_auth.get(code)
        if not auth_code:
            raise ValueError("Invalid or expired authorization code")
        auth_code.api_token = api_token
        redirect = auth_code.redirect_uri
        qs = urlencode({"code": code, "state": state})
        sep = "&" if "?" in redirect else "?"
        return f"{redirect}{sep}{qs}"

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> AuthCode | None:
        ac = self._auth_codes.get(authorization_code)
        if not ac:
            return None
        if ac.client_id != client.client_id:
            return None
        if time.time() - ac.created_at > 300:
            self._auth_codes.pop(authorization_code, None)
            return None
        return ac

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthCode) -> MCPAccessToken:
        self._auth_codes.pop(authorization_code.code, None)
        self._pending_auth.pop(authorization_code.code, None)

        jwt_token = None
        if authorization_code.api_token:
            try:
                async with httpx.AsyncClient(base_url=BOTSPACE_API_URL, timeout=10) as c:
                    r = await c.post("/auth/token/exchange/", json={"token": authorization_code.api_token})
                    r.raise_for_status()
                    data = r.json()
                    inner = data.get("data", data)
                    jwt_token = inner.get("access")
            except Exception:
                logger.warning("Failed to exchange API token for JWT", exc_info=True)

        access = secrets.token_hex(32)
        expires_at = int(time.time()) + 86400 * 30
        tok = MCPAccessToken(
            token=access,
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            expires_at=expires_at,
        )
        tok.jwt = jwt_token
        self._tokens[access] = tok
        return tok

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> None:
        return None

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token, scopes: list[str] | None = None) -> MCPAccessToken:
        raise NotImplementedError("Refresh tokens not supported")

    async def load_access_token(self, token: str) -> MCPAccessToken | None:
        t = self._tokens.get(token)
        if t and t.expires_at < time.time():
            self._tokens.pop(token, None)
            return None
        return t

    async def revoke_token(self, client: OAuthClientInformationFull, token: str, token_type_hint: str | None = None) -> None:
        self._tokens.pop(token, None)
        self._auth_codes.pop(token, None)

    def get_jwt_for_token(self, access_token: str) -> str | None:
        t = self._tokens.get(access_token)
        return t.jwt if t else None
