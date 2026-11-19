# Architecture

### Module Boundaries and Dependency Direction

`personal_memory` is organized around deep modules with thin public interfaces
and a strictly acyclic dependency direction:

```text
server.py  ──▶  mcp/  ──▶  workspace/   (offline, self-contained core)
                 └───▶  git.py          (isolated Git recording seam)
```

- **`workspace/`** (`MemoryWorkspace`, domain value types, domain errors):
  owns Markdown parsing and frontmatter validation, Deterministic Search
  (query validation, scope filtering, lexical ranking, excerpts, and Retrieval
  Request caps), unified-diff proposals, Conflict Gate checks, and atomic
  page replacement. Its internal modules stay private; none becomes a
  caller-facing interface.
- **`git.py`** (`UpdateRecorder`, `GitUpdateRecorder`, `GitRecordingError`):
  isolates Git worktree verification and target-only commits behind a narrow
  seam with both a real Git adapter and test doubles.
- **`mcp/`** (`create_mcp_server()`): the Authorized Connector protocol
  adapter. It owns JSON-safe tool schemas, bounded TTL and principal-isolated
  registries for Retrieval Requests and Proposed Updates, per-tool scope
  authorization (`memory:read` / `memory:write`), and tool registration. It
  calls `MemoryWorkspace` directly without an intermediate pass-through layer.
- **`server.py`** (`main()`, `JwtTokenVerifier`): the composition root for
  CLI/environment configuration, Auth0 RS256 token verification, and HTTP
  transport startup.

The local filesystem remains a local-substitutable dependency: the workspace
root is supplied when constructing `MemoryWorkspace`, and tests use temporary
directories. Do not add a repository port or fake repository while the
Canonical Memory Repository is the sole persistence model.

See [ADR-0002](adr/0002-deep-module-architecture.md) for the rationale behind
these boundaries.

### Code Shape

```text
src/personal_memory/
  __init__.py         # Public offline core re-exports
  workspace/
    __init__.py       # MemoryWorkspace interface and orchestration
    _errors.py        # Domain error hierarchy
    _markdown.py      # Private page parsing and frontmatter validation
    _retrieval.py     # Query validation, filtering, deterministic ranking, caps
    _proposals.py     # Private diff, approval matching, and atomic replacement
  mcp/
    __init__.py       # create_mcp_server() entrypoint
    _schemas.py       # Pydantic structured tool responses
    _state.py         # Bounded TTL, principal-isolated state registries
    _authz.py         # Tool-level scope checks and resource scope metadata
    _tools.py         # Tool handlers, annotations, and registration
  git.py              # UpdateRecorder seam and GitUpdateRecorder
  server.py           # CLI, Auth0 JwtTokenVerifier, and HTTP launcher
tests/
  test_workspace.py   # Observable behavior at the MemoryWorkspace seam
  test_architecture.py# Enforces acyclic module boundaries
  mcp/                # Synthetic MCP, authorization, Git, and launcher tests
```

This shape preserves **depth**: each public interface stays small while the
complexity that creates **leverage** and **locality** remains behind it.
