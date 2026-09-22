from hashlib import sha256
from pathlib import Path

import pytest
from mcp.types import TextContent

from .support import (
    DIRECTION_MARKDOWN,
    assert_request_is_unavailable,
    authenticated_client,
    create_test_server,
    write_memory_page,
)


@pytest.mark.anyio
async def test_authenticated_proposal_returns_exact_identity_without_writing(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    replacement = DIRECTION_MARKDOWN.replace(
        "Build one small verified milestone.",
        "Build one small independently verified milestone.",
    )
    target = tmp_path / "memory" / "direction.md"
    server = create_test_server(tmp_path)

    async with authenticated_client(server) as client:
        result = await client.call_tool(
            "propose_update",
            {"page_id": "direction.md", "markdown": replacement},
        )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["page_id"] == "direction.md"
    assert result.structured_content["version_token"] == sha256(
        DIRECTION_MARKDOWN.encode("utf-8")
    ).hexdigest()
    assert result.structured_content["diff"] == (
        "--- a/memory/direction.md\n"
        "+++ b/memory/direction.md\n"
        "@@ -4,4 +4,4 @@\n"
        " related_pages: []\n"
        " ---\n"
        " \n"
        "-Build one small verified milestone.\n"
        "+Build one small independently verified milestone.\n"
    )
    proposal_id = result.structured_content["proposal_id"]
    assert isinstance(proposal_id, str)
    assert len(proposal_id) >= 32
    assert target.read_text(encoding="utf-8") == DIRECTION_MARKDOWN


@pytest.mark.anyio
async def test_each_authenticated_proposal_issues_a_distinct_id(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    server = create_test_server(tmp_path)

    async with authenticated_client(server) as client:
        first = await client.call_tool(
            "propose_update",
            {
                "page_id": "direction.md",
                "markdown": DIRECTION_MARKDOWN.replace("small", "focused"),
            },
        )
        second = await client.call_tool(
            "propose_update",
            {
                "page_id": "direction.md",
                "markdown": DIRECTION_MARKDOWN.replace("small", "bounded"),
            },
        )

    assert first.structured_content is not None
    assert second.structured_content is not None
    assert first.structured_content["proposal_id"] != second.structured_content[
        "proposal_id"
    ]


@pytest.mark.anyio
async def test_authenticated_proposal_reports_invalid_replacement_without_writing(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    target = tmp_path / "memory" / "direction.md"
    server = create_test_server(tmp_path)

    async with authenticated_client(server) as client:
        result = await client.call_tool(
            "propose_update",
            {"page_id": "direction.md", "markdown": DIRECTION_MARKDOWN},
        )

    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "change" in result.content[0].text
    assert target.read_text(encoding="utf-8") == DIRECTION_MARKDOWN


@pytest.mark.anyio
async def test_proposal_identifier_cannot_be_used_as_a_retrieval_identifier(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    replacement = DIRECTION_MARKDOWN.replace("small", "focused")
    server = create_test_server(tmp_path)

    async with authenticated_client(server) as client:
        proposal = await client.call_tool(
            "propose_update",
            {"page_id": "direction.md", "markdown": replacement},
        )
        assert proposal.structured_content is not None

        result = await client.call_tool(
            "read_memory",
            {
                "request_id": proposal.structured_content["proposal_id"],
                "selection": "direction.md",
            },
        )

    assert_request_is_unavailable(result)
