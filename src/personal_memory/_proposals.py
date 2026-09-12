"""Private no-write proposal construction for Current Memory."""

from dataclasses import dataclass
from difflib import unified_diff

from personal_memory._markdown import MemoryPage
from personal_memory._retrieval import page_version


@dataclass(frozen=True, slots=True)
class ProposedUpdate:
    """An exact replacement diff tied to one Current Memory version."""

    page_id: str
    version_token: str
    diff: str


def propose_replacement(
    current_page: MemoryPage,
    replacement_page: MemoryPage,
) -> ProposedUpdate:
    """Create a deterministic unified diff without writing either page."""
    diff = "".join(
        unified_diff(
            current_page.markdown.splitlines(keepends=True),
            replacement_page.markdown.splitlines(keepends=True),
            fromfile=f"a/memory/{current_page.page_id}",
            tofile=f"b/memory/{current_page.page_id}",
        )
    )
    return ProposedUpdate(
        page_id=current_page.page_id,
        version_token=page_version(current_page),
        diff=diff,
    )
