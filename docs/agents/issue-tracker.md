# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body-file <path>`. Write multiline bodies to a temporary UTF-8 file and pass it with `--body-file`; use the same approach for PR bodies and long comments.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `gh issue edit <number> --remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

## Implementation issue selection

Follow `development-workflow.md` and the meanings in `triage-labels.md`.
`ready-for-agent` means the owner approved the issue's scope, acceptance
criteria, and testing boundaries. Apply it only after approval. Parent specs
use `spec` and cannot carry readiness, even when their child breakdown is
approved. Standalone executable issues need no parent spec.

For a named issue, read its full body, comments, labels, assignees, and open
blockers. Confirm its approval and that it is executable and unblocked. An
issue already assigned to the driving developer may be resumed; if assigned
to someone else, resolve ownership first. Resume its existing branch/PR.

For backlog pickup, fetch all open `ready-for-agent` candidates (paginate
beyond the CLI's default page), and exclude assigned issues, parent specs,
issues with an active PR, and issues with an open blocker. Use native issue
dependencies when available, otherwise resolve every issue in the
`## Blocked by` section. Unknown blocker state is not unblocked. Choose the
lowest issue number among eligible candidates. Recheck before and after
claiming with `gh issue edit <number> --add-assignee @me`; if ownership changed,
stop rather than duplicating work.

Use native parent/sub-issue links and dependencies where available. When
unavailable, put `## Parent` and `## Blocked by` references in each child and
an explicit child task list in the parent. Link only actual child issues;
searching for every mention of a parent number is not a membership check.
`/to-tickets` may update these links and remove incorrect readiness from a
parent, but it must not close the parent while publishing tickets.

## Implementation pull requests and merge

Open one PR per issue against `main` with `Closes #<number>`. Report acceptance
evidence, local and CI checks, and separate Standards and Spec reviews.
Finish the committed reviews before presenting the PR for the owner's review.

The owner may merge directly. The agent may squash-merge only after explicit
authorization for that PR and the gates in `development-workflow.md`. Verify
the merge before closing the linked issue; opening a PR is not completion.
Check actual child deliveries before closing a parent. Stop after the PR is
presented and after merge; the next issue needs an instruction to continue.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
