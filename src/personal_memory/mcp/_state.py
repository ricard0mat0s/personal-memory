"""Bounded TTL, principal-isolated ephemeral state for MCP sessions."""

from _thread import LockType
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from typing import Generic, TypeVar

from mcp.server.auth.provider import AccessToken, principal_components

from personal_memory.workspace import MemoryWorkspace, ProposedUpdate

DEFAULT_MAX_PENDING_REQUESTS = 128
DEFAULT_REQUEST_TTL_SECONDS = 15 * 60
DEFAULT_MAX_PENDING_PROPOSALS = 128
DEFAULT_PROPOSAL_TTL_SECONDS = 15 * 60

_State = TypeVar("_State")


@dataclass(frozen=True, slots=True)
class _PendingState(Generic[_State]):
    value: _State
    principal: tuple[str, str | None, str | None]
    expires_at: float
    lock: LockType = field(default_factory=Lock, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class PendingProposal:
    """In-flight proposal paired with the offline workspace that issued it."""

    workspace: MemoryWorkspace
    proposal: ProposedUpdate


class StateRegistry(Generic[_State]):
    """Bounded in-memory registry isolating opaque handles by principal and TTL."""

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


class LazyWorkspace:
    """Lazily open a shared retrieval workspace or fresh proposal workspace."""

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
