"""Authenticated MCP adapter for the Personal Memory workspace."""

from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from _thread import LockType
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from typing import Generic, TypeVar

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier, principal_components
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import AnyHttpUrl, BaseModel, ConfigDict

from personal_memory._git_recording import (
    GitRecordingError,
    GitUpdateRecorder,
    UpdateRecorder,
)
from personal_memory import (
    AppliedUpdate,
    ExplicitApproval,
    MemoryApplicationError,
    MemoryProposalError,
    MemoryRetrievalError,
    MemoryValidationError,
    MemoryWorkspace,
    ProposedUpdate,
    RetrievalRequest,
    SearchResult,
)


DEFAULT_MAX_PENDING_REQUESTS = 128
DEFAULT_REQUEST_TTL_SECONDS = 15 * 60
DEFAULT_MAX_PENDING_PROPOSALS = 128
DEFAULT_PROPOSAL_TTL_SECONDS = 15 * 60
DEFAULT_READ_SCOPE = "memory:read"
DEFAULT_WRITE_SCOPE = "memory:write"


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
    version_token: str
    diff: str


class AuthenticatedAppliedResult(BaseModel):
    """Applied update identity after its single Git recording."""

    model_config = ConfigDict(frozen=True)

    page_id: str
    previous_version_token: str
    version_token: str


_State = TypeVar("_State")


@dataclass(frozen=True, slots=True)
class _PendingState(Generic[_State]):
    value: _State
    principal: tuple[str, str | None, str | None]
    expires_at: float
    lock: LockType = field(default_factory=Lock, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _PendingProposal:
    workspace: MemoryWorkspace
    proposal: ProposedUpdate


class _StateRegistry(Generic[_State]):
    def __init__(
        self,
        max_entries: int,
        ttl_seconds: int,
        *,
        max_entries_name: str,
        ttl_name: str,
        unavailable_error: Callable[[], Exception],
    ) -> None:
        if max_entries < 1:
            raise ValueError(f"{max_entries_name} must be positive.")
        if ttl_seconds < 1:
            raise ValueError(f"{ttl_name} must be positive.")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, _PendingState[_State]] = OrderedDict()
        self._unavailable_error = unavailable_error
        self._lock = Lock()

    def issue(self, value: _State, access_token: AccessToken) -> str:
        now = monotonic()
        with self._lock:
            self._discard_expired(now)
            while len(self._entries) >= self._max_entries:
                self._entries.popitem(last=False)
            state_id = token_urlsafe(32)
            self._entries[state_id] = _PendingState(
                value=value,
                principal=principal_components(access_token),
                expires_at=now + self._ttl_seconds,
            )
        return state_id

    @contextmanager
    def use(
        self,
        state_id: str,
        access_token: AccessToken,
    ) -> Iterator[_State]:
        principal = principal_components(access_token)
        with self._lock:
            self._discard_expired(monotonic())
            pending = self._entries.get(state_id)
            if pending is None or pending.principal != principal:
                raise self._unavailable_error()

        with pending.lock:
            with self._lock:
                self._discard_expired(monotonic())
                current = self._entries.get(state_id)
                if current is not pending or current.principal != principal:
                    raise self._unavailable_error()
            yield pending.value

    def _discard_expired(self, now: float) -> None:
        expired_ids = [
            state_id
            for state_id, pending in self._entries.items()
            if pending.expires_at <= now
        ]
        for state_id in expired_ids:
            self._entries.pop(state_id)

    def discard(self, state_id: str, value: _State) -> None:
        """Release successfully consumed state without removing a replacement."""
        with self._lock:
            pending = self._entries.get(state_id)
            if pending is not None and pending.value is value:
                self._entries.pop(state_id)


class _LazyWorkspace:
    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = workspace_root
        self._workspace: MemoryWorkspace | None = None
        self._lock = Lock()

    def get(self) -> MemoryWorkspace:
        with self._lock:
            if self._workspace is None:
                self._workspace = MemoryWorkspace(self._workspace_root)
            return self._workspace

    def fresh(self) -> MemoryWorkspace:
        return MemoryWorkspace(self._workspace_root)


def _mcp_result(result: SearchResult) -> McpSearchResult:
    return McpSearchResult(
        page_id=result.page_id,
        title=result.title,
        scope=result.scope,
        excerpt=result.excerpt,
        matched_fields=result.matched_fields,
    )


def _require_scope(scope: str) -> AccessToken:
    access_token = get_access_token()
    if access_token is None:
        raise ToolError("Authentication is required.")
    if scope not in access_token.scopes:
        raise ToolError(f"The {scope!r} scope is required.")
    return access_token


