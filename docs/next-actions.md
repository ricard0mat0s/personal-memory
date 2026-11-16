# Next action

Complete the live Integration Gate for
[issue #18](https://github.com/ricard0mat0s/personal-memory/issues/18): connect
Codex and ChatGPT Work to the server with a browser login, using
[Connect ChatGPT and Codex](connect-memory-clients.md). Record the sanitized
evidence in the implementation pull request.

1. Configure the Auth0 tenant and API, and expose the server through the stable
   HTTPS tunnel, following the guide. Use a disposable workspace containing only
   synthetic Memory Pages.
2. In Codex, run `codex mcp add` and `codex mcp login`, finish the Auth0 login in
   the browser, then call `search_memory` and `read_memory` with the same returned
   Retrieval Request ID.
3. Add the same server as a ChatGPT Work connector, finish the login, and repeat the
   search and read.
4. Record whether each client received a refresh token (for example, that a call
   still succeeds after the access token expires) and whether `offline_access` had to
   be requested; update the guide with what you observe.
5. Record the tested revision, timestamp, endpoint, clients and versions, tools
   advertised, search/read outcomes, and the missing-token HTTP 401. Exclude tokens,
   client secrets, and personal Memory Pages.

The automated suite uses synthetic signing keys and is not evidence of a successful
live Auth0 or client run. These checks need the owner's real tenant, tunnel, and
clients. The [Postman guide](auth0-postman.md) is an optional smoke test that
needs no Memory Client.
