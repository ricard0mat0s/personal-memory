# personal-memory

Private, Git-backed durable memory for supported AI clients.

Milestones 1 through 4 provide an offline `MemoryWorkspace` boundary that
validates synthetic Markdown pages under a supplied workspace's `memory/`
directory.
It rejects pages without valid YAML metadata, unsupported memory scopes, raw
transcripts without the page contract, and related-page paths that escape the
memory root. Deterministic retrieval searches only validated page titles,
scopes, related-page paths, and literal Markdown bodies.

```python
from personal_memory import ExplicitApproval, MemoryWorkspace, RetrievalRequest

workspace = MemoryWorkspace("path/to/canonical-repository")
request = RetrievalRequest(
    "project evaluation",
    scopes=("individual_project",),
)
results = workspace.search_memory(request)
if results:
    current_markdown = workspace.read_memory(request, results[0].page_id)
```

One `RetrievalRequest` owns the cap shared by all retrieval work for one user
prompt: at most three distinct pages and approximately 1,500 words. Search
results have stable repository-relative page IDs, short relevant excerpts, and
no public ranking score. The complete page that crosses the remaining word
budget is returned without truncation; further new reads are then refused.

`propose_update` is a no-write review step. Give it an existing page's exact
repository-relative ID and complete replacement Markdown; it returns a stable
version token and an exact unified diff for deliberate approval later.

```python
proposal = workspace.propose_update(
    "projects/harpia.md",
    replacement_markdown,
)
print(proposal.version_token)
print(proposal.diff)
```

After a person or authorized caller approves that exact diff, record and apply
the approval through the same workspace:

```python
# Display and approve proposal.diff before constructing this value.
approval = ExplicitApproval.for_proposal(proposal)
result = workspace.apply_update(proposal, approval)
```

`apply_update` reloads Current Memory, rejects mismatched, stale, foreign, or
already-used proposals, and atomically replaces only the target page. It does
not create Git history or authenticate the human approval; those
responsibilities remain outside the offline module.

## Development

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync --locked
uv run pytest
```

The test suite creates temporary synthetic workspaces. It does not read real
personal memory or require GitHub, a live OAuth provider, or network access at
test time.

### Authenticated retrieval smoke test

Milestone 5's first two iterations expose `search_memory` and `read_memory`
through authenticated Streamable HTTP. To exercise the real MCP and
authorization path against local Markdown files without opening a port, point
the smoke script at a disposable workspace that contains a `memory/` directory:

```powershell
uv run python scripts/smoke_authenticated_retrieval.py `
  C:\path\to\disposable-workspace `
  "project direction" `
  --scope individual_project `
  --read-first
```

The script uses a synthetic token inside one process. It reads and validates the
real files in the supplied workspace, prints the structured Search Results and
opaque request ID, and, with `--read-first`, reads and prints the complete current
Markdown for the first result through that same bounded request. It performs no
writes and does not contact an identity provider or other network service. Do
not point initial experiments at the canonical personal-memory repository; copy
a few non-sensitive pages into a disposable workspace first.

The MCP adapter requires `memory:read` for `search_memory` and `read_memory`.
It requires the separate `memory:write` scope for `propose_update` and
`apply_update`; a read-only token cannot create proposal state or invoke an
update. Resource and token validation still occur before any tool-level scope
check. Configured read and write scope names must be non-empty and distinct.

### Authenticated proposals

The MCP adapter also exposes `propose_update` through the same authenticated
Streamable HTTP boundary. The caller supplies an existing page's exact ID and
complete replacement Markdown. Success returns an opaque `proposal_id` together
with the exact target page, current version token, and unified diff that must be
shown for later explicit approval.

Creating a proposal does not change Current Memory or Git history. Pending
proposals are tied to the authenticated principal and retained only in bounded
process memory: at most 128 entries for 15 minutes by default. They are lost on
restart and use a state registry separate from Retrieval Requests.

### Authenticated approval, application, and recording

Calling MCP `apply_update` with that exact `proposal_id` is the authorized
caller's explicit approval. The adapter resolves only a pending proposal owned
by that authenticated principal, creates the offline `ExplicitApproval`, and
delegates the stale, foreign, and single-use checks plus atomic replacement to
the same `MemoryWorkspace` that created the proposal. A successful response
returns the applied page's old and new version tokens.

Before changing Current Memory, the recorder requires the supplied workspace to
be the Git worktree root, a configured Git author, and a tracked, clean target
page. It then commits only that page with the subject
`memory: update <page_id>`; unrelated staged or working-tree changes are not
included. If Git recording fails, the workspace atomically restores Current
Memory and keeps the proposal available for the same authenticated caller to
retry after inspecting Git status. If restoration itself fails, the tool reports
that recovery failure for manual intervention.
