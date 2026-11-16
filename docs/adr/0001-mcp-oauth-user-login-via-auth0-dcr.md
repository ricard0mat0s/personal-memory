# Memory Clients authenticate by MCP OAuth user login through Auth0 Dynamic Client Registration

Memory Clients (ChatGPT Work and Codex) authenticate to the Authorized Connector as the owner through the standard MCP OAuth flow: they discover Auth0 from the server's Protected Resource Metadata, register themselves with Auth0 Dynamic Client Registration, log in with authorization code + PKCE, and refresh tokens silently. This replaces manually minting Machine-to-Machine tokens in Postman and pasting them into each client. Anyone may register a client with Auth0, so registration is deliberately not the access boundary: the server's exact allowed-subject check (the owner's Auth0 user `sub`) is.

## Considered Options

- **Automate the M2M token fetch with a script.** Rejected: tokens still expire and must be re-injected per client; ChatGPT cannot accept a pasted bearer token.
- **Pre-registered static Auth0 applications per client.** Rejected: not every Memory Client accepts a manually supplied client ID.
- **The server acts as its own OAuth proxy in front of Auth0.** Rejected: puts token issuance and secrets in the server, which today only verifies tokens.

## Consequences

- The Auth0 API Identifier must equal the public MCP resource URL (`AUTH0_AUDIENCE == MCP_RESOURCE_URL`) because clients send `resource`, mapped to `audience` by Auth0's Resource Parameter Compatibility Profile. This requires a stable hostname, served for now by an HTTPS tunnel to the owner's machine.
- The server advertises `memory:read` and `memory:write` as supported scopes; Auth0 RBAC limits granted scopes to permissions assigned to the owner.
- With frictionless login, `apply_update` remains Explicit Approval; it is annotated as destructive so clients confirm with the owner before calling it.
- The Postman M2M flow remains only as an optional smoke test.
