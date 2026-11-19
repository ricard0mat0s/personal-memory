"""Authenticated MCP adapter for the Personal Memory workspace."""

from pathlib import Path

from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from personal_memory.git import GitUpdateRecorder, UpdateRecorder
from personal_memory.mcp._authz import (
    DEFAULT_READ_SCOPE,
    DEFAULT_WRITE_SCOPE,
    ScopeAdvertisingServer,
    validate_scopes,
)
from personal_memory.mcp._schemas import (
    AuthenticatedAppliedResult,
    AuthenticatedProposalResult,
    AuthenticatedReadResult,
    AuthenticatedSearchResult,
    McpSearchResult,
)
from personal_memory.mcp._state import (
    DEFAULT_MAX_PENDING_PROPOSALS,
    DEFAULT_MAX_PENDING_REQUESTS,
    DEFAULT_PROPOSAL_TTL_SECONDS,
    DEFAULT_REQUEST_TTL_SECONDS,
    LazyWorkspace,
    PendingProposal,
    StateRegistry,
)
from personal_memory.mcp._tools import (
    ToolRuntime,
    register_tools,
    validate_exposed_tools,
)
from personal_memory.workspace import (
    MemoryProposalError,
    MemoryRetrievalError,
    RetrievalRequest,
)

__all__ = [
    "AuthenticatedAppliedResult",
    "AuthenticatedProposalResult",
    "AuthenticatedReadResult",
    "AuthenticatedSearchResult",
    "DEFAULT_MAX_PENDING_PROPOSALS",
    "DEFAULT_MAX_PENDING_REQUESTS",
    "DEFAULT_PROPOSAL_TTL_SECONDS",
    "DEFAULT_READ_SCOPE",
    "DEFAULT_REQUEST_TTL_SECONDS",
    "DEFAULT_WRITE_SCOPE",
    "McpSearchResult",
    "create_mcp_server",
]


def create_mcp_server(
    workspace_root: str | Path,
    *,
    token_verifier: TokenVerifier,
    issuer_url: str,
    resource_server_url: str,
    exposed_tools: frozenset[str] | None = None,
    read_scope: str = DEFAULT_READ_SCOPE,
    write_scope: str = DEFAULT_WRITE_SCOPE,
    max_pending_requests: int = DEFAULT_MAX_PENDING_REQUESTS,
    request_ttl_seconds: int = DEFAULT_REQUEST_TTL_SECONDS,
    max_pending_proposals: int = DEFAULT_MAX_PENDING_PROPOSALS,
    proposal_ttl_seconds: int = DEFAULT_PROPOSAL_TTL_SECONDS,
    update_recorder: UpdateRecorder | None = None,
) -> MCPServer:
    """Create the authenticated MCP boundary for one Canonical Memory workspace."""
    active_tools = validate_exposed_tools(exposed_tools)
    configured_scopes = validate_scopes(read_scope, write_scope)
    runtime = ToolRuntime(
        workspace=LazyWorkspace(workspace_root),
        requests=StateRegistry[RetrievalRequest](
            max_pending_requests,
            request_ttl_seconds,
            max_entries_name="max_pending_requests",
            ttl_name="request_ttl_seconds",
            unavailable_error=lambda: MemoryRetrievalError(
                "Retrieval Request is unavailable."
            ),
        ),
        proposals=StateRegistry[PendingProposal](
            max_pending_proposals,
            proposal_ttl_seconds,
            max_entries_name="max_pending_proposals",
            ttl_name="proposal_ttl_seconds",
            unavailable_error=lambda: MemoryProposalError(
                "Proposed Update is unavailable."
            ),
        ),
        recorder=update_recorder or GitUpdateRecorder(workspace_root),
        read_scope=read_scope,
        write_scope=write_scope,
    )
    server = ScopeAdvertisingServer(
        "Personal Memory",
        advertised_scopes=configured_scopes,
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer_url),
            resource_server_url=AnyHttpUrl(resource_server_url),
            required_scopes=[],
            validate_token_resource=True,
        ),
    )
    register_tools(server, runtime, active_tools)
    return server
