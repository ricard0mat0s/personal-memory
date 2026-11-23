"""Offline workspace boundary for curated personal memory."""

import os
import re
from _thread import LockType
from collections.abc import Callable
from pathlib import Path
from threading import Lock

from personal_memory.workspace._errors import (
    MemoryApplicationError,
    MemoryProposalError,
    MemoryRetrievalError,
    MemoryValidationError,
)
from personal_memory.workspace._markdown import (
    MemoryPage,
    validate_memory_markdown,
    validate_memory_page,
)
from personal_memory.workspace._proposals import (
    AppliedUpdate,
    ExplicitApproval,
    ProposedUpdate,
    approval_matches,
    create_atomically,
    propose_creation,
    propose_replacement,
    remove_created_target,
    replace_atomically,
)
from personal_memory.workspace._retrieval import (
    RetrievalRequest,
    SearchResult,
    page_version,
    read_candidate_page,
    search_pages,
)

__all__ = [
    "AppliedUpdate",
    "ExplicitApproval",
    "MemoryApplicationError",
    "MemoryProposalError",
    "MemoryRetrievalError",
    "MemoryValidationError",
    "MemoryWorkspace",
    "ProposedUpdate",
    "RetrievalRequest",
    "SearchResult",
]


def _reject_scan_error(error: OSError) -> None:
    raise MemoryValidationError("Cannot scan memory directory.") from error


_APPLICATION_LOCKS_GUARD = Lock()
_APPLICATION_LOCKS: dict[Path, LockType] = {}
_NEW_PAGE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*\.md$", flags=re.ASCII)


def _application_lock_for(memory_root: Path) -> LockType:
    with _APPLICATION_LOCKS_GUARD:
        return _APPLICATION_LOCKS.setdefault(memory_root, Lock())


