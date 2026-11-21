# Personal Memory

## Introduction

Personal Memory provides a private, Git-backed memory workspace that AI
clients can read and update through a controlled interface. It solves the
problem of keeping durable, shared context in files instead of relying only on
an AI provider's transient memory.

The project is built with Python 3.12+, Markdown files with YAML frontmatter,
and a local filesystem-backed `MemoryWorkspace`. An authenticated MCP server
exposes the workspace over Streamable HTTP. Auth0 access tokens protect the
server, and Git records approved memory updates.

## Quick start

Install Python 3.12 or later and [uv](https://docs.astral.sh/uv/), then install
the locked dependencies:

```bash
uv sync --locked
```

For local development, run the tests and type checker:

```bash
uv run --no-sync pytest
uv run --no-sync mypy
```

To run the authenticated MCP server, copy the example environment file,
configure the Auth0 issuer, audience, and allowed subject, then provide a
workspace containing a `memory/` directory:

```bash
cp .env.example .env
uv run personal-memory-server /path/to/workspace
```

The server exposes `search_memory`, `read_memory`, `propose_update`, and
`apply_update`. Read operations require `memory:read`; update operations
require `memory:write`. See [Connect ChatGPT and Codex](docs/connect-memory-clients.md)
for client and tunnel setup. For an offline example that does not require
Auth0 or a running server, see
`scripts/smoke_authenticated_retrieval.py`.

## Architecture

The project has three main layers:

- **Memory workspace:** `MemoryWorkspace` loads and validates Markdown pages
  under `<workspace>/memory`, performs deterministic scoped retrieval, enforces
  request word/page budgets, and creates or applies exact update proposals.
- **MCP adapter:** `personal_memory.mcp` translates authenticated MCP tool
  calls into workspace operations. It keeps retrieval requests and update
  proposals bounded, short-lived, and tied to the authenticated principal.
- **Server and recording boundary:** `personal_memory.server` validates Auth0
  JWTs and runs the Streamable HTTP transport. Approved updates are atomically
  applied and recorded as Git commits for the target page only.

Parsing, validation, ranking, budgeting, and diff generation remain private
workspace implementation details. The architecture and module boundaries are
described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
