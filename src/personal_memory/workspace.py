"""Offline workspace boundary for curated personal memory."""

import os
from pathlib import Path

from personal_memory._errors import MemoryRetrievalError, MemoryValidationError
from personal_memory._markdown import (
    PERMITTED_MEMORY_SCOPES,
    MemoryPage,
    validate_memory_page,
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


class MemoryWorkspace:
    """Open a repository-backed collection of permitted Memory Pages."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._memory_root = (self._workspace_root / "memory").resolve()
        self._request_token = object()
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

        request_state = request._state
        if not request_state.bind_to(self._request_token):
            raise MemoryRetrievalError(
                "Retrieval Request belongs to another workspace."
            )

        query_terms = normalized_terms(request.query)
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
