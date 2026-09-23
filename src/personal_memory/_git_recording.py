"""Git recording adapter for successful approved memory updates."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from subprocess import PIPE, run
from typing import Protocol


class GitRecordingError(RuntimeError):
    """Raised when an approved update cannot be safely recorded in Git."""


class UpdateRecorder(Protocol):
    """Record one already-applied update in the canonical Git repository."""

    def prepare(self, page_id: str) -> None:
        """Refuse application when Git cannot record exactly this target."""

    def record(self, page_id: str, version_token: str) -> None:
        """Commit the verified target."""


class GitUpdateRecorder:
    """Record one target-only memory update in its canonical Git worktree."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def prepare(self, page_id: str) -> None:
        """Check that Git can make a target-only commit before application."""
        target = self._target_path(page_id)
        repository_root = Path(
            self._run("rev-parse", "--show-toplevel").stdout.strip()
        ).resolve()
        if repository_root != self._workspace_root:
            raise GitRecordingError(
                "Canonical Memory must be the root of its Git working tree."
            )
        self._run("var", "GIT_AUTHOR_IDENT")
        self._run("var", "GIT_COMMITTER_IDENT")
        self._run("ls-files", "--error-unmatch", "--", target)
        if self._has_changes("diff", "--quiet", "--", target) or self._has_changes(
            "diff", "--cached", "--quiet", "--", target
        ):
            raise GitRecordingError(
                "Memory Page has uncommitted changes before application."
            )

    def record(self, page_id: str, version_token: str) -> None:
        """Commit only the newly applied target after verifying its content."""
        target = self._target_path(page_id)
        try:
            actual_version = sha256(
                (self._workspace_root / target).read_bytes()
            ).hexdigest()
        except OSError as error:
            raise GitRecordingError("Approved Memory Page cannot be recorded.") from error
        if actual_version != version_token:
            raise GitRecordingError(
                "Memory Page changed before its approved update could be recorded."
            )
        self._run(
            "commit",
            "--only",
            "-m",
            f"memory: update {page_id}",
            "--",
            target,
        )

    def _target_path(self, page_id: str) -> str:
        return (Path("memory") / Path(page_id)).as_posix()

    def _has_changes(self, *arguments: str) -> bool:
        completed = self._run(*arguments, allowed_returncodes=(0, 1))
        return completed.returncode == 1

    def _run(
        self,
        *arguments: str,
        allowed_returncodes: tuple[int, ...] = (0,),
    ):
        try:
            completed = run(
                ["git", "-C", str(self._workspace_root), *arguments],
                check=False,
                stdout=PIPE,
                stderr=PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            raise GitRecordingError("Git recording is unavailable.") from error
        if completed.returncode not in allowed_returncodes:
            raise GitRecordingError("Approved update could not be recorded in Git.")
        return completed
