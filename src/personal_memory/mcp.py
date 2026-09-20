"""Authenticated MCP adapter for the Personal Memory workspace."""

from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from _thread import LockType
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
from time import monotonic

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier, principal_components
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import AnyHttpUrl, BaseModel, ConfigDict

from personal_memory import (
    MemoryRetrievalError,
    MemoryWorkspace,
    RetrievalRequest,
    SearchResult,
)


DEFAULT_MAX_PENDING_REQUESTS = 128
DEFAULT_REQUEST_TTL_SECONDS = 15 * 60


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


@dataclass(frozen=True, slots=True)
class _PendingRequest:
    request: RetrievalRequest
    principal: tuple[str, str | None, str | None]
    expires_at: float
    lock: LockType = field(default_factory=Lock, repr=False, compare=False)


class _RequestRegistry:
    def __init__(self, max_requests: int, ttl_seconds: int) -> None:
        if max_requests < 1:
            raise ValueError("max_pending_requests must be positive.")
        if ttl_seconds < 1:
            raise ValueError("request_ttl_seconds must be positive.")
        self._max_requests = max_requests
        self._ttl_seconds = ttl_seconds
        self._requests: OrderedDict[str, _PendingRequest] = OrderedDict()
        self._lock = Lock()

    def issue(self, request: RetrievalRequest, access_token: AccessToken) -> str:
        now = monotonic()
        with self._lock:
            self._discard_expired(now)
            while len(self._requests) >= self._max_requests:
                self._requests.popitem(last=False)
            request_id = token_urlsafe(32)
            self._requests[request_id] = _PendingRequest(
                request=request,
                principal=principal_components(access_token),
                expires_at=now + self._ttl_seconds,
            )
        return request_id

    @contextmanager
    def use(
        self,
        request_id: str,
        access_token: AccessToken,
    ) -> Iterator[RetrievalRequest]:
        principal = principal_components(access_token)
        with self._lock:
            self._discard_expired(monotonic())
            pending = self._requests.get(request_id)
            if pending is None or pending.principal != principal:
                raise MemoryRetrievalError("Retrieval Request is unavailable.")

        with pending.lock:
            with self._lock:
                self._discard_expired(monotonic())
                current = self._requests.get(request_id)
                if current is not pending or current.principal != principal:
                    raise MemoryRetrievalError("Retrieval Request is unavailable.")
            yield pending.request

    def _discard_expired(self, now: float) -> None:
        expired_ids = [
            request_id
            for request_id, pending in self._requests.items()
            if pending.expires_at <= now
        ]
        for request_id in expired_ids:
            self._requests.pop(request_id)


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


def _mcp_result(result: SearchResult) -> McpSearchResult:
    return McpSearchResult(
        page_id=result.page_id,
        title=result.title,
        scope=result.scope,
        excerpt=result.excerpt,
        matched_fields=result.matched_fields,
    )


def create_mcp_server(
    workspace_root: str | Path,
    *,
    token_verifier: TokenVerifier,
    issuer_url: str,
    resource_server_url: str,
    required_scopes: tuple[str, ...] = ("memory:read",),
    max_pending_requests: int = DEFAULT_MAX_PENDING_REQUESTS,
    request_ttl_seconds: int = DEFAULT_REQUEST_TTL_SECONDS,
) -> MCPServer:
    """Create the authenticated MCP boundary for one Canonical Memory workspace."""
    workspace = _LazyWorkspace(workspace_root)
    requests = _RequestRegistry(max_pending_requests, request_ttl_seconds)
    server = MCPServer(
        "Personal Memory",
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer_url),
            resource_server_url=AnyHttpUrl(resource_server_url),
            required_scopes=list(required_scopes),
            validate_token_resource=True,
        ),
    )

    @server.tool(structured_output=True)
    def search_memory(
        query: str,
        scopes: list[str] | None = None,
    ) -> AuthenticatedSearchResult:
        """Search permitted memory within one bounded Retrieval Request."""
        access_token = get_access_token()
        if access_token is None:
            raise ToolError("Authentication is required.")
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
        access_token = get_access_token()
        if access_token is None:
            raise ToolError("Authentication is required.")
        try:
            with requests.use(request_id, access_token) as request:
                markdown = workspace.get().read_memory(request, selection)
        except MemoryRetrievalError as error:
            raise ToolError(str(error)) from error
        return AuthenticatedReadResult(markdown=markdown)

    return server
