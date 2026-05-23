"""BotSpace API async client.

Supports two modes:
1. Static token (env var BOTSPACE_API_TOKEN) — for local stdio usage
2. Per-request token — for HTTP server mode (each user has own token)
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class BotSpaceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"BotSpace API error {status_code}: {detail}")


class BotSpaceClient:
    def __init__(
        self,
        api_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self.api_url = (
            api_url or os.getenv("BOTSPACE_API_URL", "https://api.botspace.uz")
        ).rstrip("/")
        self.token = token or os.getenv("BOTSPACE_API_TOKEN", "")
        self._client = httpx.AsyncClient(base_url=self.api_url, timeout=30.0)

    def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        try:
            r = await self._client.request(method, path, headers=headers, **kwargs)
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = str(exc)
            try:
                body = exc.response.json()
                detail = body.get("detail") or body.get("message") or str(body)
            except Exception:
                pass
            raise BotSpaceError(exc.response.status_code, detail) from exc

        try:
            data = r.json()
        except Exception:
            return {}

        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, dict) and "results" in inner:
                return inner["results"]
            return inner
        return data

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- Projects --
    async def list_projects(self) -> list[dict]:
        return await self._request("GET", "/api/project/")

    async def get_project(self, project_id: str | int) -> dict:
        return await self._request("GET", f"/api/project/{project_id}/")

    async def create_project(self, name: str, description: str = "") -> dict:
        return await self._request("POST", "/api/project/", json={"name": name, "description": description})

    async def update_project(self, project_id: str | int, payload: dict) -> dict:
        return await self._request("PATCH", f"/api/project/{project_id}/", json=payload)

    # -- Flow --
    async def get_flow(self, project_id: str | int) -> dict:
        project = await self.get_project(project_id)
        flow = project.get("flow") or {}
        if not isinstance(flow, dict):
            flow = {}
        flow.setdefault("nodes", [])
        flow.setdefault("edges", [])
        return flow

    async def save_flow(self, project_id: str | int, flow: dict) -> dict:
        return await self.update_project(project_id, {"flow": flow})

    # -- Release --
    async def deploy(self, project_id: str | int) -> dict:
        return await self._request("POST", "/api/relase/", json={"project": project_id})

    # -- Env --
    async def list_env(self, project_id: str | int) -> list[dict]:
        return await self._request("GET", f"/api/enviroment/?project={project_id}")

    async def set_env(self, project_id: str | int, key: str, value: str) -> dict:
        existing = await self.list_env(project_id)
        for env in existing:
            if env.get("key") == key:
                return await self._request("PATCH", f"/api/enviroment/{env['id']}/", json={"value": value})
        return await self._request("POST", "/api/enviroment/", json={"project": project_id, "key": key, "value": value})

    # -- Subscription --
    async def get_subscription(self) -> dict:
        return await self._request("GET", "/api/subscription/")

    async def list_plans(self) -> list[dict]:
        return await self._request("GET", "/api/plans/")
