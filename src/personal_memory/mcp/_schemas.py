"""JSON-safe Pydantic schemas for MCP structured tool responses."""

from pydantic import BaseModel, ConfigDict

from personal_memory.workspace import SearchResult


class McpSearchResult(BaseModel):
    """JSON-safe Search Result returned through MCP."""

    model_config = ConfigDict(frozen=True)

    page_id: str
    title: str
    scope: str
    excerpt: str
    matched_fields: tuple[str, ...]


class AuthenticatedSearchResult(BaseModel):
    """One bounded Retrieval Request and its initial candidates."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    results: tuple[McpSearchResult, ...]


class AuthenticatedReadResult(BaseModel):
    """Complete Current Memory returned through MCP."""

    model_config = ConfigDict(frozen=True)

    markdown: str


class AuthenticatedProposalResult(BaseModel):
    """Inspectable proposal identity retained for later explicit approval."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str
    page_id: str
    version_token: str | None
    diff: str


class AuthenticatedAppliedResult(BaseModel):
    """Applied update identity after its single Git recording."""

    model_config = ConfigDict(frozen=True)

    page_id: str
    previous_version_token: str | None
    version_token: str


def to_mcp_search_result(result: SearchResult) -> McpSearchResult:
    """Translate a domain SearchResult into its JSON-safe MCP representation."""
    return McpSearchResult(
        page_id=result.page_id,
        title=result.title,
        scope=result.scope,
        excerpt=result.excerpt,
        matched_fields=result.matched_fields,
    )
