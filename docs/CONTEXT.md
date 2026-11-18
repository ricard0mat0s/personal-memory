# Personal Memory

Personal Memory is a private, single-user system for retaining concise, durable knowledge across supported AI clients. Its vocabulary protects the boundary between curated memory and raw conversation, and between a proposed change and a committed one.

## Memory

**Durable Memory**:
A concise, deliberately retained statement that remains useful beyond the conversation in which it arose.
_Avoid_: Chat history, transcript, conversation log

**Memory Page**:
A concise Markdown document for one long-lived topic, with human-readable content and metadata that identifies its primary scope and related pages.
_Avoid_: One-file-per-fact, generated record, note dump

**Memory Scope**:
The primary context in which a Durable Memory is relevant: Personal History, Career & Job Opportunities, Organization/Work Context, or one Individual Project.
_Avoid_: Folder, namespace, tag collection

**Permitted Memory**:
The user's own non-confidential personal, career, organization/work, and project knowledge that fits a Memory Scope.
_Avoid_: Employer confidential information, third-party personal information, credentials

**Canonical Memory Repository**:
The private Git-backed collection of Memory Pages that is the sole source of truth for Durable Memory.
_Avoid_: Client cache, Obsidian database, secondary mirror

**Current Memory**:
The authoritative wording of a Durable Memory after an Explicit Update.
_Avoid_: Transcript, immutable event

**Memory History**:
Earlier versions of Current Memory, preserved as meaningful repository history and normally excluded from retrieval.
_Avoid_: Current Memory, chat archive

**Raw Transcript**:
Uncurated text from a chat or session that is outside the system's intended content.
_Avoid_: Memory, source of truth, import source

## Retrieval

**Retrieval Request**:
The complete, bounded set of memory material assembled to answer one user prompt, even when the Memory Client uses more than one read or search operation.
_Avoid_: Tool call, unrestricted browsing session

**Bounded Retrieval**:
Retrieval of only the Memory Scopes clearly relevant to a Retrieval Request.
_Avoid_: Global context injection, indiscriminate recall

**Deterministic Search**:
Bounded Retrieval that ranks only Memory Page titles, YAML scope, related pages, and literal Markdown text.
_Avoid_: Semantic index, embedding search, opaque ranking

**Search Result**:
A candidate Memory Page returned by Deterministic Search, identified with the information needed to decide whether it belongs in the Retrieval Request.
_Avoid_: Memory Page, retrieved context

**Retrieval Cap**:
The limit of at most three Memory Pages and roughly 1,500 words made available for one Retrieval Request.
_Avoid_: Per-call limit, whole-vault context, unlimited recall

## Change Control

**Proposed Update**:
The exact Markdown diff of an intended memory change, tied to the Memory Page version from which it was produced.
_Avoid_: Silent rewrite, unreviewed extraction, automatic capture

**Explicit Approval**:
The user's deliberate confirmation of one exact Proposed Update. It is specific to that diff and its target version; it is not standing permission to change memory.
_Avoid_: Blanket consent, implied consent, background authorization

**Explicit Update**:
A deliberate, user-requested change to Durable Memory performed only after Explicit Approval of its Proposed Update.
_Avoid_: Silent capture, automatic logging

**Conflict Gate**:
The refusal to apply an Explicit Update when its target Memory Page no longer matches the version used for its Proposed Update.
_Avoid_: Automatic merge, silent rebase

## Access

**Memory Client**:
ChatGPT Work or Codex when it retrieves or explicitly updates Durable Memory.
_Avoid_: Memory store, source of truth

**Authorized Connector**:
The shared MCP-facing bridge that serves a Memory Client only for the authenticated owner and does not expose the Canonical Memory Repository directly.
_Avoid_: Anonymous file endpoint, public repository access

**Cross-Client Access**:
The same Current Memory being available to both Memory Clients through the Authorized Connector, with deliberate Markdown attachment as a fallback.
_Avoid_: Client-specific copy, separate memory store

**Integration Gate**:
The successful invocation of the same personal-memory connector from one ChatGPT Work chat and one supported Codex surface before Cross-Client Access is considered available.
_Avoid_: Assumed compatibility, untested installation

**Knowledge Interface**:
Obsidian when it browses or manually edits the Canonical Memory Repository without becoming a separate source of truth.
_Avoid_: Memory platform, canonical store
