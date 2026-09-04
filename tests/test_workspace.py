from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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


class MemoryWorkspaceContractTests(unittest.TestCase):
    def test_workspace_opens_synthetic_pages_for_each_permitted_scope(self) -> None:
        for memory_scope in PERMITTED_MEMORY_SCOPES:
            with self.subTest(memory_scope=memory_scope):
                with TemporaryDirectory() as temporary_directory:
                    workspace_root = Path(temporary_directory)
                    memory_root = workspace_root / "memory"
                    memory_root.mkdir()
                    permitted_memory_page = PERMITTED_MEMORY_PAGE.format(
                        memory_scope=memory_scope
                    )
                    (memory_root / "project-preferences.md").write_text(
                        permitted_memory_page,
                        encoding="utf-8",
                    )

                    workspace = MemoryWorkspace(workspace_root)

                    self.assertIsInstance(workspace, MemoryWorkspace)

    def test_workspace_refuses_raw_transcript_without_frontmatter(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            workspace_root = Path(temporary_directory)
            memory_root = workspace_root / "memory"
            memory_root.mkdir()
            (memory_root / "raw-chat.md").write_text(
                "User: Remember every message from this conversation.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                MemoryValidationError,
                "YAML frontmatter",
            ):
                MemoryWorkspace(workspace_root)

    def test_workspace_refuses_a_page_without_a_title(self) -> None:
        page_without_title = """\
---
scope: individual_project
related_pages: []
---

# Missing title metadata
"""

        with TemporaryDirectory() as temporary_directory:
            workspace_root = Path(temporary_directory)
            memory_root = workspace_root / "memory"
            memory_root.mkdir()
            (memory_root / "untitled.md").write_text(
                page_without_title,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(MemoryValidationError, "title"):
                MemoryWorkspace(workspace_root)

    def test_workspace_refuses_invalid_yaml_frontmatter(self) -> None:
        page_with_invalid_yaml = """\
---
title: [unterminated
scope: individual_project
related_pages: []
---

# Invalid metadata
"""

        with TemporaryDirectory() as temporary_directory:
            workspace_root = Path(temporary_directory)
            memory_root = workspace_root / "memory"
            memory_root.mkdir()
            (memory_root / "invalid-metadata.md").write_text(
                page_with_invalid_yaml,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(MemoryValidationError, "invalid YAML"):
                MemoryWorkspace(workspace_root)

    def test_workspace_refuses_an_unsupported_memory_scope(self) -> None:
        transcript_page = """\
---
title: Complete chat transcript
scope: raw_transcript
related_pages: []
---

User: Save this entire conversation.
"""

        with TemporaryDirectory() as temporary_directory:
            workspace_root = Path(temporary_directory)
            memory_root = workspace_root / "memory"
            memory_root.mkdir()
            (memory_root / "complete-chat.md").write_text(
                transcript_page,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(MemoryValidationError, "scope"):
                MemoryWorkspace(workspace_root)

    def test_workspace_refuses_a_page_without_related_pages(self) -> None:
        page_without_related_pages = """\
---
title: Incomplete project preferences
scope: individual_project
---

# Incomplete project preferences
"""

        with TemporaryDirectory() as temporary_directory:
            workspace_root = Path(temporary_directory)
            memory_root = workspace_root / "memory"
            memory_root.mkdir()
            (memory_root / "incomplete-project-preferences.md").write_text(
                page_without_related_pages,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(MemoryValidationError, "related_pages"):
                MemoryWorkspace(workspace_root)

    def test_workspace_refuses_a_related_page_outside_the_memory_root(self) -> None:
        page_with_escaping_relation = """\
---
title: Unsafe project preferences
scope: individual_project
related_pages:
  - ../private.md
---

# Unsafe project preferences
"""

        with TemporaryDirectory() as temporary_directory:
            workspace_root = Path(temporary_directory)
            memory_root = workspace_root / "memory"
            memory_root.mkdir()
            (memory_root / "unsafe-project-preferences.md").write_text(
                page_with_escaping_relation,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(MemoryValidationError, "related_pages"):
                MemoryWorkspace(workspace_root)


if __name__ == "__main__":
    unittest.main()