class MemoryWorkspace:
    """Open a repository-backed collection of permitted Memory Pages."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._memory_root = (self._workspace_root / "memory").resolve()
        self._request_token = object()
        self._pending_updates: dict[int, tuple[ProposedUpdate, str]] = {}
        self._applied_updates: list[ProposedUpdate] = []
        self._application_lock = _application_lock_for(self._memory_root)
        self._load_pages()

    def _load_pages(self) -> tuple[MemoryPage, ...]:
        memory_root = self._memory_root
        if not memory_root.is_relative_to(self._workspace_root):
            raise MemoryValidationError(
                "The memory root must stay inside the workspace."
            )

        pages: list[MemoryPage] = []
        for directory, directories, files in os.walk(
            memory_root, onerror=_reject_scan_error
        ):
            directories.sort()
            for name in directories + sorted(files):
                page_path = Path(directory) / name
                if not page_path.resolve().is_relative_to(memory_root):
                    raise MemoryValidationError(
                        f"{page_path.name} must stay inside the memory root."
                    )
            # Check links above, then visit their in-root targets only through
            # ordinary directory entries. Windows walk otherwise follows junctions.
            directories[:] = [
                name for name in directories
                if not (Path(directory) / name).is_symlink()
                and not (Path(directory) / name).is_junction()
            ]
            for name in sorted(files):
                page_path = Path(directory) / name
                if page_path.suffix.lower() == ".md":
                    pages.append(validate_memory_page(page_path, memory_root))
        return tuple(pages)

    def search_memory(self, request: RetrievalRequest) -> tuple[SearchResult, ...]:
        """Return deterministic candidates for one bounded Retrieval Request."""
        return search_pages(self._load_pages, request, self._request_token)

    def read_memory(self, request: RetrievalRequest, selection: str) -> str:
        """Return complete Current Memory for a candidate in this request."""
        return read_candidate_page(
            self._load_pages, request, selection, self._request_token
        )

    def _target_exists_in_memory_root(self, page_id: str) -> bool:
        target = self._memory_root / page_id
        if target.exists() or target.is_symlink() or target.is_junction():
            return True
        try:
            entries = list(self._memory_root.iterdir())
        except OSError as error:
            _reject_scan_error(error)
            return False
        folded = page_id.lower()
        return any(entry.name.lower() == folded for entry in entries)

    def propose_create(self, page_id: str, markdown: str) -> ProposedUpdate:
        """Return a validated, exact creation proposal without writing."""
        if not isinstance(page_id, str) or not page_id.strip():
            raise MemoryProposalError("Memory Page target must be non-empty.")
        if _NEW_PAGE_ID_PATTERN.fullmatch(page_id) is None:
            raise MemoryProposalError(
                "Memory Page target must be a top-level lowercase slug ending in .md."
            )
        if not isinstance(markdown, str):
            raise MemoryProposalError("New Memory Page Markdown must be a string.")

        self._load_pages()
        if self._target_exists_in_memory_root(page_id):
            raise MemoryProposalError("Memory Page target already exists.")

        new_page = validate_memory_markdown(page_id, markdown, self._memory_root)
        proposal = propose_creation(new_page)
        self._pending_updates[id(proposal)] = (
            proposal,
            new_page.markdown,
        )
        return proposal

    def propose_update(self, page_id: str, markdown: str) -> ProposedUpdate:
        """Return a validated, exact replacement proposal without writing."""
        if not isinstance(page_id, str) or not page_id.strip():
            raise MemoryProposalError("Memory Page target must be non-empty.")
        if not isinstance(markdown, str):
            raise MemoryProposalError("Replacement Markdown must be a string.")

        pages = {page.page_id: page for page in self._load_pages()}
        current_page = pages.get(page_id)
        if current_page is None:
            raise MemoryProposalError("Memory Page target does not exist.")

        replacement_page = validate_memory_markdown(
            current_page.page_id, markdown, self._memory_root
        )
        if replacement_page.markdown == current_page.markdown:
            raise MemoryProposalError("Replacement Markdown must change the page.")
        proposal = propose_replacement(current_page, replacement_page)
        self._pending_updates[id(proposal)] = (
            proposal,
            replacement_page.markdown,
        )
        return proposal

    def apply_update(
        self,
        proposal: ProposedUpdate,
        approval: ExplicitApproval,
        *,
        after_application: Callable[[AppliedUpdate], None] | None = None,
    ) -> AppliedUpdate:
        """Apply one exact update, optionally recording it before finalizing."""
        if not isinstance(proposal, ProposedUpdate):
            raise MemoryApplicationError("Update must be a Proposed Update.")
        if not isinstance(approval, ExplicitApproval):
            raise MemoryApplicationError("Update requires Explicit Approval.")
        with self._application_lock:
            return self._apply_update(proposal, approval, after_application)

    def _apply_update(
        self,
        proposal: ProposedUpdate,
        approval: ExplicitApproval,
        after_application: Callable[[AppliedUpdate], None] | None,
    ) -> AppliedUpdate:
        if not approval_matches(approval, proposal):
            raise MemoryApplicationError(
                "Explicit Approval does not match this exact Proposed Update."
            )
        if any(applied is proposal for applied in self._applied_updates):
            raise MemoryApplicationError("Explicit Approval was already applied.")

        pending_update = self._pending_updates.get(id(proposal))
        if pending_update is None or pending_update[0] is not proposal:
            raise MemoryApplicationError(
                "Proposed Update was not issued by the same workspace."
            )

        if proposal.version_token is None:
            return self._apply_creation(
                proposal,
                pending_update[1],
                after_application,
            )

        pages = {page.page_id: page for page in self._load_pages()}
        current_page = pages.get(proposal.page_id)
        if current_page is None:
            raise MemoryApplicationError("Memory Page target does not exist.")
        current_version = page_version(current_page)
        if current_version != proposal.version_token:
            raise MemoryApplicationError(
                "Current Memory changed after this update was proposed."
            )

        replacement_markdown = pending_update[1]
        replacement_page = validate_memory_markdown(
            current_page.page_id,
            replacement_markdown,
            self._memory_root,
        )
        self._require_matching_proposal(
            proposal,
            propose_replacement(current_page, replacement_page),
        )

        target = self._memory_root / current_page.page_id
        replace_atomically(
            target,
            replacement_page.markdown,
            current_page.markdown,
            self._memory_root,
        )
        applied = AppliedUpdate(
            page_id=current_page.page_id,
            previous_version_token=current_version,
            version_token=page_version(replacement_page),
        )
        return self._finalize_application(
            proposal,
            applied,
            after_application,
            rollback=lambda: replace_atomically(
                target,
                current_page.markdown,
                replacement_page.markdown,
                self._memory_root,
            ),
        )

    def _apply_creation(
        self,
        proposal: ProposedUpdate,
        new_markdown: str,
        after_application: Callable[[AppliedUpdate], None] | None,
    ) -> AppliedUpdate:
        self._load_pages()
        if self._target_exists_in_memory_root(proposal.page_id):
            raise MemoryApplicationError(
                "Current Memory changed after this update was proposed."
            )

        new_page = validate_memory_markdown(
            proposal.page_id,
            new_markdown,
            self._memory_root,
        )
        self._require_matching_proposal(proposal, propose_creation(new_page))

        target = self._memory_root / new_page.page_id
        create_atomically(target, new_page.markdown, self._memory_root)
        applied = AppliedUpdate(
            page_id=new_page.page_id,
            previous_version_token=None,
            version_token=page_version(new_page),
        )
        return self._finalize_application(
            proposal,
            applied,
            after_application,
            rollback=lambda: remove_created_target(
                target,
                new_page.markdown,
                self._memory_root,
            ),
        )

    @staticmethod
    def _require_matching_proposal(
        proposal: ProposedUpdate,
        expected_proposal: ProposedUpdate,
    ) -> None:
        if (
            expected_proposal.page_id,
            expected_proposal.version_token,
            expected_proposal.diff,
        ) != (
            proposal.page_id,
            proposal.version_token,
            proposal.diff,
        ):
            raise MemoryApplicationError(
                "Proposed Update does not match its replacement."
            )

    def _finalize_application(
        self,
        proposal: ProposedUpdate,
        applied: AppliedUpdate,
        after_application: Callable[[AppliedUpdate], None] | None,
        *,
        rollback: Callable[[], None],
    ) -> AppliedUpdate:
        if after_application is not None:
            try:
                after_application(applied)
            except Exception as error:
                try:
                    rollback()
                except MemoryApplicationError as rollback_error:
                    raise MemoryApplicationError(
                        "Approved update could not be recorded or rolled back."
                    ) from rollback_error
                raise MemoryApplicationError(
                    "Approved update could not be recorded; Current Memory was restored."
                ) from error
        self._pending_updates.pop(id(proposal))
        self._applied_updates.append(proposal)
        return applied
