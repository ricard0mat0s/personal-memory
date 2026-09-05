# Architecture

## Offline Memory Core

The first implementation is one **deep module**, `MemoryWorkspace`. Its
**Interface** is the four user-facing memory operations: `search_memory`,
`read_memory`, `propose_update`, and (later) `apply_update`. Callers learn
the memory contract once; the module hides Markdown parsing, content
eligibility checks, lexical ranking, result shaping, diff generation,
conflict detection, and eventual Git work.

`MemoryWorkspace` is the external **seam** for the offline core. Tests cross
that same seam using a temporary fixture repository; they do not mock its
private parsing, ranking, or diff logic.

### Interface invariants

- `search_memory` returns deterministic Search Results only from Permitted
  Memory and never treats Raw Transcripts as memory.
- `read_memory` returns Current Memory for an unambiguous Memory Page. It
  does not expose repository history as current context.
- `propose_update` returns an exact Proposed Update and performs no write.
- `apply_update` is deferred until the offline contracts have passed. When
  introduced, it requires an Explicit Approval for the same diff and target
  page version; the Conflict Gate rejects a stale proposal.
- The Retrieval Cap remains a pending product decision: the current glossary
  models it per Retrieval Request rather than per tool call. No implementation
  should silently treat that interpretation as approved.

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

### Suggested code shape

```text
src/personal_memory/
  workspace.py        # MemoryWorkspace interface and orchestration
  _markdown.py        # private page parsing and validation
  _search.py          # private deterministic ranking and result shaping
  _proposals.py       # private diff and page-version handling
  mcp.py               # future MCP adapter only
tests/
  test_workspace.py   # observable behavior at the MemoryWorkspace seam
  fixtures/           # synthetic, permitted Markdown only
```

This shape preserves **depth**: the public Interface stays small while the
complexity that creates **leverage** and **locality** remains behind it.
