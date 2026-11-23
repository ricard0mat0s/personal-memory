"""MCP tool handlers and registration for Personal Memory."""

from dataclasses import dataclass

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from personal_memory.git import GitRecordingError, UpdateRecorder
from personal_memory.mcp._authz import require_scope
from personal_memory.mcp._schemas import (
    AuthenticatedAppliedResult,
    AuthenticatedProposalResult,
    AuthenticatedReadResult,
    AuthenticatedSearchResult,
    to_mcp_search_result,
)
from personal_memory.mcp._state import LazyWorkspace, PendingProposal, StateRegistry
from personal_memory.workspace import (
    AppliedUpdate,
    ExplicitApproval,
    MemoryApplicationError,
    MemoryProposalError,
    MemoryRetrievalError,
    MemoryValidationError,
    RetrievalRequest,
)

AVAILABLE_TOOLS = frozenset(
    {
        "search_memory",
        "read_memory",
        "propose_create",
        "propose_update",
        "apply_update",
    }
)

# Clients use these hints to decide when to ask the owner before calling a tool.
_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_NON_DESTRUCTIVE_WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, open_world_hint=False
)
_DESTRUCTIVE_WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, open_world_hint=False
)


@dataclass(frozen=True, slots=True)
class ToolRuntime:
    """Shared dependencies used by registered MCP tool handlers."""

    workspace: LazyWorkspace
    requests: StateRegistry[RetrievalRequest]
    proposals: StateRegistry[PendingProposal]
    recorder: UpdateRecorder
    read_scope: str
    write_scope: str


def validate_exposed_tools(exposed_tools: frozenset[str] | None) -> frozenset[str]:
    """Validate an optional tool allowlist and return the active tool set."""
    if exposed_tools is None:
        return AVAILABLE_TOOLS
    unknown_tools = exposed_tools - AVAILABLE_TOOLS
    if unknown_tools:
        raise ValueError(
            f"Unknown exposed tool(s): {', '.join(sorted(unknown_tools))}."
        )
    return exposed_tools


def register_tools(
    server: MCPServer,
    runtime: ToolRuntime,
    exposed_tools: frozenset[str],
) -> None:
    """Register the configured Personal Memory tools on the MCP server."""

    def search_memory(
        query: str,
        scopes: list[str] | None = None,
    ) -> AuthenticatedSearchResult:
        """Search permitted memory within one bounded Retrieval Request."""
        access_token = require_scope(runtime.read_scope)
        request = RetrievalRequest(
            query=query,
            scopes=tuple(scopes) if scopes is not None else None,
        )
        try:
            results = runtime.workspace.get().search_memory(request)
        except MemoryRetrievalError as error:
            raise ToolError(str(error)) from error
        request_id = runtime.requests.issue(request, access_token)
        return AuthenticatedSearchResult(
            request_id=request_id,
            results=tuple(to_mcp_search_result(result) for result in results),
        )

    def read_memory(request_id: str, selection: str) -> AuthenticatedReadResult:
        """Read complete Current Memory selected from an authenticated search."""
        access_token = require_scope(runtime.read_scope)
        try:
            with runtime.requests.use(request_id, access_token) as request:
                markdown = runtime.workspace.get().read_memory(request, selection)
        except MemoryRetrievalError as error:
            raise ToolError(str(error)) from error
        return AuthenticatedReadResult(markdown=markdown)

    def propose_create(page_id: str, markdown: str) -> AuthenticatedProposalResult:
        """Propose creating a new top-level Memory Page without changing Current Memory."""
        access_token = require_scope(runtime.write_scope)
        proposal_workspace = runtime.workspace.fresh()
        try:
            proposal = proposal_workspace.propose_create(page_id, markdown)
        except (MemoryProposalError, MemoryValidationError) as error:
            raise ToolError(str(error)) from error
        proposal_id = runtime.proposals.issue(
            PendingProposal(workspace=proposal_workspace, proposal=proposal),
            access_token,
        )
        return AuthenticatedProposalResult(
            proposal_id=proposal_id,
            page_id=proposal.page_id,
            version_token=proposal.version_token,
            diff=proposal.diff,
        )

    def propose_update(page_id: str, markdown: str) -> AuthenticatedProposalResult:
        """Propose complete replacement Markdown without changing Current Memory."""
        access_token = require_scope(runtime.write_scope)
        proposal_workspace = runtime.workspace.fresh()
        try:
            proposal = proposal_workspace.propose_update(page_id, markdown)
        except (MemoryProposalError, MemoryValidationError) as error:
            raise ToolError(str(error)) from error
        proposal_id = runtime.proposals.issue(
            PendingProposal(workspace=proposal_workspace, proposal=proposal),
            access_token,
        )
        return AuthenticatedProposalResult(
            proposal_id=proposal_id,
            page_id=proposal.page_id,
            version_token=proposal.version_token,
            diff=proposal.diff,
        )

    def apply_update(proposal_id: str) -> AuthenticatedAppliedResult:
        """Apply and commit a proposed update after the user approves its exact diff."""
        access_token = require_scope(runtime.write_scope)

        try:
            with runtime.proposals.use(proposal_id, access_token) as pending:
                is_create = pending.proposal.version_token is None

                def record_applied_update(applied: AppliedUpdate) -> None:
                    runtime.recorder.record(
                        applied.page_id,
                        applied.version_token,
                        create=is_create,
                    )

                runtime.recorder.prepare(
                    pending.proposal.page_id,
                    create=is_create,
                )
                applied = pending.workspace.apply_update(
                    pending.proposal,
                    ExplicitApproval.for_proposal(pending.proposal),
                    after_application=record_applied_update,
                )
                runtime.proposals.discard(proposal_id, pending)
        except (
            GitRecordingError,
            MemoryApplicationError,
            MemoryProposalError,
            MemoryValidationError,
        ) as error:
            raise ToolError(str(error)) from error
        return AuthenticatedAppliedResult(
            page_id=applied.page_id,
            previous_version_token=applied.previous_version_token,
            version_token=applied.version_token,
        )

    tool_registrations = (
        ("search_memory", search_memory, _READ_ONLY),
        ("read_memory", read_memory, _READ_ONLY),
        ("propose_create", propose_create, _NON_DESTRUCTIVE_WRITE),
        ("propose_update", propose_update, _NON_DESTRUCTIVE_WRITE),
        ("apply_update", apply_update, _DESTRUCTIVE_WRITE),
    )
    for name, handler, annotations in tool_registrations:
        if name in exposed_tools:
            server.tool(structured_output=True, annotations=annotations)(handler)
