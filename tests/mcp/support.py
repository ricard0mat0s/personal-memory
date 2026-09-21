from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.types import CallToolResult, TextContent
from starlette.types import ASGIApp

from personal_memory.mcp import create_mcp_server


RESOURCE_SERVER_URL = "http://127.0.0.1:8000/mcp"
DIRECTION_MARKDOWN = """\
---
title: Project direction
scope: individual_project
related_pages: []
---

Build one small verified milestone.
"""


class StaticTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if token == "wrong-resource-test-token":
            return AccessToken(
                token=token,
                client_id="synthetic-client",
                scopes=["memory:read"],
                resource="https://other.example.com/mcp",
                subject="synthetic-user",
            )
        if token == "wrong-scope-test-token":
            return AccessToken(
                token=token,
                client_id="synthetic-client",
                scopes=["memory:write"],
                resource=RESOURCE_SERVER_URL,
                subject="synthetic-user",
            )
        if token not in {"valid-test-token", "other-user-test-token"}:
            return None
        return AccessToken(
            token=token,
            client_id="synthetic-client",
            scopes=["memory:read"],
            resource=RESOURCE_SERVER_URL,
            subject=(
                "other-synthetic-user"
                if token == "other-user-test-token"
                else "synthetic-user"
            ),
        )


def write_memory_page(workspace_root: Path) -> None:
    memory_root = workspace_root / "memory"
    memory_root.mkdir()
    (memory_root / "direction.md").write_text(
        DIRECTION_MARKDOWN,
        encoding="utf-8",
    )


def write_large_topic_pages(workspace_root: Path) -> None:
    memory_root = workspace_root / "memory"
    memory_root.mkdir()
    for name in ("a", "b", "c"):
        body = "topic " + " ".join(f"{name}{index}" for index in range(800))
        (memory_root / f"{name}.md").write_text(
            f"""\
---
title: Topic {name}
scope: individual_project
related_pages: []
---

{body}
""",
            encoding="utf-8",
        )


def assert_request_is_unavailable(result: CallToolResult) -> None:
    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.endswith("Retrieval Request is unavailable.")


def create_test_server(
    workspace_root: Path,
    *,
    max_pending_requests: int = 128,
    request_ttl_seconds: int = 15 * 60,
) -> MCPServer:
    return create_mcp_server(
        workspace_root,
        token_verifier=StaticTokenVerifier(),
        issuer_url="https://auth.example.com",
        resource_server_url=RESOURCE_SERVER_URL,
        required_scopes=("memory:read",),
        max_pending_requests=max_pending_requests,
        request_ttl_seconds=request_ttl_seconds,
    )


@asynccontextmanager
async def connected_client(
    app: ASGIApp,
    token: str,
) -> AsyncIterator[Client]:
    transport = httpx2.ASGITransport(app=app)
    async with (
        httpx2.AsyncClient(
            transport=transport,
            base_url=RESOURCE_SERVER_URL,
            headers={"Authorization": f"Bearer {token}"},
        ) as http_client,
        Client(
            streamable_http_client(
                RESOURCE_SERVER_URL,
                http_client=http_client,
            )
        ) as client,
    ):
        yield client


@asynccontextmanager
async def authenticated_client(server: MCPServer) -> AsyncIterator[Client]:
    app = server.streamable_http_app()
    async with server.session_manager.run():
        async with connected_client(app, "valid-test-token") as client:
            yield client
