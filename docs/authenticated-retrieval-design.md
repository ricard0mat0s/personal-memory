# Authenticated memory retrieval: agreed design

## Goal

Extend the existing MCP adapter into a running, local HTTP server. A small client opens a browser for Auth0 login, then uses the server to search and read Memory Pages. The implementation is a learning exercise: the project owner will build it through small test-driven steps.

The milestone is complete when the owner logs in through Auth0 and retrieves a page from a disposable workspace. Automated tests remain offline.

## Scope and boundaries

- Serve one Canonical Memory Repository at a time. Supply its directory as a command line argument at startup. Use disposable Memory Pages during development and the final check.
- Bind the HTTP server to the local machine for this milestone.
- Advertise only `search_memory` and `read_memory`. The existing update tools are outside this server's offered capabilities.
- Keep OAuth login and access-token verification in the MCP-facing code. `MemoryWorkspace` remains responsible for retrieval rules and the Retrieval Cap.
- Use maintained libraries for OAuth and token-validation protocol details. The project owner writes the client and server integration.

## Authentication and authorization

Register a native client application and a resource API with Auth0. The small client starts a browser-based Authorization Code with PKCE flow and requests an access token for the memory API with the `memory:read` scope. The client sends that access token with MCP requests; an ID token is not a substitute for the API access token.

Before returning memory, the server validates the access token's signature, issuer, audience, and expiry. It also requires the configured Auth0 user ID (`sub`) and the `memory:read` scope. Missing, invalid, expired, wrong-audience, wrong-user, and insufficient-scope tokens cannot retrieve memory. The server trusts only the configured issuer and its keys; token-supplied key locations are not trusted.

Supply Auth0 settings, the expected API identifier, and the owner's Auth0 user ID through environment variables. Reject missing or invalid configuration at startup. The existing example verifier in `src/main.py` accepts arbitrary tokens and must not be used by the running server.

## Test seam and TDD sequence

Test observable behavior through a **separate running HTTP server process** and a small MCP client. Use a temporary workspace containing synthetic Memory Pages. Automated tests do not call Auth0: they sign access tokens with a temporary test key and configure the test server to trust the matching test public key. The real server configuration trusts Auth0's keys, never the test key. `test_unauthorized_search_is_refused_before_memory_is_opened` already checks unauthenticated requests against the MCP app through an in-process ASGI transport. Do not repeat that adapter test; the new test must exercise the command line launcher and a real local socket.

Work one red → green cycle at a time, keeping each test after it passes:

1. Launch the server as a separate process with a temporary workspace supplied on the command line and test settings in the environment. Send a valid MCP request over a local socket without a token; expect HTTP `401`. This is a startup and wiring test: the `401` is the observable proof that the launched process serves the protected MCP endpoint.
2. Send a locally signed, valid owner token; search for a known page and read it through the returned Retrieval Request ID. Confirm that only the two retrieval tools are advertised.
3. Add one failing case at a time for a bad signature, wrong issuer, wrong audience, expired token, wrong user ID, and missing `memory:read` scope. Make each pass before adding the next.
4. Add the browser login to the small client and manually verify login, search, and read with Auth0 against disposable pages.

The first implementation step is **only step 1's failing process-level test**, followed by the smallest change that makes it pass. Later steps should preserve the existing bounded retrieval behavior and authorization checks.

## Deferred choices

Choose exact command and environment-variable names, HTTP port, OAuth library, and local callback details when implementing their first relevant slice. Remote access, other MCP clients, and memory updates are outside this milestone.
