"""Run authenticated MCP search against a local memory workspace without a network."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.provider import AccessToken, TokenVerifier

from personal_memory.mcp import create_mcp_server


RESOURCE_SERVER_URL = "http://127.0.0.1:8000/mcp"
SMOKE_TOKEN = "local-smoke-test-token"


class SmokeTokenVerifier(TokenVerifier):
    """Accept one local synthetic token for this one-process smoke test."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if token != SMOKE_TOKEN:
            return None
        return AccessToken(
            token=token,
            client_id="local-smoke-test",
            scopes=["memory:read"],
            resource=RESOURCE_SERVER_URL,
            subject="local-user",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search real Markdown files through authenticated in-process MCP. "
            "The workspace must contain a memory/ directory."
        )
    )
    parser.add_argument("workspace", type=Path)
    parser.add_argument("query")
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        help="Limit results to one Memory Scope; repeat for multiple scopes.",
    )
    return parser.parse_args()


async def run_search(
    workspace: Path,
    query: str,
    scopes: list[str] | None,
) -> None:
    server = create_mcp_server(
        workspace,
        token_verifier=SmokeTokenVerifier(),
        issuer_url="https://auth.example.com",
        resource_server_url=RESOURCE_SERVER_URL,
        required_scopes=("memory:read",),
    )
    transport = httpx2.ASGITransport(app=server.streamable_http_app())
    async with server.session_manager.run():
        async with (
            httpx2.AsyncClient(
                transport=transport,
                base_url=RESOURCE_SERVER_URL,
                headers={"Authorization": f"Bearer {SMOKE_TOKEN}"},
            ) as http_client,
            Client(
                streamable_http_client(
                    RESOURCE_SERVER_URL,
                    http_client=http_client,
                )
            ) as client,
        ):
            arguments: dict[str, object] = {"query": query}
            if scopes is not None:
                arguments["scopes"] = scopes
            result = await client.call_tool("search_memory", arguments)

    if result.is_error or result.structured_content is None:
        detail = result.content[0] if result.content else "No error detail returned."
        raise SystemExit(f"Authenticated search failed: {detail}")
    print(json.dumps(result.structured_content, indent=2, ensure_ascii=False))


def main() -> None:
    args = parse_args()
    asyncio.run(run_search(args.workspace, args.query, args.scopes))


if __name__ == "__main__":
    main()
