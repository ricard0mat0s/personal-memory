"""Git recording adapter for successful approved memory updates."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from subprocess import PIPE, CompletedProcess, run
from typing import Protocol

__all__ = [
    "GitRecordingError",
    "GitUpdateRecorder",
    "UpdateRecorder",
]


class GitRecordingError(RuntimeError):
    """Raised when an approved update cannot be safely recorded in Git."""


class UpdateRecorder(Protocol):
    """Record one already-applied update in the canonical Git repository."""

    def prepare(self, page_id: str, *, create: bool = False) -> None:
        """Refuse application when Git cannot record exactly this target."""

    def record(
        self,
        page_id: str,
        version_token: str,
        *,
        create: bool = False,
    ) -> None:
        """Commit the verified target."""


class GitUpdateRecorder:
    """Record one target-only memory update in its canonical Git worktree."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def prepare(self, page_id: str, *, create: bool = False) -> None:
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
        if create:
            self._prepare_create(target)
            return
        self._run("ls-files", "--error-unmatch", "--", target)
        if self._has_changes("diff", "--quiet", "--", target) or self._has_changes(
            "diff", "--cached", "--quiet", "--", target
        ):
            raise GitRecordingError(
                "Memory Page has uncommitted changes before application."
            )

    def _prepare_create(self, target: str) -> None:
        target_path = self._workspace_root / target
        if (
            target_path.exists()
            or target_path.is_symlink()
            or target_path.is_junction()
        ):
            raise GitRecordingError(
                "Memory Page target already exists before creation."
            )
        if self._run("ls-files", "--", target).stdout.strip() or self._has_changes(
            "diff", "--cached", "--quiet", "--", target
        ):
            raise GitRecordingError(
                "Memory Page target is already tracked or staged in Git."
            )
        ignored = self._run(
            "check-ignore",
            "--quiet",
            "--",
            target,
            allowed_returncodes=(0, 1),
        )
        if ignored.returncode == 0:
            raise GitRecordingError("Memory Page target is ignored by Git.")

    def record(
        self,
        page_id: str,
        version_token: str,
        *,
        create: bool = False,
    ) -> None:
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
        if create:
            self._run("add", "--", target)
            try:
                self._run(
                    "commit",
                    "--only",
                    "-m",
                    f"memory: create {page_id}",
                    "--",
                    target,
                )
            except GitRecordingError:
                self._run(
                    "rm",
                    "--cached",
                    "--quiet",
                    "--",
                    target,
                    allowed_returncodes=(0, 1, 128),
                )
                raise
            return
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
    ) -> CompletedProcess[str]:
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
