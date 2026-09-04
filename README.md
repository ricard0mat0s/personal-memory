# personal-memory

Private, Git-backed durable memory for supported AI clients.

Milestone 1 provides an offline `MemoryWorkspace` boundary that validates
synthetic Markdown pages under a supplied workspace's `memory/` directory.
It rejects pages without valid YAML metadata, unsupported memory scopes, raw
transcripts without the page contract, and related-page paths that escape the
memory root.

## Development

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync --locked
uv run python -m unittest discover -s tests -v
```

The test suite creates temporary synthetic workspaces. It does not read real
personal memory or require GitHub, OAuth, MCP, or network access at test time.
