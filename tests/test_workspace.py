from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import re
import sys

import pytest

from personal_memory import (
    AppliedUpdate,
    ExplicitApproval,
    MemoryApplicationError,
    MemoryProposalError,
    MemoryRetrievalError,
    MemoryValidationError,
    MemoryWorkspace,
    ProposedUpdate,
    RetrievalRequest,
)


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
    memory_root.mkdir(parents=True, exist_ok=True)
    page_path = memory_root / file_name
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(content, encoding="utf-8")


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

    with pytest.raises(MemoryValidationError, match="requires a non-empty title"):
        MemoryWorkspace(tmp_path)


def link_directory(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_workspace_refuses_a_memory_directory_that_cannot_be_scanned(tmp_path: Path) -> None:
    (tmp_path / "memory").write_text("Not a directory", encoding="utf-8")
    with pytest.raises(MemoryValidationError, match="Cannot scan memory directory"):
        MemoryWorkspace(tmp_path)


def test_workspace_opens_with_an_internal_directory_cycle(tmp_path: Path) -> None:
    write_memory_page(tmp_path, "page.md", PERMITTED_MEMORY_PAGE.format(
        memory_scope="individual_project"
    ))
    memory = tmp_path / "memory"
    link = memory / "loop"
    link_directory(link, memory)
    try:
        MemoryWorkspace(tmp_path)
    finally:
        if sys.platform == "win32":
            link.rmdir()
        else:
            link.unlink()


@pytest.mark.parametrize("scope", ["[]", "{}", "null", "123"])
def test_workspace_refuses_non_string_scopes(tmp_path: Path, scope: str) -> None:
    write_memory_page(tmp_path, "page.md", PERMITTED_MEMORY_PAGE.format(memory_scope=scope))
    with pytest.raises(MemoryValidationError, match="unsupported scope"):
        MemoryWorkspace(tmp_path)


def test_workspace_refuses_a_page_link_outside_memory(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    memory.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"\xff")
    try:
        (memory / "page.md").symlink_to(outside)
    except OSError as error:
        if sys.platform == "win32" and error.winerror == 1314:
            pytest.skip("Windows requires symlink privileges for this test.")
        raise
    with pytest.raises(MemoryValidationError, match="inside the memory root"):
        MemoryWorkspace(tmp_path)


def test_workspace_opens_nested_permitted_pages(tmp_path: Path) -> None:
    nested = tmp_path / "memory" / "projects"
    nested.mkdir(parents=True)
    (nested / "page.md").write_text(
        PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project"), encoding="utf-8"
    )
    MemoryWorkspace(tmp_path)


def test_workspace_refuses_pages_through_an_escaping_directory(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    memory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "page.md").write_bytes(b"\xff")
    link = memory / "linked"
    link_directory(link, outside)
    try:
        with pytest.raises(MemoryValidationError, match="inside the memory root"):
            MemoryWorkspace(tmp_path)
    finally:
        if sys.platform == "win32":
            link.rmdir()
        else:
            link.unlink()


def test_workspace_refuses_a_memory_root_outside_the_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    # Invalid UTF-8 proves rejection happens before page contents are read.
    (outside / "page.md").write_bytes(b"\xff")
    link = workspace / "memory"
    link_directory(link, outside)
    try:
        with pytest.raises(MemoryValidationError, match="memory root.*workspace"):
            MemoryWorkspace(workspace)
    finally:
        if sys.platform == "win32":
            link.rmdir()
        else:
            link.unlink()


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


def test_search_memory_returns_a_title_match_with_public_page_identity(
    tmp_path: Path,
) -> None:
    write_memory_page(
        tmp_path,
        "projects/harpia.md",
        """\
---
title: HarpIA evaluation
scope: individual_project
related_pages: []
---

Prefer complete truck passages for independent evaluation.
""",
    )
    workspace = MemoryWorkspace(tmp_path)

    results = workspace.search_memory(RetrievalRequest("harpia"))

    assert len(results) == 1
    assert results[0].page_id == "projects/harpia.md"
    assert results[0].title == "HarpIA evaluation"
    assert results[0].scope == "individual_project"
    assert "complete truck passages" in results[0].excerpt
    assert not hasattr(results[0], "score")


def test_search_memory_refuses_an_empty_query_through_the_public_contract(
    tmp_path: Path,
) -> None:
    (tmp_path / "memory").mkdir()
    workspace = MemoryWorkspace(tmp_path)

    with pytest.raises(MemoryRetrievalError, match="non-empty"):
        workspace.search_memory(RetrievalRequest("  "))


def test_search_memory_refuses_a_punctuation_only_query_through_the_public_contract(
    tmp_path: Path,
) -> None:
    (tmp_path / "memory").mkdir()
    workspace = MemoryWorkspace(tmp_path)

    with pytest.raises(MemoryRetrievalError, match="text term"):
        workspace.search_memory(RetrievalRequest("!!!"))


def test_read_memory_returns_the_complete_current_page_selected_from_search(
    tmp_path: Path,
) -> None:
    original = """\
---
title: Project direction
scope: individual_project
related_pages: []
---

Build the first version.
"""
    current = original.replace("first version", "small verified version")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)
    request = RetrievalRequest("project direction")
    result = workspace.search_memory(request)[0]
    write_memory_page(tmp_path, "direction.md", current)

    returned_markdown = workspace.read_memory(request, result.page_id)

    assert returned_markdown == current
    assert "first version" not in returned_markdown


