"""Private Markdown validation for Memory Pages."""

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from personal_memory._errors import MemoryValidationError


PERMITTED_MEMORY_SCOPES = frozenset(
    {
        "personal_history",
        "career_and_job_opportunities",
        "organization_work_context",
        "individual_project",
    }
)


@dataclass(frozen=True, slots=True)
class MemoryPage:
    """Validated Current Memory used only inside the offline core."""

    page_id: str
    title: str
    scope: str
    related_pages: tuple[str, ...]
    body: str
    markdown: str


def validate_memory_page(page_path: Path, memory_root: Path) -> MemoryPage:
    """Reject Markdown that violates the permitted Memory Page contract."""
    page_text = page_path.read_text(encoding="utf-8")
    opening_delimiter = "---\n"
    closing_delimiter = "\n---\n"

    has_opening_delimiter = page_text.startswith(opening_delimiter)
    frontmatter_body = page_text[len(opening_delimiter) :]
    has_closing_delimiter = closing_delimiter in frontmatter_body

    if not has_opening_delimiter or not has_closing_delimiter:
        raise MemoryValidationError(
            f"{page_path.name} must contain YAML frontmatter."
        )

    frontmatter_text, _, body = frontmatter_body.partition(closing_delimiter)
    try:
        metadata = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as error:
        raise MemoryValidationError(
            f"{page_path.name} contains invalid YAML frontmatter."
        ) from error

    if not isinstance(metadata, dict):
        raise MemoryValidationError(
            f"{page_path.name} frontmatter must be a YAML mapping."
        )

    title = metadata.get("title")
    if not isinstance(title, str) or not title.strip():
        raise MemoryValidationError(
            f"{page_path.name} frontmatter requires a non-empty title."
        )

    memory_scope = metadata.get("scope")
    if not isinstance(memory_scope, str) or memory_scope not in PERMITTED_MEMORY_SCOPES:
        raise MemoryValidationError(
            f"{page_path.name} frontmatter contains an unsupported scope."
        )

    related_pages = metadata.get("related_pages")
    has_valid_related_pages = isinstance(related_pages, list) and all(
        isinstance(related_page, str) for related_page in related_pages
    )
    if not has_valid_related_pages:
        raise MemoryValidationError(
            f"{page_path.name} frontmatter requires a related_pages list."
        )
    validated_related_pages = cast(list[str], related_pages)

    resolved_memory_root = memory_root.resolve()
    for related_page in validated_related_pages:
        resolved_related_page = (resolved_memory_root / related_page).resolve()
        if not resolved_related_page.is_relative_to(resolved_memory_root):
            raise MemoryValidationError(
                f"{page_path.name} related_pages must stay inside the memory root."
            )

    return MemoryPage(
        page_id=page_path.relative_to(memory_root).as_posix(),
        title=title.strip(),
        scope=memory_scope,
        related_pages=tuple(validated_related_pages),
        body=body,
        markdown=page_text,
    )
