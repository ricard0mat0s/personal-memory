---
name: implement
description: Implement one approved GitHub issue through tests, independent review, and a pull request; supports a named issue or backlog pickup.
---

Read `AGENTS.md`, `docs/agents/development-workflow.md`, and
`docs/agents/issue-tracker.md`. Those files define approval, issue eligibility,
branching, verification, PR, and merge rules.

1. Read the named issue and comments, or select the oldest eligible backlog
   issue. Confirm approved scope, acceptance criteria, testing boundaries,
   and blockers. Exclude parent specs. Reuse an existing branch/PR on resume.
2. Claim the issue and create its dedicated branch from current `origin/main`.
   Preserve existing work, using an isolated worktree when necessary.
3. Use [TDD](../tdd/SKILL.md) for features and bug fixes at the approved
   boundaries. Run focused checks while working. Bring missing decisions or
   material scope changes to the owner; proceed with routine implementation.
4. Use [update-documentation](../update-documentation/SKILL.md) for the intended
   change set before committing. Commit in small atomic changes, each with
   one coherent purpose and its necessary code, tests, and documentation.
   Reference the issue in commit messages.
5. Run the full suite and source typechecking using the README commands.
   Commit before review so every intended change is included in `HEAD`.
6. Fetch `origin/main`, pin its merge-base with `HEAD`, and use
   [code-review](../code-review/SKILL.md) with that base and the issue/spec.
   Run Standards and Spec in separate parallel agents. Fix findings within
   scope, rerun affected checks, commit fixes, and review those changes again.
7. Push and open one PR against `main`, linking the issue with `Closes` and
   reporting acceptance evidence, checks, both review axes, and tradeoffs.
   Monitor the required CI checks and address failures within scope. Report
   unavailable verification or review explicitly; do not mark it passed.
8. Present the PR and stop for human review. Handle comments when requested.
   Only merge after explicit authorization and the documented merge gates;
   otherwise the owner may merge directly. Verify merge, sync `main` safely,
   and confirm issue closure. Wait before selecting another issue.

Approval to implement an issue does not authorize merging its PR. Releases
and deployment are outside this skill.
