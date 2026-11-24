from pathlib import Path

import pytest
from mcp.types import Tool

from .support import authenticated_client, create_test_server

EXPECTED_SCOPE_MEANINGS = (
    ("personal_history", "Personal History"),
    ("career_and_job_opportunities", "Career & Job Opportunities"),
    ("organization_work_context", "Organization/Work Context"),
    ("individual_project", "Individual Project"),
)


def _tool_metadata_text(tool: Tool) -> str:
    parts = [tool.description or ""]
    properties = tool.input_schema.get("properties", {})
    if isinstance(properties, dict):
        for schema in properties.values():
            if isinstance(schema, dict) and isinstance(schema.get("description"), str):
                parts.append(schema["description"])
    return "\n".join(parts)


@pytest.mark.anyio
async def test_tools_list_exposes_permitted_memory_scopes_and_meanings(
    tmp_path: Path,
) -> None:
    async with authenticated_client(create_test_server(tmp_path)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    for tool_name in ("search_memory", "propose_create", "propose_update"):
        metadata = _tool_metadata_text(tools[tool_name])
        for scope_id, meaning in EXPECTED_SCOPE_MEANINGS:
            assert scope_id in metadata, f"{scope_id} missing from {tool_name}"
            assert meaning in metadata, f"{meaning} missing from {tool_name}"

    scopes_description = tools["search_memory"].input_schema["properties"]["scopes"][
        "description"
    ]
    for scope_id, meaning in EXPECTED_SCOPE_MEANINGS:
        assert scope_id in scopes_description
        assert meaning in scopes_description


@pytest.mark.anyio
async def test_proposal_tools_list_frontmatter_and_new_page_slug_guidance(
    tmp_path: Path,
) -> None:
    async with authenticated_client(create_test_server(tmp_path)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    for tool_name in ("propose_create", "propose_update"):
        markdown_description = tools[tool_name].input_schema["properties"]["markdown"][
            "description"
        ]
        assert "YAML frontmatter" in markdown_description
        assert "title" in markdown_description
        assert "scope" in markdown_description
        assert "related_pages" in markdown_description
        assert "memory/" in markdown_description

    page_id_description = tools["propose_create"].input_schema["properties"]["page_id"][
        "description"
    ]
    assert r"^[a-z0-9][a-z0-9_-]*\.md$" in page_id_description
    assert "memory/" in page_id_description
    assert "top-level" in page_id_description


@pytest.mark.anyio
async def test_tools_list_preserves_existing_input_schema_structure(
    tmp_path: Path,
) -> None:
    async with authenticated_client(create_test_server(tmp_path)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools["search_memory"].input_schema["properties"]) == {"query", "scopes"}
    assert tools["search_memory"].input_schema["required"] == ["query"]
    assert set(tools["propose_create"].input_schema["properties"]) == {
        "page_id",
        "markdown",
    }
    assert tools["propose_create"].input_schema["required"] == ["page_id", "markdown"]
    assert set(tools["propose_update"].input_schema["properties"]) == {
        "page_id",
        "markdown",
    }
    assert tools["propose_update"].input_schema["required"] == ["page_id", "markdown"]
