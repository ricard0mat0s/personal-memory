"""Offline workspace boundary for curated personal memory."""

import os
from pathlib import Path

from personal_memory._errors import MemoryValidationError
from personal_memory._markdown import validate_memory_page


def _reject_scan_error(error: OSError) -> None:
    raise MemoryValidationError("Cannot scan memory directory.") from error


class MemoryWorkspace:
    """Open a repository-backed collection of permitted Memory Pages."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        memory_root = (self._workspace_root / "memory").resolve()
        if not memory_root.is_relative_to(self._workspace_root):
            raise MemoryValidationError("The memory root must stay inside the workspace.")

        for directory, directories, files in os.walk(memory_root, onerror=_reject_scan_error):
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
                    validate_memory_page(page_path, memory_root)
