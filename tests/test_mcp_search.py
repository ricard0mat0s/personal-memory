from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import httpx2
import pytest
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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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


@pytest.mark.anyio
async def test_authorized_search_returns_results_and_an_opaque_request_id(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path)
    async with authenticated_client(server) as client:
        result = await client.call_tool(
            "search_memory",
            {"query": "direction"},
        )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["results"] == [
        {
            "page_id": "direction.md",
            "title": "Project direction",
            "scope": "individual_project",
            "excerpt": "Build one small verified milestone",
            "matched_fields": ["title"],
        }
    ]
    request_id = result.structured_content["request_id"]
    assert isinstance(request_id, str)
    assert len(request_id) >= 32


@pytest.mark.anyio
@pytest.mark.parametrize("selection", ["direction.md", "Project direction"])
async def test_authenticated_read_returns_complete_current_candidate(
    tmp_path: Path,
    selection: str,
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path)
    async with authenticated_client(server) as client:
        search = await client.call_tool("search_memory", {"query": "direction"})
        assert search.structured_content is not None

        result = await client.call_tool(
            "read_memory",
            {
                "request_id": search.structured_content["request_id"],
                "selection": selection,
            },
        )

    assert not result.is_error
    assert result.structured_content == {
        "markdown": DIRECTION_MARKDOWN,
    }


@pytest.mark.anyio
async def test_authenticated_read_refuses_another_principals_request(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path)
    app = server.streamable_http_app()
    async with server.session_manager.run():
        async with connected_client(app, "valid-test-token") as owner:
            search = await owner.call_tool("search_memory", {"query": "direction"})
            assert search.structured_content is not None
        async with connected_client(app, "other-user-test-token") as other_user:
            result = await other_user.call_tool(
                "read_memory",
                {
                    "request_id": search.structured_content["request_id"],
                    "selection": "direction.md",
                },
            )

    assert_request_is_unavailable(result)


@pytest.mark.anyio
async def test_authenticated_read_refuses_an_expired_request(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path, request_ttl_seconds=1)
    async with authenticated_client(server) as client:
        search = await client.call_tool("search_memory", {"query": "direction"})
        assert search.structured_content is not None
        await anyio.sleep(1.01)

        result = await client.call_tool(
            "read_memory",
            {
                "request_id": search.structured_content["request_id"],
                "selection": "direction.md",
            },
        )

    assert_request_is_unavailable(result)


@pytest.mark.anyio
async def test_authenticated_read_refuses_an_evicted_request(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path, max_pending_requests=1)
    async with authenticated_client(server) as client:
        first = await client.call_tool("search_memory", {"query": "direction"})
        second = await client.call_tool("search_memory", {"query": "direction"})
        assert first.structured_content is not None
        assert second.structured_content is not None

        evicted = await client.call_tool(
            "read_memory",
            {
                "request_id": first.structured_content["request_id"],
                "selection": "direction.md",
            },
        )
        retained = await client.call_tool(
            "read_memory",
            {
                "request_id": second.structured_content["request_id"],
                "selection": "direction.md",
            },
        )

    assert evicted.is_error
    assert evicted.structured_content is None
    assert not retained.is_error
    assert retained.structured_content == {"markdown": DIRECTION_MARKDOWN}


