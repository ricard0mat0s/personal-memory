from pathlib import Path

import pytest

from personal_memory import MemoryValidationError, MemoryWorkspace


PERMITTED_MEMORY_PAGE = """\
---
title: Project preferences
scope: {memory_scope}
related_pages: []
---

# Project preferences

Prefer small, verifiable milestones.
"""

PERMITTED_MEMORY_SCOPES = (
    "personal_history",
    "career_and_job_opportunities",
    "organization_work_context",
    "individual_project",
)


def write_memory_page(workspace_root: Path, file_name: str, content: str) -> None:
    memory_root = workspace_root / "memory"
    memory_root.mkdir(exist_ok=True)
    (memory_root / file_name).write_text(content, encoding="utf-8")


@pytest.mark.parametrize("memory_scope", PERMITTED_MEMORY_SCOPES)
def test_workspace_opens_synthetic_pages_for_each_permitted_scope(
    tmp_path: Path,
    memory_scope: str,
) -> None:
    permitted_memory_page = PERMITTED_MEMORY_PAGE.format(memory_scope=memory_scope)
    write_memory_page(
        tmp_path,
        "project-preferences.md",
        permitted_memory_page,
    )

    workspace = MemoryWorkspace(tmp_path)

    assert isinstance(workspace, MemoryWorkspace)


def test_workspace_refuses_raw_transcript_without_frontmatter(tmp_path: Path) -> None:
    write_memory_page(
        tmp_path,
        "raw-chat.md",
        "User: Remember every message from this conversation.\n",
    )

    with pytest.raises(MemoryValidationError, match="YAML frontmatter"):
        MemoryWorkspace(tmp_path)


def test_workspace_refuses_a_page_without_a_title(tmp_path: Path) -> None:
    page_without_title = """\
---
scope: individual_project
related_pages: []
---

# Missing title metadata
"""

    write_memory_page(tmp_path, "untitled.md", page_without_title)

    with pytest.raises(MemoryValidationError, match="title"):
        MemoryWorkspace(tmp_path)


def test_workspace_refuses_invalid_yaml_frontmatter(tmp_path: Path) -> None:
    page_with_invalid_yaml = """\
---
title: [unterminated
scope: individual_project
related_pages: []
---

# Invalid metadata
"""

    write_memory_page(tmp_path, "invalid-metadata.md", page_with_invalid_yaml)

    with pytest.raises(MemoryValidationError, match="invalid YAML"):
        MemoryWorkspace(tmp_path)


def test_workspace_refuses_an_unsupported_memory_scope(tmp_path: Path) -> None:
    transcript_page = """\
---
title: Complete chat transcript
scope: raw_transcript
related_pages: []
---

User: Save this entire conversation.
"""

    write_memory_page(tmp_path, "complete-chat.md", transcript_page)

    with pytest.raises(MemoryValidationError, match="scope"):
        MemoryWorkspace(tmp_path)


def test_workspace_refuses_a_page_without_related_pages(tmp_path: Path) -> None:
    page_without_related_pages = """\
---
title: Incomplete project preferences
scope: individual_project
---

# Incomplete project preferences
"""

    write_memory_page(
        tmp_path,
        "incomplete-project-preferences.md",
        page_without_related_pages,
    )

    with pytest.raises(MemoryValidationError, match="related_pages"):
        MemoryWorkspace(tmp_path)


def test_workspace_refuses_a_related_page_outside_the_memory_root(
    tmp_path: Path,
) -> None:
    page_with_escaping_relation = """\
---
title: Unsafe project preferences
scope: individual_project
related_pages:
  - ../private.md
---

# Unsafe project preferences
"""

    write_memory_page(
        tmp_path,
        "unsafe-project-preferences.md",
        page_with_escaping_relation,
    )

    with pytest.raises(MemoryValidationError, match="related_pages"):
        MemoryWorkspace(tmp_path)
