"""Offline workspace boundary for curated personal memory."""

from pathlib import Path

from personal_memory._markdown import validate_memory_page


class MemoryWorkspace:
    """Open a repository-backed collection of permitted Memory Pages."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        memory_root = self._workspace_root / "memory"

        for page_path in sorted(memory_root.rglob("*.md")):
            validate_memory_page(page_path, memory_root)
