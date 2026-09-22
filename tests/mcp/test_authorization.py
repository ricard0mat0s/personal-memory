from pathlib import Path

import httpx2
import pytest
from mcp import Client
from mcp.types import TextContent

from .support import create_test_server


def write_unsafe_memory_page(workspace_root: Path) -> None:
    memory_root = workspace_root / "memory"
    memory_root.mkdir()
    (memory_root / "unsafe.md").write_text(
        "This invalid page proves the workspace was never opened.",
        encoding="utf-8",
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
async def test_search_requires_the_configured_read_scope(tmp_path: Path) -> None:
    write_unsafe_memory_page(tmp_path)
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