def test_read_memory_refuses_an_ambiguous_candidate_title(tmp_path: Path) -> None:
    for page_id, sentence in (
        ("career/shared.md", "Career notes."),
        ("projects/shared.md", "Project notes."),
    ):
        write_memory_page(
            tmp_path,
            page_id,
            f"""\
---
title: Shared notes
scope: individual_project
related_pages: []
---

{sentence}
""",
        )
    workspace = MemoryWorkspace(tmp_path)
    request = RetrievalRequest("shared")
    workspace.search_memory(request)

    with pytest.raises(MemoryRetrievalError, match="ambiguous"):
        workspace.read_memory(request, "Shared notes")


def test_propose_update_returns_an_exact_diff_and_version_without_writing(
    tmp_path: Path,
) -> None:
    original = """\
---
title: Project direction
scope: individual_project
related_pages: []
---

Build the first version.
"""
    replacement = original.replace(
        "Build the first version.", "Build a small, verified version."
    )
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)

    proposal = workspace.propose_update("direction.md", replacement)

    assert proposal == ProposedUpdate(
        page_id="direction.md",
        version_token=sha256(original.encode("utf-8")).hexdigest(),
        diff=(
            "--- a/memory/direction.md\n"
            "+++ b/memory/direction.md\n"
            "@@ -4,4 +4,4 @@\n"
            " related_pages: []\n"
            " ---\n"
            " \n"
            "-Build the first version.\n"
            "+Build a small, verified version.\n"
        ),
    )
    assert (tmp_path / "memory" / "direction.md").read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("page_id", "markdown", "message"),
    [
        ("", PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project"), "target"),
        ("missing.md", PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project"), "exist"),
        ("direction.md", None, "Markdown"),  # type: ignore[list-item]
    ],
)
def test_propose_update_rejects_invalid_targets_and_replacements(
    tmp_path: Path,
    page_id: str,
    markdown: str,
    message: str,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)

    with pytest.raises(MemoryProposalError, match=message):
        workspace.propose_update(page_id, markdown)

    assert (tmp_path / "memory" / "direction.md").read_text(encoding="utf-8") == original


def test_propose_update_rejects_an_invalid_or_unchanged_memory_page(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)

    with pytest.raises(MemoryProposalError, match="change"):
        workspace.propose_update("direction.md", original)
    with pytest.raises(MemoryValidationError, match="non-empty title"):
        workspace.propose_update(
            "direction.md",
            original.replace("title: Project preferences\n", ""),
        )

    assert (tmp_path / "memory" / "direction.md").read_text(encoding="utf-8") == original


def test_propose_update_uses_the_current_page_version_at_proposal_time(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    current = original.replace("small, verifiable", "current, deliberate")
    replacement = current.replace("current, deliberate", "small, verified")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)
    write_memory_page(tmp_path, "direction.md", current)

    proposal = workspace.propose_update("direction.md", replacement)

    assert proposal.version_token == sha256(current.encode("utf-8")).hexdigest()
    assert "-Prefer current, deliberate milestones." in proposal.diff
    assert "+Prefer small, verified milestones." in proposal.diff
    assert (tmp_path / "memory" / "direction.md").read_text(encoding="utf-8") == current


def test_apply_update_atomically_replaces_only_its_approved_target(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    replacement = original.replace("small, verifiable", "small, verified")
    other_page = original.replace("Project preferences", "Other project")
    write_memory_page(tmp_path, "direction.md", original)
    write_memory_page(tmp_path, "other.md", other_page)
    workspace = MemoryWorkspace(tmp_path)
    proposal = workspace.propose_update("direction.md", replacement)
    approval = ExplicitApproval.for_proposal(proposal)

    result = workspace.apply_update(proposal, approval)

    assert result == AppliedUpdate(
        page_id="direction.md",
        previous_version_token=sha256(original.encode("utf-8")).hexdigest(),
        version_token=sha256(replacement.encode("utf-8")).hexdigest(),
    )
    assert (tmp_path / "memory" / "direction.md").read_text(
        encoding="utf-8"
    ) == replacement
    assert (tmp_path / "memory" / "other.md").read_text(
        encoding="utf-8"
    ) == other_page


def test_apply_update_refuses_a_used_approval_after_the_page_is_restored(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    replacement = original.replace("small, verifiable", "small, verified")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)
    first_proposal = workspace.propose_update("direction.md", replacement)
    first_approval = ExplicitApproval.for_proposal(first_proposal)
    workspace.apply_update(first_proposal, first_approval)
    restore_proposal = workspace.propose_update("direction.md", original)
    workspace.apply_update(
        restore_proposal,
        ExplicitApproval.for_proposal(restore_proposal),
    )

    with pytest.raises(MemoryApplicationError, match="already applied"):
        workspace.apply_update(first_proposal, first_approval)

    assert (tmp_path / "memory" / "direction.md").read_text(
        encoding="utf-8"
    ) == original


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("page_id", "other.md"),
        ("version_token", "different-version"),
        ("diff", "different diff"),
    ],
)
def test_apply_update_refuses_approval_for_a_different_proposal_field(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    replacement = original.replace("small, verifiable", "small, verified")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)
    proposal = workspace.propose_update("direction.md", replacement)
    approval = ExplicitApproval.for_proposal(proposal)
    if field == "page_id":
        approval = replace(approval, page_id=value)
    elif field == "version_token":
        approval = replace(approval, version_token=value)
    else:
        approval = replace(approval, diff=value)

    with pytest.raises(MemoryApplicationError, match="does not match"):
        workspace.apply_update(proposal, approval)

    assert (tmp_path / "memory" / "direction.md").read_text(
        encoding="utf-8"
    ) == original


