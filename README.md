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
personal memory or require GitHub, OAuth, MCP, or network access at test time.