@pytest.mark.anyio
async def test_authenticated_read_rejects_unknown_request_before_memory_is_opened(
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    (memory_root / "unsafe.md").write_text(
        "This invalid page proves the workspace was never opened.",
        encoding="utf-8",
    )
    server = create_test_server(tmp_path)
    async with authenticated_client(server) as client:
        result = await client.call_tool(
            "read_memory",
            {
                "request_id": "not-an-issued-request-id",
                "selection": "unsafe.md",
            },
        )

    assert_request_is_unavailable(result)


@pytest.mark.anyio
async def test_authenticated_read_shares_the_search_request_word_budget(
    tmp_path: Path,
) -> None:
    write_large_topic_pages(tmp_path)
    server = create_test_server(tmp_path)
    async with authenticated_client(server) as client:
        search = await client.call_tool("search_memory", {"query": "topic"})
        assert search.structured_content is not None
        request_id = search.structured_content["request_id"]

        first = await client.call_tool(
            "read_memory",
            {"request_id": request_id, "selection": "a.md"},
        )
        second = await client.call_tool(
            "read_memory",
            {"request_id": request_id, "selection": "b.md"},
        )
        exhausted = await client.call_tool(
            "read_memory",
            {"request_id": request_id, "selection": "c.md"},
        )

    assert not first.is_error
    assert not second.is_error
    assert exhausted.is_error
    assert exhausted.structured_content is None
    assert len(exhausted.content) == 1
    assert isinstance(exhausted.content[0], TextContent)
    assert "word cap" in exhausted.content[0].text


@pytest.mark.anyio
async def test_concurrent_authenticated_reads_preserve_the_shared_word_budget(
    tmp_path: Path,
) -> None:
    write_large_topic_pages(tmp_path)
    server = create_test_server(tmp_path)
    app = server.streamable_http_app()
    concurrent_results: list[CallToolResult] = []

    async def read_candidate(client: Client, request_id: str, page_id: str) -> None:
        concurrent_results.append(
            await client.call_tool(
                "read_memory",
                {"request_id": request_id, "selection": page_id},
            )
        )

    async with server.session_manager.run():
        async with (
            connected_client(app, "valid-test-token") as first_client,
            connected_client(app, "valid-test-token") as second_client,
        ):
            search = await first_client.call_tool(
                "search_memory",
                {"query": "topic"},
            )
            assert search.structured_content is not None
            request_id = search.structured_content["request_id"]
            first = await first_client.call_tool(
                "read_memory",
                {"request_id": request_id, "selection": "a.md"},
            )
            assert not first.is_error

            async with anyio.create_task_group() as task_group:
                task_group.start_soon(
                    read_candidate,
                    first_client,
                    request_id,
                    "b.md",
                )
                task_group.start_soon(
                    read_candidate,
                    second_client,
                    request_id,
                    "c.md",
                )

    assert len(concurrent_results) == 2
    assert sorted(result.is_error is True for result in concurrent_results) == [
        False,
        True,
    ]


@pytest.mark.anyio
async def test_authenticated_read_refuses_a_page_outside_search_candidates(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    (tmp_path / "memory" / "other.md").write_text(
        """\
---
title: Other notes
scope: individual_project
related_pages: []
---

This page was not a search result.
""",
        encoding="utf-8",
    )
    server = create_test_server(tmp_path)
    async with authenticated_client(server) as client:
        search = await client.call_tool("search_memory", {"query": "direction"})
        assert search.structured_content is not None

        result = await client.call_tool(
            "read_memory",
            {
                "request_id": search.structured_content["request_id"],
                "selection": "other.md",
            },
        )

    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "Search Results" in result.content[0].text


@pytest.mark.anyio
async def test_in_memory_transport_cannot_bypass_read_authorization(
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    (memory_root / "unsafe.md").write_text(
        "This invalid page proves the workspace was never opened.",
        encoding="utf-8",
    )
    server = create_test_server(tmp_path)

    async with Client(server) as client:
        result = await client.call_tool(
            "read_memory",
            {"request_id": "not-issued", "selection": "unsafe.md"},
        )

    assert result.is_error
    assert result.structured_content is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer rejected-test-token"},
        {"Authorization": "Bearer wrong-resource-test-token"},
    ],
)
async def test_unauthorized_search_is_refused_before_memory_is_opened(
    tmp_path: Path,
    headers: dict[str, str],
) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    (memory_root / "unsafe.md").write_text(
        "This invalid page proves the workspace was never opened.",
        encoding="utf-8",
    )
    server = create_test_server(tmp_path)
    transport = httpx2.ASGITransport(app=server.streamable_http_app())

    async with httpx2.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
    ) as http_client:
        response = await http_client.post("/mcp", json={}, headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_token",
        "error_description": "Authentication required",
    }


@pytest.mark.anyio
async def test_in_memory_transport_cannot_bypass_search_authorization(
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    (memory_root / "unsafe.md").write_text(
        "This invalid page proves the workspace was never opened.",
        encoding="utf-8",
    )
    server = create_test_server(tmp_path)

    async with Client(server) as client:
        result = await client.call_tool("search_memory", {"query": "direction"})

    assert result.is_error
    assert result.structured_content is None


@pytest.mark.anyio
async def test_search_requires_the_configured_read_scope(tmp_path: Path) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    (memory_root / "unsafe.md").write_text(
        "This invalid page proves the workspace was never opened.",
        encoding="utf-8",
    )
    server = create_test_server(tmp_path)
    transport = httpx2.ASGITransport(app=server.streamable_http_app())

    async with httpx2.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer wrong-scope-test-token"},
    ) as http_client:
        response = await http_client.post("/mcp", json={})

    assert response.status_code == 403
    assert response.json()["error"] == "insufficient_scope"


@pytest.mark.anyio
async def test_authenticated_search_reports_invalid_queries_as_tool_errors(
    tmp_path: Path,
) -> None:
    (tmp_path / "memory").mkdir()
    server = create_test_server(tmp_path)
    async with authenticated_client(server) as client:
        result = await client.call_tool("search_memory", {"query": "  "})

    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "non-empty" in result.content[0].text


@pytest.mark.anyio
async def test_each_authenticated_search_issues_a_distinct_request_id(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path)
    async with authenticated_client(server) as client:
        first = await client.call_tool("search_memory", {"query": "direction"})
        second = await client.call_tool("search_memory", {"query": "direction"})

    assert first.structured_content is not None
    assert second.structured_content is not None
    assert first.structured_content["request_id"] != second.structured_content["request_id"]


@pytest.mark.anyio
async def test_authenticated_search_honors_explicit_memory_scopes(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    (tmp_path / "memory" / "career.md").write_text(
        """\
---
title: Career direction
scope: career_and_job_opportunities
related_pages: []
---

Choose one direction to explore.
""",
        encoding="utf-8",
    )
    server = create_test_server(tmp_path)
    async with authenticated_client(server) as client:
        result = await client.call_tool(
            "search_memory",
            {
                "query": "direction",
                "scopes": ["career_and_job_opportunities"],
            },
        )

    assert result.structured_content is not None
    assert [
        item["page_id"] for item in result.structured_content["results"]
    ] == ["career.md"]