def test_apply_update_refuses_a_stale_proposal_without_losing_current_memory(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    proposed = original.replace("small, verifiable", "small, verified")
    current = original.replace("small, verifiable", "current, deliberate")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)
    proposal = workspace.propose_update("direction.md", proposed)
    approval = ExplicitApproval.for_proposal(proposal)
    write_memory_page(tmp_path, "direction.md", current)

    with pytest.raises(MemoryApplicationError, match="Current Memory changed"):
        workspace.apply_update(proposal, approval)

    assert (tmp_path / "memory" / "direction.md").read_text(
        encoding="utf-8"
    ) == current


def test_apply_update_refuses_a_boolean_instead_of_explicit_approval(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    replacement = original.replace("small, verifiable", "small, verified")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)
    proposal = workspace.propose_update("direction.md", replacement)

    with pytest.raises(MemoryApplicationError, match="Explicit Approval"):
        workspace.apply_update(proposal, True)  # type: ignore[arg-type]

    assert (tmp_path / "memory" / "direction.md").read_text(
        encoding="utf-8"
    ) == original


def test_apply_update_refuses_a_structurally_equal_foreign_proposal(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    replacement = original.replace("small, verifiable", "small, verified")
    local_root = tmp_path / "local"
    foreign_root = tmp_path / "foreign"
    write_memory_page(local_root, "direction.md", original)
    write_memory_page(foreign_root, "direction.md", original)
    local_workspace = MemoryWorkspace(local_root)
    foreign_workspace = MemoryWorkspace(foreign_root)
    local_proposal = local_workspace.propose_update("direction.md", replacement)
    foreign_proposal = foreign_workspace.propose_update("direction.md", replacement)
    assert foreign_proposal == local_proposal

    with pytest.raises(MemoryApplicationError, match="same workspace"):
        local_workspace.apply_update(
            foreign_proposal,
            ExplicitApproval.for_proposal(foreign_proposal),
        )

    assert (local_root / "memory" / "direction.md").read_text(
        encoding="utf-8"
    ) == original


def test_apply_update_refuses_approval_reconstructed_from_public_fields(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    replacement = original.replace("small, verifiable", "small, verified")
    write_memory_page(tmp_path, "direction.md", original)
    workspace = MemoryWorkspace(tmp_path)
    proposal = workspace.propose_update("direction.md", replacement)
    reconstructed_approval = ExplicitApproval(
        page_id=proposal.page_id,
        version_token=proposal.version_token,
        diff=proposal.diff,
    )

    with pytest.raises(MemoryApplicationError, match="exact Proposed Update"):
        workspace.apply_update(proposal, reconstructed_approval)

    assert (tmp_path / "memory" / "direction.md").read_text(
        encoding="utf-8"
    ) == original


def test_apply_update_refuses_an_out_of_scope_target_without_touching_it(
    tmp_path: Path,
) -> None:
    original = PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project")
    write_memory_page(tmp_path, "direction.md", original)
    outside = tmp_path / "outside.md"
    outside.write_text("Outside Permitted Memory.\n", encoding="utf-8")
    workspace = MemoryWorkspace(tmp_path)
    forged_proposal = ProposedUpdate(
        page_id="../outside.md",
        version_token=sha256(outside.read_bytes()).hexdigest(),
        diff="forged diff",
    )

    with pytest.raises(MemoryApplicationError, match="same workspace"):
        workspace.apply_update(
            forged_proposal,
            ExplicitApproval.for_proposal(forged_proposal),
        )

    assert outside.read_text(encoding="utf-8") == "Outside Permitted Memory.\n"
    assert (tmp_path / "memory" / "direction.md").read_text(
        encoding="utf-8"
    ) == original


def test_repeated_searches_share_the_three_page_request_cap(tmp_path: Path) -> None:
    for name in ("a", "b", "c", "d"):
        write_memory_page(
            tmp_path,
            f"{name}.md",
            f"""\
---
title: Topic {name}
scope: individual_project
related_pages: []
---

Relevant topic context for {name}.
""",
        )
    workspace = MemoryWorkspace(tmp_path)
    request = RetrievalRequest("topic")

    first_results = workspace.search_memory(request)
    for result in first_results:
        write_memory_page(
            tmp_path,
            result.page_id,
            f"""\
---
title: Unrelated {result.page_id}
scope: individual_project
related_pages: []
---

No matching content remains.
""",
        )

    assert [result.page_id for result in first_results] == ["a.md", "b.md", "c.md"]
    assert workspace.search_memory(request) == ()


def test_read_memory_returns_the_complete_next_page_then_exhausts_word_budget(
    tmp_path: Path,
) -> None:
    for name in ("a", "b", "c"):
        body = "topic " + " ".join(f"{name}{index}" for index in range(800))
        write_memory_page(
            tmp_path,
            f"{name}.md",
            f"""\
---
title: Topic {name}
scope: individual_project
related_pages: []
---

{body}
""",
        )
    workspace = MemoryWorkspace(tmp_path)
    request = RetrievalRequest("topic")
    results = workspace.search_memory(request)

    workspace.read_memory(request, results[0].page_id)
    complete_second_page = workspace.read_memory(request, results[1].page_id)

    assert complete_second_page.rstrip().endswith("b799")
    with pytest.raises(MemoryRetrievalError, match="word cap"):
        workspace.read_memory(request, results[2].page_id)


def test_search_excerpt_centers_late_literal_body_match_with_normalization(
    tmp_path: Path,
) -> None:
    filler = " ".join(f"filler{index}" for index in range(60))
    write_memory_page(
        tmp_path,
        "learning.md",
        f"""\
---
title: Learning notes
scope: personal_history
related_pages: []
---

{filler} programação creates durable understanding.
""",
    )
    workspace = MemoryWorkspace(tmp_path)

    result = workspace.search_memory(RetrievalRequest("PROGRAMAÇÃO!!!"))[0]

    assert result.matched_fields == ("body",)
    assert "programação creates durable understanding" in result.excerpt
    assert not result.excerpt.startswith("filler0")


def test_search_excerpt_centers_a_late_decomposed_body_match(
    tmp_path: Path,
) -> None:
    filler = " ".join(f"filler{index}" for index in range(60))
    decomposed_programacao = "programac\u0327a\u0303o"
    write_memory_page(
        tmp_path,
        "learning.md",
        f"""\
---
title: Learning notes
scope: personal_history
related_pages: []
---

{filler} {decomposed_programacao} creates durable understanding.
""",
    )
    workspace = MemoryWorkspace(tmp_path)

    result = workspace.search_memory(RetrievalRequest("PROGRAMAÇÃO"))[0]

    assert result.matched_fields == ("body",)
    assert decomposed_programacao in result.excerpt
    assert not result.excerpt.startswith("filler0")


def test_search_excerpt_is_limited_by_the_documented_word_definition(
    tmp_path: Path,
) -> None:
    body = " ".join(["alpha/beta"] * 50)
    write_memory_page(
        tmp_path,
        "excerpt-contract.md",
        f"""\
---
title: Excerpt contract
scope: individual_project
related_pages: []
---

{body}
""",
    )
    workspace = MemoryWorkspace(tmp_path)

    result = workspace.search_memory(RetrievalRequest("excerpt"))[0]

    assert len(re.findall(r"\b[\w'-]+\b", result.excerpt)) == 40


def test_search_excerpt_does_not_split_a_decomposed_term_at_the_word_limit(
    tmp_path: Path,
) -> None:
    prefix = " ".join(f"filler{index}" for index in range(39))
    decomposed_programacao = "programac\u0327a\u0303o"
    body = f"{prefix} {decomposed_programacao} trailing context"
    write_memory_page(
        tmp_path,
        "excerpt-contract.md",
        f"""\
---
title: Excerpt contract
scope: individual_project
related_pages: []
---

{body}
""",
    )
    workspace = MemoryWorkspace(tmp_path)

    result = workspace.search_memory(RetrievalRequest("excerpt"))[0]

    assert result.excerpt.rstrip().endswith("filler38")
    assert len(re.findall(r"\b[\w'-]+\b", result.excerpt)) == 39


def test_search_matches_scope_words_and_honors_explicit_scope_selection(
    tmp_path: Path,
) -> None:
    write_memory_page(
        tmp_path,
        "project.md",
        """\
---
title: Direction
scope: individual_project
related_pages: []
---

Choose one concrete experiment.
""",
    )
    write_memory_page(
        tmp_path,
        "career.md",
        """\
---
title: Career direction
scope: career_and_job_opportunities
related_pages: []
---

An individual project can provide evidence.
""",
    )
    workspace = MemoryWorkspace(tmp_path)

    results = workspace.search_memory(
        RetrievalRequest("individual project", scopes=("individual_project",))
    )

    assert [result.page_id for result in results] == ["project.md"]
    assert results[0].matched_fields == ("scope",)


def test_search_ranking_and_path_tie_break_are_deterministic(tmp_path: Path) -> None:
    pages = {
        "c-title.md": ("HarpIA overview", [], "Evaluation notes."),
        "b-related.md": ("Related index", ["projects/harpia.md"], "Index notes."),
        "a-body.md": ("Body match", [], "HarpIA evaluation notes."),
        "d-body.md": ("Another body match", [], "HarpIA training notes."),
        "irrelevant.md": ("Cooking", [], "Bread recipe."),
    }
    for page_id, (title, related_pages, body) in pages.items():
        related_yaml = "[" + ", ".join(related_pages) + "]"
        write_memory_page(
            tmp_path,
            page_id,
            f"""\
---
title: {title}
scope: individual_project
related_pages: {related_yaml}
---

{body}
""",
        )
    workspace = MemoryWorkspace(tmp_path)

    first = workspace.search_memory(RetrievalRequest("harpia harpia"))
    repeated = workspace.search_memory(RetrievalRequest("HÁRPIA"))

    assert [result.page_id for result in first] == [
        "c-title.md",
        "b-related.md",
        "a-body.md",
    ]
    assert [result.page_id for result in repeated] == [
        "c-title.md",
        "b-related.md",
        "a-body.md",
    ]
    assert workspace.search_memory(RetrievalRequest("absent")) == ()


@pytest.mark.parametrize(
    "malformed_request",
    [
        "plain query",
        RetrievalRequest("query", scopes=()),
        RetrievalRequest("query", scopes=([],)),  # type: ignore[arg-type]
        RetrievalRequest(None),  # type: ignore[arg-type]
    ],
)
def test_search_rejects_malformed_retrieval_requests(
    tmp_path: Path,
    malformed_request: object,
) -> None:
    (tmp_path / "memory").mkdir()
    workspace = MemoryWorkspace(tmp_path)

    with pytest.raises(MemoryRetrievalError):
        workspace.search_memory(malformed_request)  # type: ignore[arg-type]


def test_retrieval_request_cannot_be_reused_across_workspaces(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for root in (first_root, second_root):
        write_memory_page(root, "page.md", PERMITTED_MEMORY_PAGE.format(
            memory_scope="individual_project"
        ))
    first_workspace = MemoryWorkspace(first_root)
    second_workspace = MemoryWorkspace(second_root)
    request = RetrievalRequest("project")
    first_workspace.search_memory(request)

    with pytest.raises(MemoryRetrievalError, match="another workspace"):
        second_workspace.search_memory(request)


def test_search_does_not_admit_an_excerpt_that_crosses_the_word_budget(
    tmp_path: Path,
) -> None:
    first_body = "topic " + " ".join(f"a{index}" for index in range(1470))
    write_memory_page(
        tmp_path,
        "a.md",
        f"""\
---
title: Topic a
scope: individual_project
related_pages: []
---

{first_body}
""",
    )
    workspace = MemoryWorkspace(tmp_path)
    request = RetrievalRequest("topic")
    first_result = workspace.search_memory(request)[0]
    workspace.read_memory(request, first_result.page_id)
    second_body = "topic " + " ".join(f"b{index}" for index in range(100))
    write_memory_page(
        tmp_path,
        "b.md",
        f"""\
---
title: Topic b
scope: individual_project
related_pages: []
---

{second_body}
""",
    )

    later_results = workspace.search_memory(request)

    assert [result.page_id for result in later_results] == ["a.md"]
    with pytest.raises(MemoryRetrievalError, match="Search Results"):
        workspace.read_memory(request, "b.md")


def test_read_memory_reapplies_scope_after_a_candidate_changes(
    tmp_path: Path,
) -> None:
    write_memory_page(
        tmp_path,
        "direction.md",
        PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project"),
    )
    workspace = MemoryWorkspace(tmp_path)
    request = RetrievalRequest("project", scopes=("individual_project",))
    result = workspace.search_memory(request)[0]
    write_memory_page(
        tmp_path,
        "direction.md",
        PERMITTED_MEMORY_PAGE.format(
            memory_scope="career_and_job_opportunities"
        ),
    )

    with pytest.raises(MemoryRetrievalError, match="scope"):
        workspace.read_memory(request, result.page_id)


def test_changed_page_content_is_charged_again_to_the_request_budget(
    tmp_path: Path,
) -> None:
    write_memory_page(
        tmp_path,
        "a.md",
        PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project"),
    )
    workspace = MemoryWorkspace(tmp_path)
    request = RetrievalRequest("project")
    result = workspace.search_memory(request)[0]
    workspace.read_memory(request, result.page_id)
    changed_body = "project " + " ".join(f"changed{index}" for index in range(2000))
    write_memory_page(
        tmp_path,
        "a.md",
        f"""\
---
title: Project preferences
scope: individual_project
related_pages: []
---

{changed_body}
""",
    )

    changed_page = workspace.read_memory(request, result.page_id)
    write_memory_page(
        tmp_path,
        "b.md",
        PERMITTED_MEMORY_PAGE.format(memory_scope="individual_project"),
    )

    assert changed_page.rstrip().endswith("changed1999")
    assert workspace.search_memory(request) == ()
