from pathlib import Path

import pytest
from mcp.types import TextContent

from .support import authenticated_client, create_test_server, write_memory_page


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
