# Project Agent Instructions

This project works as my own memory but in another place, I will be able to do simple operations.

Basicaly what I really want with this project is a simple way to retrieve and update information in a file system that every AI agent can use, this way I don't have to deal just with the memory that AI stores.

Details about software architecture and design can be found in the [ARCHITECTURE.md](ARCHITECTURE.md) file.

We're actually building the mcp server that will receive requests and do the correct thing, like read for an file or make changes to it

## Agent skills

### Development workflow

Follow `docs/agents/development-workflow.md` from approved issue through pull
request and merge. When asked to implement a named issue or work on the backlog,
use `.agents/skills/implement/SKILL.md`. One issue gets one branch and PR with
atomic commits, local verification, and separate Standards and Spec reviews.
Stop after presenting the PR. The owner can merge directly, or authorize the
agent to squash-merge after checks and reviews pass. Wait for an instruction
before starting the next issue. Releases are outside this workflow.

Explain important decisions and tradeoffs briefly. Required workflow skills
and their references are tracked under `.agents/skills/` for fresh clones.

### Issue tracker

Issues are tracked in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository using `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.

## Documentation map

- Public behavior, installation, and local verification commands: `README.md`.
- Architecture and module boundaries: `ARCHITECTURE.md`.
- Domain vocabulary and decisions: `CONTEXT.md` and `docs/adr/`.
- Development lifecycle: `docs/agents/development-workflow.md`.
- GitHub operations and issue eligibility: `docs/agents/issue-tracker.md`.
- Label meanings: `docs/agents/triage-labels.md`.
- Auth0 setup and live integration verification: `docs/auth0-postman.md`.