def create_mcp_server(
    workspace_root: str | Path,
    *,
    token_verifier: TokenVerifier,
    issuer_url: str,
    resource_server_url: str,
    read_scope: str = DEFAULT_READ_SCOPE,
    write_scope: str = DEFAULT_WRITE_SCOPE,
    max_pending_requests: int = DEFAULT_MAX_PENDING_REQUESTS,
    request_ttl_seconds: int = DEFAULT_REQUEST_TTL_SECONDS,
    max_pending_proposals: int = DEFAULT_MAX_PENDING_PROPOSALS,
    proposal_ttl_seconds: int = DEFAULT_PROPOSAL_TTL_SECONDS,
    update_recorder: UpdateRecorder | None = None,
) -> MCPServer:
    """Create the authenticated MCP boundary for one Canonical Memory workspace."""
    configured_scopes = (read_scope, write_scope)
    if (
        any(
            not isinstance(scope, str)
            or not scope
            or scope != scope.strip()
            for scope in configured_scopes
        )
        or read_scope == write_scope
    ):
        raise ValueError("read_scope and write_scope must be distinct non-empty strings.")
    workspace = _LazyWorkspace(workspace_root)
    requests = _StateRegistry[RetrievalRequest](
        max_pending_requests,
        request_ttl_seconds,
        max_entries_name="max_pending_requests",
        ttl_name="request_ttl_seconds",
        unavailable_error=lambda: MemoryRetrievalError(
            "Retrieval Request is unavailable."
        ),
    )
    proposals = _StateRegistry[_PendingProposal](
        max_pending_proposals,
        proposal_ttl_seconds,
        max_entries_name="max_pending_proposals",
        ttl_name="proposal_ttl_seconds",
        unavailable_error=lambda: MemoryProposalError(
            "Proposed Update is unavailable."
        ),
    )
    recorder = update_recorder or GitUpdateRecorder(workspace_root)
    server = MCPServer(
        "Personal Memory",
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer_url),
            resource_server_url=AnyHttpUrl(resource_server_url),
            required_scopes=[],
            validate_token_resource=True,
        ),
    )

    @server.tool(structured_output=True)
    def search_memory(
        query: str,
        scopes: list[str] | None = None,
    ) -> AuthenticatedSearchResult:
        """Search permitted memory within one bounded Retrieval Request."""
        access_token = _require_scope(read_scope)
        request = RetrievalRequest(
            query=query,
            scopes=tuple(scopes) if scopes is not None else None,
        )
        try:
            results = workspace.get().search_memory(request)
        except MemoryRetrievalError as error:
            raise ToolError(str(error)) from error
        request_id = requests.issue(request, access_token)
        return AuthenticatedSearchResult(
            request_id=request_id,
            results=tuple(_mcp_result(result) for result in results),
        )

    @server.tool(structured_output=True)
    def read_memory(request_id: str, selection: str) -> AuthenticatedReadResult:
        """Read complete Current Memory selected from an authenticated search."""
        access_token = _require_scope(read_scope)
        try:
            with requests.use(request_id, access_token) as request:
                markdown = workspace.get().read_memory(request, selection)
        except MemoryRetrievalError as error:
            raise ToolError(str(error)) from error
        return AuthenticatedReadResult(markdown=markdown)

    @server.tool(structured_output=True)
    def propose_update(page_id: str, markdown: str) -> AuthenticatedProposalResult:
        """Propose complete replacement Markdown without changing Current Memory."""
        access_token = _require_scope(write_scope)
        proposal_workspace = workspace.fresh()
        try:
            proposal = proposal_workspace.propose_update(page_id, markdown)
        except (MemoryProposalError, MemoryValidationError) as error:
            raise ToolError(str(error)) from error
        proposal_id = proposals.issue(
            _PendingProposal(workspace=proposal_workspace, proposal=proposal),
            access_token,
        )
        return AuthenticatedProposalResult(
            proposal_id=proposal_id,
            page_id=proposal.page_id,
            version_token=proposal.version_token,
            diff=proposal.diff,
        )

    @server.tool(structured_output=True)
    def apply_update(proposal_id: str) -> AuthenticatedAppliedResult:
        """Explicitly approve, apply, and Git-record one exact proposed update."""
        access_token = _require_scope(write_scope)

        def record_applied_update(applied: AppliedUpdate) -> None:
            recorder.record(applied.page_id, applied.version_token)

        try:
            with proposals.use(proposal_id, access_token) as pending:
                recorder.prepare(pending.proposal.page_id)
                applied = pending.workspace.apply_update(
                    pending.proposal,
                    ExplicitApproval.for_proposal(pending.proposal),
                    after_application=record_applied_update,
                )
                proposals.discard(proposal_id, pending)
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

    return server
