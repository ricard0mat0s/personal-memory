# personal-memory

Private, Git-backed durable memory for supported AI clients.

Milestones 1 and 2 provide an offline `MemoryWorkspace` boundary that validates
synthetic Markdown pages under a supplied workspace's `memory/` directory.
It rejects pages without valid YAML metadata, unsupported memory scopes, raw
transcripts without the page contract, and related-page paths that escape the
memory root. Deterministic retrieval searches only validated page titles,
scopes, related-page paths, and literal Markdown bodies.

```python
from personal_memory import MemoryWorkspace, RetrievalRequest

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

## Development

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync --locked
uv run pytest
```

The test suite creates temporary synthetic workspaces. It does not read real
personal memory or require GitHub, OAuth, MCP, or network access at test time.
