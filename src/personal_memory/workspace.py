"""Offline workspace boundary for curated personal memory."""

import os
from _thread import LockType
from pathlib import Path
from threading import Lock

from personal_memory._errors import (
    MemoryApplicationError,
    MemoryProposalError,
    MemoryRetrievalError,
    MemoryValidationError,
)
from personal_memory._markdown import (
    PERMITTED_MEMORY_SCOPES,
    MemoryPage,
    validate_memory_markdown,
    validate_memory_page,
)
from personal_memory._proposals import (
    AppliedUpdate,
    ExplicitApproval,
    ProposedUpdate,
    approval_matches,
    propose_replacement,
    replace_atomically,
)
from personal_memory._retrieval import (
    RETRIEVAL_PAGE_LIMIT,
    RetrievalRequest,
    SearchResult,
    count_words,
    excerpt_for,
    normalized_terms,
    page_version,
    rank_page,
)


def _reject_scan_error(error: OSError) -> None:
    raise MemoryValidationError("Cannot scan memory directory.") from error


_APPLICATION_LOCKS_GUARD = Lock()
_APPLICATION_LOCKS: dict[Path, LockType] = {}


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
        if not isinstance(request, RetrievalRequest):
            raise MemoryRetrievalError("request must be a RetrievalRequest.")
        if not isinstance(request.query, str) or not request.query.strip():
            raise MemoryRetrievalError("Retrieval query must be a non-empty string.")
        if request.scopes is not None:
            if (
                not isinstance(request.scopes, tuple)
                or not request.scopes
                or any(
                    not isinstance(scope, str)
                    or scope not in PERMITTED_MEMORY_SCOPES
                    for scope in request.scopes
                )
            ):
                raise MemoryRetrievalError(
                    "Retrieval scopes must contain permitted Memory Scopes."
                )

        query_terms = normalized_terms(request.query)
        if not query_terms:
            raise MemoryRetrievalError(
                "Retrieval query must contain at least one text term."
            )

        request_state = request._state
        if not request_state.bind_to(self._request_token):
            raise MemoryRetrievalError(
                "Retrieval Request belongs to another workspace."
            )

        ranked: list[tuple[int, MemoryPage, tuple[str, ...]]] = []
        for page in self._load_pages():
            if request.scopes is not None and page.scope not in request.scopes:
                continue
            score, matched_fields = rank_page(page, query_terms)
            if score:
                ranked.append((score, page, matched_fields))
        ranked.sort(
            key=lambda item: (
                -item[0],
                item[1].page_id.casefold(),
                item[1].page_id,
            )
        )

        results = []
        for _, page, matched_fields in ranked:
            excerpt = excerpt_for(page, query_terms)
            if not request_state.admit_excerpt(
                page.page_id,
                count_words(excerpt),
                page_version(page),
            ):
                continue
            results.append(
                SearchResult(
                    page_id=page.page_id,
                    title=page.title,
                    scope=page.scope,
                    excerpt=excerpt,
                    matched_fields=matched_fields,
                )
            )
            if len(results) >= RETRIEVAL_PAGE_LIMIT:
                break
        return tuple(results)

    def read_memory(self, request: RetrievalRequest, selection: str) -> str:
        """Return complete Current Memory for a candidate in this request."""
        if not isinstance(request, RetrievalRequest):
            raise MemoryRetrievalError("request must be a RetrievalRequest.")
        request_state = request._state
        if not request_state.is_bound_to(self._request_token):
            raise MemoryRetrievalError(
                "Retrieval Request does not belong to this workspace."
            )
        if not isinstance(selection, str) or not selection.strip():
            raise MemoryRetrievalError("Memory Page selection must be non-empty.")
        pages = {page.page_id: page for page in self._load_pages()}
        candidate_pages = [
            pages[candidate_id]
            for candidate_id in request_state.candidate_ids()
            if candidate_id in pages
        ]
        page = (
            pages.get(selection)
            if selection in request_state.candidate_ids()
            else None
        )
        if page is None:
            title_matches = [
                candidate
                for candidate in candidate_pages
                if candidate.title.casefold() == selection.casefold()
            ]
            if len(title_matches) > 1:
                raise MemoryRetrievalError("Memory Page selection is ambiguous.")
            if len(title_matches) == 1:
                page = title_matches[0]
        if page is None:
            raise MemoryRetrievalError(
                "Memory Page must be selected from this request's Search Results."
            )
        if request.scopes is not None and page.scope not in request.scopes:
            raise MemoryRetrievalError(
                "Selected Memory Page is outside the request's scope selection."
            )

        if not request_state.charge_complete_read(
            page.page_id,
            count_words(page.markdown),
            page_version(page),
        ):
            raise MemoryRetrievalError("Retrieval Request word cap is exhausted.")
        return page.markdown

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
    ) -> AppliedUpdate:
        """Apply one exact, explicitly approved, current proposal atomically."""
        if not isinstance(proposal, ProposedUpdate):
            raise MemoryApplicationError("Update must be a Proposed Update.")
        if not isinstance(approval, ExplicitApproval):
            raise MemoryApplicationError("Update requires Explicit Approval.")
        with self._application_lock:
            return self._apply_update(proposal, approval)

    def _apply_update(
        self,
        proposal: ProposedUpdate,
        approval: ExplicitApproval,
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
        expected_proposal = propose_replacement(current_page, replacement_page)
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

        target = self._memory_root / current_page.page_id
        replace_atomically(
            target,
            replacement_page.markdown,
            current_page.markdown,
            self._memory_root,
        )
        self._pending_updates.pop(id(proposal))
        self._applied_updates.append(proposal)
        return AppliedUpdate(
            page_id=current_page.page_id,
            previous_version_token=current_version,
            version_token=page_version(replacement_page),
        )
