# Architecture

### Internal design

Markdown parsing, frontmatter validation, lexical ranking, word accounting,
and unified-diff production are in-process implementation details of
`MemoryWorkspace`. They can be separated into private helpers for locality,
but none becomes a caller-facing Interface.

The local filesystem is a local-substitutable dependency: the workspace root
is supplied when constructing the module and tests use temporary directories.
Do not add a repository port or a fake repository yet—there is only one real
adapter, so that seam would be hypothetical indirection.

When `apply_update` gains a Git commit, introduce a commit **seam** only if it
has both a real Git **adapter** and a test adapter. OAuth verification and MCP
transport remain outside this offline module; a future Authorized Connector is
an adapter that translates authenticated MCP requests into this Interface,
not a second home for memory rules.

### Code Shape

```text
src/personal_memory/
  workspace.py        # MemoryWorkspace interface and orchestration
  _markdown.py        # private page parsing and validation
  _retrieval.py       # request budget, deterministic ranking, result shaping
  _proposals.py       # private diff and page-version handling
  mcp.py              # MCP adapter
tests/
  test_workspace.py   # observable behavior at the MemoryWorkspace seam
  fixtures/           # synthetic, permitted Markdown only
```

This shape preserves **depth**: the public Interface stays small while the
complexity that creates **leverage** and **locality** remains behind it.
