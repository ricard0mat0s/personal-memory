from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent

from .support import (
    DIRECTION_MARKDOWN,
    assert_request_is_unavailable,
    authenticated_client,
    connected_client,
    create_test_server,
    write_large_topic_pages,
    write_memory_page,
)


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
