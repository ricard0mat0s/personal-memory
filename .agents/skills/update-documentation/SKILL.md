---
name: update-documentation
description: Update repository documentation from a deliberate pre-commit change set when explicitly invoked.
---

# Update documentation

Use this skill after the intended implementation is complete and before a commit. Its job is to keep documentation truthful about the resulting repository state, not to produce a changelog of every code edit.

Work from the current worktree. Update documentation directly when the evidence and destination are clear. Never stage, commit, push, or alter source code as part of this skill.

## Establish the change set

1. Locate the Git root and inspect `git status --short`.
2. Inspect both staged and unstaged changes, plus relevant untracked files. Do not assume that staged changes are the whole pre-commit change set.
3. Read enough changed source, tests, configuration, and existing documentation to explain the observable resulting behavior. A filename or commit message is not evidence.

Keep pre-existing user changes intact, especially edits already present in documentation files. Treat them as part of the worktree state rather than permission to rewrite their surrounding document.

## Select the documentation target

First read the repository's applicable `AGENTS.md`. If it contains a documentation map, follow it. A useful map assigns concerns such as public behavior, architecture and boundaries, setup or operations, and user-facing configuration to their authoritative files; it can also identify generated or managed documents.

When no map exists, infer cautiously from the repository's current documents and their actual scope. Prefer updating an existing authoritative document. Create a focused document only when no existing target can accurately carry an important change. Do not create a document merely to record an internal implementation detail.

If a mapped document is generated or managed, use its documented source or workflow instead of hand-editing the generated output. If that workflow is unavailable, report the situation as uncertain.

## Decide whether documentation is needed

Classify the complete change set before editing:

- **Updated**: a public contract, architecture boundary, data flow, setup or operating procedure, or user-facing configuration changed, and its documentation target is clear.
- **No documentation needed**: changes are limited to private refactoring, tests, formatting, or another change that does not alter a documented contract or a useful operating fact.
- **Uncertain**: the diff does not establish intended semantics, the right target is ambiguous, a map conflicts with the documents, or a consequential behavior change lacks a reliable explanation.

For **Updated**, edit the selected documentation without asking for an extra approval. For **No documentation needed**, make no documentation edit. For **Uncertain**, stop before editing and ask a focused question that names the uncertainty and evidence.

## Make a truthful, narrow edit

Write for the changed state, not the sequence of implementation steps. Preserve established terminology, structure, voice, and Markdown conventions. State externally observable behavior, boundaries, constraints, and operational consequences that the change actually supports.

Keep the edit narrow: do not rewrite adjacent sections, add a changelog, document speculative future work, or turn a private helper into public architecture unless the repository's documentation map explicitly calls for it.

## Verify and report

Review the resulting documentation diff together with the implementation diff. Confirm that every documentation claim is supported by the current code or configuration, and run `git diff --check`. Run a repository-provided documentation validation only when it applies to the edited targets.

Report the classification, evidence used, documentation map or fallback used, files changed (or why none changed), validation result, and any remaining uncertainty. Leave all changes unstaged for the user to review and commit.

## Recommended `AGENTS.md` map

Repositories can make target selection deterministic with a compact section such as:

```markdown
## Documentation map

- Public behavior and first-use instructions: `README.md`.
- Architecture boundaries, invariants, and data flow: `ARCHITECTURE.md`.
- Local setup and operational procedures: `docs/development.md`.
- `docs/generated/*` is managed; edit its declared source and run its generator.
```

Keep the map limited to ownership and maintenance facts that cannot be safely inferred from filenames alone.
