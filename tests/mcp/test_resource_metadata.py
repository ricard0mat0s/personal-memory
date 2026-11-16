from pathlib import Path

import httpx2
import pytest
from mcp.types import TextContent

from personal_memory.mcp import create_mcp_server

from .support import (
    RESOURCE_SERVER_URL,
    StaticTokenVerifier,
    authenticated_client,
    create_test_server,
    write_memory_page,
)

METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"


async def fetch_resource_metadata(server) -> httpx2.Response:
    transport = httpx2.ASGITransport(app=server.streamable_http_app())
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8000"
    ) as http_client:
        return await http_client.get(METADATA_PATH)


@pytest.mark.anyio
async def test_resource_metadata_advertises_read_and_write_scopes(
    tmp_path: Path,
) -> None:
    response = await fetch_resource_metadata(create_test_server(tmp_path))

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["resource"] == RESOURCE_SERVER_URL
    assert metadata["authorization_servers"] == ["https://auth.example.com/"]
    assert metadata["scopes_supported"] == ["memory:read", "memory:write"]


@pytest.mark.anyio
async def test_resource_metadata_advertises_configured_scope_names(
    tmp_path: Path,
) -> None:
    server = create_mcp_server(
        tmp_path,
        token_verifier=StaticTokenVerifier(),
        issuer_url="https://auth.example.com",
        resource_server_url=RESOURCE_SERVER_URL,
        read_scope="notes:read",
        write_scope="notes:write",
    )

    response = await fetch_resource_metadata(server)

    assert response.json()["scopes_supported"] == ["notes:read", "notes:write"]


@pytest.mark.anyio
async def test_advertised_scopes_do_not_make_both_scopes_mandatory(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path)

    async with authenticated_client(server, "read-only-test-token") as client:
        search = await client.call_tool("search_memory", {"query": "direction"})
        assert not search.is_error
        assert search.structured_content is not None
        read = await client.call_tool(
            "read_memory",
            {
                "request_id": search.structured_content["request_id"],
                "selection": "direction.md",
            },
        )
        writes = [
            await client.call_tool(
                "propose_update", {"page_id": "direction.md", "markdown": "x"}
            ),
            await client.call_tool("apply_update", {"proposal_id": "not-issued"}),
        ]

    assert not read.is_error
    for write in writes:
        assert write.is_error
        assert isinstance(write.content[0], TextContent)
        assert "memory:write" in write.content[0].text
