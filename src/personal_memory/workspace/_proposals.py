"""Private proposal and guarded application mechanics for Current Memory."""

import os
import time
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path
from tempfile import NamedTemporaryFile

from personal_memory.workspace._errors import MemoryApplicationError
from personal_memory.workspace._markdown import MemoryPage
from personal_memory.workspace._retrieval import page_version


@dataclass(frozen=True, slots=True)
class ProposedUpdate:
    """An exact replacement diff tied to one Current Memory version."""

    page_id: str
    version_token: str | None
    diff: str


@dataclass(frozen=True, slots=True)
class ExplicitApproval:
    """Approval bound to the public identity of one exact Proposed Update."""

    page_id: str
    version_token: str | None
    diff: str
    _proposal: ProposedUpdate | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @classmethod
    def for_proposal(cls, proposal: ProposedUpdate) -> "ExplicitApproval":
        """Record an external approval for one exact proposal."""
        if not isinstance(proposal, ProposedUpdate):
            raise MemoryApplicationError("Approval requires a Proposed Update.")
        return cls(
            page_id=proposal.page_id,
            version_token=proposal.version_token,
            diff=proposal.diff,
            _proposal=proposal,
        )


@dataclass(frozen=True, slots=True)
class AppliedUpdate:
    """Observable result of replacing one Current Memory page."""

    page_id: str
    previous_version_token: str | None
    version_token: str


def propose_creation(new_page: MemoryPage) -> ProposedUpdate:
    """Create a deterministic unified diff for a new page without writing."""
    diff = "".join(
        unified_diff(
            [],
            new_page.markdown.splitlines(keepends=True),
            fromfile="/dev/null",
            tofile=f"b/memory/{new_page.page_id}",
        )
    )
    return ProposedUpdate(
        page_id=new_page.page_id,
        version_token=None,
        diff=diff,
    )


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


def approval_matches(
    approval: ExplicitApproval,
    proposal: ProposedUpdate,
) -> bool:
    """Return whether approval names every public proposal field."""
    return approval._proposal is proposal and (
        (
            approval.page_id,
            approval.version_token,
            approval.diff,
        )
        == (
            proposal.page_id,
            proposal.version_token,
            proposal.diff,
        )
    )


def _require_permitted_target(target: Path, memory_root: Path) -> None:
    resolved_root = memory_root.resolve()
    resolved_target = target.resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise MemoryApplicationError(
            "Memory Page target moved outside Permitted Memory."
        )
    current_path = target
    while current_path != memory_root:
        if current_path.is_symlink() or current_path.is_junction():
            raise MemoryApplicationError(
                "Memory Page target cannot be applied through a link."
            )
        current_path = current_path.parent


def replace_atomically(
    target: Path,
    markdown: str,
    expected_markdown: str,
    memory_root: Path,
) -> None:
    """Replace a page through a temporary file on the target filesystem."""
    temporary_path: Path | None = None
    try:
        _require_permitted_target(target, memory_root)
        with NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(markdown.encode("utf-8"))
            temporary.flush()
            os.fsync(temporary.fileno())
        for attempt in range(3):
            _require_permitted_target(target, memory_root)
            if target.read_text(encoding="utf-8") != expected_markdown:
                raise MemoryApplicationError(
                    "Current Memory changed while applying this update."
                )
            try:
                os.replace(temporary_path, target)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 2:
                    raise
                time.sleep(0.01 * (attempt + 1))
    except MemoryApplicationError:
        raise
    except OSError as error:
        raise MemoryApplicationError(
            "The approved update could not be applied atomically."
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def create_atomically(
    target: Path,
    markdown: str,
    memory_root: Path,
) -> None:
    """Create a new page exclusively without overwriting any existing entry."""
    created = False
    try:
        _require_permitted_target(target, memory_root)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(target, flags, 0o666)
        created = True
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(markdown.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    except FileExistsError as error:
        raise MemoryApplicationError(
            "Current Memory changed after this update was proposed."
        ) from error
    except MemoryApplicationError:
        raise
    except OSError as error:
        if created:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        raise MemoryApplicationError(
            "The approved update could not be applied atomically."
        ) from error


def remove_created_target(
    target: Path,
    expected_markdown: str,
    memory_root: Path,
) -> None:
    """Remove a newly created page when post-application recording fails."""
    try:
        _require_permitted_target(target, memory_root)
        if target.read_text(encoding="utf-8") != expected_markdown:
            raise MemoryApplicationError(
                "Current Memory changed while rolling back this update."
            )
        target.unlink()
    except MemoryApplicationError:
        raise
    except OSError as error:
        raise MemoryApplicationError(
            "The created page could not be removed during rollback."
        ) from error
