"""Exercise the installed launcher over real loopback HTTP sockets."""

from pathlib import Path
from dataclasses import replace

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from cryptography.hazmat.primitives.asymmetric import rsa

from .process_support import RunningServer, running_server
from .support import DIRECTION_MARKDOWN


def initialize(server: RunningServer, token: str | None = None) -> httpx2.Response:
    headers = {"Accept": "application/json, text/event-stream"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return httpx2.post(
        server.url, headers=headers,
        json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "process-test", "version": "1"},
            },
        },
        timeout=5, trust_env=False,
    )


def test_launched_server_refuses_missing_token(tmp_path: Path) -> None:
    with running_server(tmp_path) as server:
        assert initialize(server).status_code == 401


@pytest.mark.anyio
async def test_launched_server_searches_and_reads_with_owner_token(tmp_path: Path) -> None:
    with running_server(tmp_path) as server:
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {server.sign()}"}, trust_env=False,
        ) as http_client:
            async with Client(streamable_http_client(server.url, http_client=http_client)) as client:
                listing = await client.list_tools()
                assert {tool.name for tool in listing.tools} == {
                    "search_memory", "read_memory", "propose_update", "apply_update",
                }
                search = await client.call_tool("search_memory", {"query": "direction"})
                assert not search.is_error
                assert search.structured_content is not None
                assert search.structured_content["results"][0]["page_id"] == "direction.md"
                result = await client.call_tool("read_memory", {
                    "request_id": search.structured_content["request_id"],
                    "selection": "direction.md",
                })
                assert result.structured_content == {"markdown": DIRECTION_MARKDOWN}


def test_launched_server_refuses_bad_signature(tmp_path: Path) -> None:
    with running_server(tmp_path) as server:
        impostor = replace(server, signing_key=rsa.generate_private_key(
            public_exponent=65537, key_size=2048,
        ))
        assert initialize(server, impostor.sign()).status_code == 401


@pytest.mark.parametrize("claims", [
    {"iss": "https://wrong-issuer.invalid/"},
    {"aud": "wrong-api"},
    {"exp": 1},
    {"sub": "another-owner"},
])
def test_launched_server_refuses_invalid_token_claims(tmp_path: Path, claims: dict[str, object]) -> None:
    with running_server(tmp_path) as server:
        assert initialize(server, server.sign(**claims)).status_code == 401


@pytest.mark.anyio
async def test_launched_server_refuses_search_without_read_scope(tmp_path: Path) -> None:
    with running_server(tmp_path) as server:
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {server.sign(scope='')}"}, trust_env=False,
        ) as http_client:
            async with Client(streamable_http_client(server.url, http_client=http_client)) as client:
                result = await client.call_tool("search_memory", {"query": "direction"})
                assert result.is_error
                assert result.structured_content is None
                assert isinstance(result.content[0], TextContent)
                assert "memory:read" in result.content[0].text


@pytest.mark.parametrize(("host", "cli_host", "expected_host"), [
    ("127.0.0.2", None, "127.0.0.2"),
    ("127.0.0.2", "127.0.0.1", "127.0.0.1"),
])
def test_launcher_uses_configured_bind_address(
    tmp_path: Path, host: str, cli_host: str | None, expected_host: str,
) -> None:
    with running_server(tmp_path, host=host, cli_host=cli_host) as server:
        assert server.url.startswith(f"http://{expected_host}:")
        assert initialize(server).status_code == 401
