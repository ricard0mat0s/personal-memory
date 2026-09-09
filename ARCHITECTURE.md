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
- The Retrieval Cap is owned by one `RetrievalRequest` and shared across every
  search and read performed for that user prompt. It is not reset per call.

### Milestone 2 retrieval contract

`RetrievalRequest` carries a non-empty ordinary-text query, optional explicit
Memory Scopes, and private request-level budget state. Omitted scopes mean all
permitted scopes; supplied scopes must be a non-empty tuple containing only
permitted values. A request binds to the first `MemoryWorkspace` that serves it.

`search_memory(request)` refreshes the filesystem and returns at most three
`SearchResult` values. A result exposes the page's POSIX-relative path as its
stable `page_id`, plus `title`, `scope`, a relevant excerpt of at most 40 body
words, and the names of matched fields. Numeric scores remain private. No match
is the empty tuple.

Search case-folds text, removes diacritics, treats punctuation and underscores
as separators, and ignores repeated query terms. Unique term matches are
weighted by field: title 8, scope 4, related pages 2, and literal Markdown body
1. Results are ordered by descending private score and then by case-folded and
exact `page_id`.

`read_memory(request, selection)` accepts a candidate's exact `page_id` or an
unambiguous candidate title. It refreshes the workspace and returns the entire
current Markdown file, including frontmatter. Unknown, stale, non-candidate,
out-of-scope, and ambiguous selections fail through `MemoryRetrievalError`.

The cap counts at most three distinct pages and approximately 1,500 words per
request. Each result excerpt counts once; a later complete read adds the rest
of that page once. If the next complete page crosses the remaining word budget,
that page is returned whole and the request then refuses further new reads.
Repeated searches and reads do not replenish or double-charge the budget. Word
counting uses every match of Python's Unicode-aware `\b[\w'-]+\b` expression in
the returned excerpt or complete Markdown. The 1,500-word threshold is exact
for admitting new material; only that final complete page may cross it. Private
content hashes make repeated unchanged reads free, while changed Current Memory
is new material and is charged again. Scope eligibility is rechecked on reads.

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
  _retrieval.py       # request budget, deterministic ranking, result shaping
  _proposals.py       # private diff and page-version handling
  mcp.py               # future MCP adapter only
tests/
  test_workspace.py   # observable behavior at the MemoryWorkspace seam
  fixtures/           # synthetic, permitted Markdown only
```

This shape preserves **depth**: the public Interface stays small while the
complexity that creates **leverage** and **locality** remains behind it.
