from pathlib import Path

import httpx2
import pytest
from mcp import Client
from mcp.types import TextContent

from personal_memory.mcp import create_mcp_server

from .support import (
    RESOURCE_SERVER_URL,
    StaticTokenVerifier,
    authenticated_client,
    create_test_server,
    write_memory_page,
)


def write_unsafe_memory_page(workspace_root: Path) -> None:
    memory_root = workspace_root / "memory"
    memory_root.mkdir()
    (memory_root / "unsafe.md").write_text(
        "This invalid page proves the workspace was never opened.",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("read_scope", "write_scope"),
    [
        ("", "memory:write"),
        ("memory:read", ""),
        ("memory:read", "memory:read"),
    ],
)
def test_server_refuses_blank_or_equal_read_and_write_scopes(
    tmp_path: Path,
    read_scope: str,
    write_scope: str,
) -> None:
    with pytest.raises(ValueError, match="distinct non-empty"):
        create_mcp_server(
            tmp_path,
            token_verifier=StaticTokenVerifier(),
            issuer_url="https://auth.example.com",
            resource_server_url=RESOURCE_SERVER_URL,
            read_scope=read_scope,
            write_scope=write_scope,
        )


@pytest.mark.anyio
async def test_in_memory_transport_cannot_bypass_read_authorization(
    tmp_path: Path,
) -> None:
    write_unsafe_memory_page(tmp_path)
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
    write_unsafe_memory_page(tmp_path)
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
    write_unsafe_memory_page(tmp_path)
    server = create_test_server(tmp_path)

    async with Client(server) as client:
        result = await client.call_tool("search_memory", {"query": "direction"})

    assert result.is_error
    assert result.structured_content is None


@pytest.mark.anyio
async def test_in_memory_transport_cannot_bypass_proposal_authorization(
    tmp_path: Path,
) -> None:
    write_unsafe_memory_page(tmp_path)
    server = create_test_server(tmp_path)

    async with Client(server) as client:
        result = await client.call_tool(
            "propose_update",
            {"page_id": "unsafe.md", "markdown": "replacement"},
        )

    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "Authentication is required" in result.content[0].text


@pytest.mark.anyio
async def test_in_memory_transport_cannot_bypass_application_authorization(
    tmp_path: Path,
) -> None:
    write_unsafe_memory_page(tmp_path)
    server = create_test_server(tmp_path)

    async with Client(server) as client:
        result = await client.call_tool(
            "apply_update",
            {"proposal_id": "not-issued"},
        )

    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "Authentication is required" in result.content[0].text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            "propose_update",
            {"page_id": "direction.md", "markdown": "replacement"},
        ),
        ("apply_update", {"proposal_id": "not-issued"}),
    ],
)
async def test_read_only_token_cannot_invoke_write_tools(
    tmp_path: Path,
    tool_name: str,
    arguments: dict[str, str],
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path)

    async with authenticated_client(server, "read-only-test-token") as client:
        result = await client.call_tool(tool_name, arguments)

    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "memory:write" in result.content[0].text


@pytest.mark.anyio
async def test_write_only_token_cannot_invoke_read_tools(tmp_path: Path) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path)

    async with authenticated_client(server, "write-only-test-token") as client:
        result = await client.call_tool("search_memory", {"query": "direction"})

    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "memory:read" in result.content[0].text
