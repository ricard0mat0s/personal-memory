"""Private deterministic retrieval rules and public result values."""

from dataclasses import dataclass, field
from hashlib import sha256
import re
import unicodedata

from personal_memory._markdown import MemoryPage


_FIELD_WEIGHTS = {
    "title": 8,
    "scope": 4,
    "related_pages": 2,
    "body": 1,
}
_EXCERPT_WORDS = 40
RETRIEVAL_PAGE_LIMIT = 3
RETRIEVAL_WORD_LIMIT = 1_500
_WORD_PATTERN = re.compile(r"\b[\w'-]+\b", flags=re.UNICODE)


@dataclass(slots=True)
class _RetrievalState:
    workspace_token: object | None = None
    candidate_page_ids: set[str] = field(default_factory=set)
    excerpt_word_counts: dict[str, int] = field(default_factory=dict)
    excerpt_versions: dict[str, str] = field(default_factory=dict)
    read_versions: dict[str, str] = field(default_factory=dict)
    words_used: int = 0
    overflow_consumed: bool = False
    pending_complete_page_id: str | None = None

    def bind_to(self, workspace_token: object) -> bool:
        if self.workspace_token is None:
            self.workspace_token = workspace_token
        return self.workspace_token is workspace_token

    def is_bound_to(self, workspace_token: object) -> bool:
        return self.workspace_token is workspace_token

    def candidate_ids(self) -> frozenset[str]:
        return frozenset(self.candidate_page_ids)

    def admit_excerpt(self, page_id: str, word_count: int, version: str) -> bool:
        if self.excerpt_versions.get(page_id) == version:
            return True
        if (
            self.overflow_consumed
            or self.words_used >= RETRIEVAL_WORD_LIMIT
            or self.words_used + word_count > RETRIEVAL_WORD_LIMIT
            or (
                page_id not in self.candidate_page_ids
                and len(self.candidate_page_ids) >= RETRIEVAL_PAGE_LIMIT
            )
        ):
            return False

        self.candidate_page_ids.add(page_id)
        self.excerpt_word_counts[page_id] = word_count
        self.excerpt_versions[page_id] = version
        self.words_used += word_count
        if self.words_used >= RETRIEVAL_WORD_LIMIT:
            self.pending_complete_page_id = page_id
        return True

    def charge_complete_read(
        self,
        page_id: str,
        total_word_count: int,
        version: str,
    ) -> bool:
        if self.read_versions.get(page_id) == version:
            return True
        completes_pending_page = self.pending_complete_page_id == page_id
        if (
            self.overflow_consumed
            or self.words_used >= RETRIEVAL_WORD_LIMIT
        ) and not completes_pending_page:
            return False

        excerpt_words = (
            self.excerpt_word_counts.get(page_id, 0)
            if self.excerpt_versions.get(page_id) == version
            else 0
        )
        self.words_used += max(0, total_word_count - excerpt_words)
        self.read_versions[page_id] = version
        if completes_pending_page:
            self.pending_complete_page_id = None
        if self.words_used >= RETRIEVAL_WORD_LIMIT:
            self.overflow_consumed = True
        return True


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """Retrieval work and shared budget for one user prompt."""

    query: str
    scopes: tuple[str, ...] | None = None
    _state: _RetrievalState = field(
        default_factory=_RetrievalState, init=False, repr=False, compare=False
    )


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Inspectable candidate returned by deterministic search."""

    page_id: str
    title: str
    scope: str
    excerpt: str
    matched_fields: tuple[str, ...]


def normalized_terms(text: str) -> frozenset[str]:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_diacritics = "".join(
        character for character in decomposed
        if not unicodedata.combining(character)
    )
    return frozenset(
        re.findall(r"[^\W_]+", without_diacritics, flags=re.UNICODE)
    )


def rank_page(
    page: MemoryPage,
    query_terms: frozenset[str],
) -> tuple[int, tuple[str, ...]]:
    fields = {
        "title": page.title,
        "scope": page.scope,
        "related_pages": " ".join(page.related_pages),
        "body": page.body,
    }
    matches = {
        field_name: query_terms & normalized_terms(value)
        for field_name, value in fields.items()
    }
    matched_fields = tuple(
        field_name for field_name in _FIELD_WEIGHTS if matches[field_name]
    )
    score = sum(
        len(matches[field_name]) * _FIELD_WEIGHTS[field_name]
        for field_name in matched_fields
    )
    return score, matched_fields


def _normalized_term_spans(text: str) -> tuple[tuple[int, int], ...]:
    term_start: int | None = None
    spans: list[tuple[int, int]] = []
    for index, character in enumerate(text):
        if character.isalnum():
            if term_start is None:
                term_start = index
        elif term_start is not None and unicodedata.combining(character):
            continue
        elif term_start is not None:
            spans.append((term_start, index))
            term_start = None

    if term_start is not None:
        spans.append((term_start, len(text)))
    return tuple(spans)


def _first_matching_position(
    text: str,
    query_terms: frozenset[str],
    term_spans: tuple[tuple[int, int], ...],
) -> int:
    for term_start, term_end in term_spans:
        if normalized_terms(text[term_start:term_end]) & query_terms:
            return term_start
    return 0


def _excerpt_start_position(
    position: int,
    term_spans: tuple[tuple[int, int], ...],
) -> int:
    return next(
        (
            term_end
            for term_start, term_end in term_spans
            if term_start < position < term_end
        ),
        position,
    )


def _excerpt_end_position(
    position: int,
    term_spans: tuple[tuple[int, int], ...],
) -> int:
    return next(
        (
            term_start
            for term_start, term_end in term_spans
            if term_start < position < term_end
        ),
        position,
    )


def excerpt_for(page: MemoryPage, query_terms: frozenset[str]) -> str:
    words = tuple(_WORD_PATTERN.finditer(page.body))
    if not words:
        return ""
    term_spans = _normalized_term_spans(page.body)
    match_position = _first_matching_position(
        page.body, query_terms, term_spans
    )
    match_index = next(
        (
            index
            for index, word in enumerate(words)
            if word.end() > match_position
        ),
        0,
    )
    start = max(0, match_index - 10)
    end = min(len(words), start + _EXCERPT_WORDS)
    start_position = _excerpt_start_position(words[start].start(), term_spans)
    end_position = _excerpt_end_position(words[end - 1].end(), term_spans)
    return page.body[start_position:end_position].strip()


def count_words(text: str) -> int:
    return len(_WORD_PATTERN.findall(text))


def page_version(page: MemoryPage) -> str:
    return sha256(page.markdown.encode("utf-8")).hexdigest()
