# Organize personal_memory into deep workspace, mcp, git, and server modules

`personal_memory` is structured as three deep modules (`workspace/`, `mcp/`, `git.py`) plus a thin composition root (`server.py`) with strictly acyclic dependencies (`server` -> `mcp` -> `workspace` + `git`). `workspace/` stays completely offline and self-contained, consolidating query validation, filtering, deterministic ranking, and Retrieval Request caps in `workspace/_retrieval.py` so richer search and filtering can be added without modifying the transport or Git seams. `mcp/` separates structured schemas, bounded TTL state registries, scope authorization, and tool handlers out of a single closure factory, and calls `MemoryWorkspace` directly.

## Considered Options

- **Add a `Services` layer between MCP tools and Markdown storage.** Rejected: with `MemoryWorkspace` already owning validation, Deterministic Search, and guarded updates, a `Services` layer would become a shallow pass-through module that adds indirection without owning distinct invariants.
- **Abstract Markdown behind a generic Repository port.** Rejected: Markdown files, YAML frontmatter, unified diffs, and Git history are part of the domain (not accidental persistence details), and the local filesystem is already locally substitutable via temporary directories in tests.
- **Move Git commits into the Markdown / workspace module.** Rejected: Git subprocess execution, worktree cleanliness checks, and commit failures are a separate failure domain from local file validation and atomic replacement. Keeping Git behind `UpdateRecorder` preserves offline, Git-free unit tests for `MemoryWorkspace`.
- **Keep all modules flat in `src/personal_memory/` and all MCP logic in one `create_mcp_server()` closure.** Rejected: mixing schemas, TTL registries, authorization, and tool handlers in one function made adding new tools or search parameters harder to extend and obscured module boundaries.

## Consequences

- `workspace/` has zero imports from `mcp/`, `git.py`, `server.py`, or OAuth/HTTP libraries, and `git.py` has zero imports from `workspace/` or `mcp/`; `tests/test_architecture.py` enforces these boundaries automatically.
- Adding richer search and filtering stays localized to `RetrievalRequest`, `workspace/_retrieval.py`, and the corresponding tool parameters in `mcp/_tools.py`.
- `git.py` and `server.py` remain single files until they grow enough to justify subpackages, avoiding unnecessary directory structure.
- Proposal lifecycle remains self-contained inside `MemoryWorkspace` for offline callers, while `mcp/_state.py` continues to own principal isolation and TTL eviction for authenticated MCP sessions.
