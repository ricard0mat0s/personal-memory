# Development workflow

This workflow takes one approved issue through implementation, verification,
pull request review, and merge into `main`. The owner approves scope and
acceptance criteria and decides when to merge. Agents execute routine work
within that scope and briefly explain important decisions and tradeoffs.
Versioning, releases, and deployment are outside this workflow.

## Discovery and approval

Use `/grill-me` for requirements discovery or `/grill-with-docs` when domain
terms or architectural decisions also need attention. Read `CONTEXT.md`,
`ARCHITECTURE.md`, and relevant ADRs before designing changes.

Small work can be a standalone issue. For a larger feature, use `/to-spec` to
publish a parent spec, then `/to-tickets` to draft independently verifiable
vertical slices with explicit blocking relationships. Approve the breakdown
before publishing executable tickets as ready.

Every executable issue needs:

- A concrete behavior or outcome and explicit scope.
- Verifiable acceptance criteria.
- Approved testing boundaries and verification expectations.
- Its parent, if any, and explicit blockers (or `None`).

The owner's approval in the conversation or on GitHub permits the agent to
apply `ready-for-agent` to that exact scope. A maintainer applying the label
also signals approval. Material changes to scope, acceptance criteria, or
testing boundaries require renewed approval; routine implementation choices
within those boundaries do not.

Parent specs carry `spec` and never `ready-for-agent`. They organize child
issues and cannot be picked for implementation. See
[issue eligibility](issue-tracker.md#implementation-issue-selection) and
[label meanings](triage-labels.md).

## Select and claim one issue

When asked to implement a named issue, fetch it and its comments and confirm
it is executable, approved, and unblocked. Resume an existing branch or PR for
that issue rather than duplicating it. If it is assigned to someone else,
resolve ownership before taking over.

When asked to work on the backlog without naming an issue, choose the oldest
eligible issue by issue number: open, `ready-for-agent`, unassigned, with no
open blockers, and neither a parent spec nor an issue with an active PR.
Inspect all candidates, including paginated results. If none is eligible,
report why and stop; do not invent work or bypass blockers.

Recheck ownership and eligibility immediately before assigning the issue to
the driving developer. Recheck after assigning; if another agent has claimed
it, stop rather than proceeding with duplicate work. Keep the issue open
through review; assignment records that work has been claimed.

## Implement and verify

Use `/implement`. Start a dedicated `feat/<issue>-<slug>`,
`fix/<issue>-<slug>`, or `chore/<issue>-<slug>` branch from current `origin/main`.
Keep existing user changes intact; use a separate worktree when needed. One
issue gets one branch and PR. Commit in atomic changes, each with the code,
tests, and documentation needed to make that change coherent. Reference the
issue in commit messages.

For features and bug fixes, use `/tdd`: a failing behavioral test, then the
smallest implementation that passes it, one slice at a time. Use the issue's
approved testing boundaries without asking for them again. For refactors,
use existing coverage and add tests for uncovered behavior. Documentation
and workflow changes get appropriate validation rather than tests that only
assert their wording. A newly needed boundary goes back to the owner.

Run focused checks while working and the full suite and source typechecking
before the PR is presented as verified. The local commands are in
[README.md](../../README.md#development). GitHub Actions runs the full tests
on Ubuntu and Windows with Python 3.12 and typechecking on Ubuntu. CI uses
synthetic workspaces and keys and needs no production Auth0 secrets.

Live Auth0 or cross-client integration checks are distinct from automated
tests. When an acceptance criterion needs them, provide that evidence or
mark the criterion incomplete. A passing synthetic suite does not establish
the live integration gate. If a required check fails or cannot run, explain
the failure and remaining work; do not report the PR as fully verified.

## Documentation, commits, and independent review

Use `/update-documentation` before committing. Follow the documentation map
in `AGENTS.md`; an update is unnecessary when no documented behavior or
operating fact changed. Commit the intended work before invoking
`/code-review`, because its comparison ends at `HEAD`.

Pin the merge-base with current `origin/main` and the reviewed `HEAD` commit.
Run the Standards and Spec reviews as separate parallel agents against the
same committed diff. Give the Spec reviewer the originating issue, its
comments, and the parent spec when relevant.

Fix findings within the approved scope and rerun affected checks. Commit
the fixes and review the affected changes again. Any new scope decision
goes back to the owner. Report both review axes separately, including any
remaining findings; one axis cannot compensate for a failure on the other.
If a required reviewer is unavailable, report the incomplete review rather
than claiming both reviews passed.

## Pull request and human review

Push the branch and open a PR against `main`. Include:

- The concrete problem and resulting behavior, with `Closes #<issue>`.
- Acceptance criteria mapped to verification evidence.
- Local check results and the Ubuntu/Windows CI results, or their pending
  state until the runs finish.
- Standards and Spec review results for the current revision.
- Important decisions, tradeoffs, and any remaining limitations.

Wait for CI and address failures within scope. Stop after presenting the PR
and its evidence to the owner. Do not start another issue or merge on the
strength of the original implementation approval.

When asked to address review comments, make the changes within scope, update
documentation and verification as needed, commit and push, then present the
updated revision. New scope requires approval. The PR returns to human
review after changes.

## Merge and finish

The owner may merge through GitHub directly, or explicitly instruct the
agent to merge a particular PR. For an agent merge, fetch the current PR
state and require successful Ubuntu tests, Windows tests, and Ubuntu
typechecking for the latest revision, completed Standards and Spec reviews,
resolved blocking review findings, and no unresolved change requests. A
missing, pending, skipped, cancelled, or failed required check is not a pass.
If the reviewed revision changed after merge authorization, present it for
renewed authorization before merging.

Use `gh pr merge --squash --delete-branch` after authorization. Confirm the
merge before closing anything. If the owner merged directly, verify that
state rather than attempting another merge. GitHub normally closes the
linked issue via `Closes`; otherwise close it after confirming the merge.

Refresh the remote and fast-forward a clean local `main` to `origin/main`.
Preserve unrelated changes and worktrees; if a local checkout prevents that
sync, report it rather than resetting or discarding work. A parent spec can
close when all its approved child deliveries are merged or the owner has
explicitly removed the remaining scope. Do not equate an arbitrarily closed
child with delivered behavior.

Report the merge and issue state. Wait for the owner's instruction before
starting another issue. Do not create a release or change hosting settings.
