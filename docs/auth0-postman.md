# Auth0 and Postman

Auth0 issues a signed access token. Postman sends it as a bearer token to the
MCP server. The server retrieves Auth0's public signing keys, checks the
signature, issuer, audience, expiration, and allowed subject, then enforces the
`memory:read` scope. Neither a client secret nor a downloaded public-key file
is needed by the server.

## Configure Auth0

1. In Applications → APIs, open your API. Select RS256 and add `memory:read`
   and `memory:write` permissions. Copy its exact **Identifier** (audience).
   It can be a URL identifier even while the server runs locally.
2. Create a **Machine to Machine Application** for this initial Postman test.
   Authorize it for your API and grant `memory:read`. Copy its Client ID and
   Client Secret into your private Postman environment, not the server config.
3. Copy your tenant domain from Auth0. The issuer is `https://DOMAIN/`.

This M2M test authenticates the application. It does not test an interactive
user login. For eventual interactive MCP login, configure the client's callback
URLs and authorization-code/PKCE flow; Auth0's Resource Parameter Compatibility
Profile is needed for clients that send `resource` rather than `audience`.

## Run the server

Copy `.env.example` to `.env` and replace its placeholders:

```dotenv
AUTH0_ISSUER=https://YOUR_TENANT.us.auth0.com/
AUTH0_AUDIENCE=YOUR_EXACT_API_IDENTIFIER
MCP_RESOURCE_URL=http://127.0.0.1:8000/mcp
MCP_HOST=127.0.0.1
AUTH0_ALLOWED_SUBJECTS=YOUR_TEST_CLIENT_ID@clients
```

M2M token subjects normally have the form `CLIENT_ID@clients`. Use the exact
`sub` claim from your issued token if different. When adding personal login,
use your Auth0 user's exact `sub`; multiple allowed subjects are comma-separated.
A valid token from another identity is refused. `.env` is ignored by Git and is
loaded from the current directory; existing environment variables take priority.
The existing `.env` is never overwritten by the launcher.

Use a disposable workspace with valid Markdown under `memory/`:

```bash
uv sync --locked
uv run personal-memory-server /path/to/disposable-workspace
```

Alternatively, `uv run python src/server.py /path/to/disposable-workspace`.
The listener defaults to `127.0.0.1` and port 8000. Set `MCP_HOST` or use `--host`
to choose the bind address; the command-line option takes priority. `--port`, `--issuer`,
`--audience`, `--resource-url`, and repeatable `--allowed-subject` options override
configuration. If the port changes, update `MCP_RESOURCE_URL` too (or omit it for
the automatic URL derived from the bind address and port). For wildcard bind
addresses such as `0.0.0.0`, set `MCP_RESOURCE_URL` to the actual client-facing
address. Host and Origin checks accept that configured resource origin.
For hosted access the resource URL must be the external
MCP URL, while the audience must remain your Auth0 API Identifier.

This launcher exposes only `search_memory` and `read_memory`. Write permissions
alone do not expose update tools.

## Obtain a token in Postman

Create an HTTP request with **No Auth**:

```text
POST https://YOUR_AUTH0_DOMAIN/oauth/token
Content-Type: application/json
```

Choose Body → raw → JSON:

```json
{
  "grant_type": "client_credentials",
  "client_id": "{{auth0_client_id}}",
  "client_secret": "{{auth0_client_secret}}",
  "audience": "{{auth0_audience}}",
  "scope": "memory:read"
}
```

Set those Postman variables to the application's credentials and your exact API
Identifier. Send the request and copy the response's `access_token` into a private
`access_token` variable. This proves Auth0 can issue a token for the application.

## Call the MCP server

In the Postman desktop app, create an **MCP request**, select **Streamable HTTP**,
and enter `http://127.0.0.1:8000/mcp`. Under Authorization select **Bearer Token**
and enter `{{access_token}}`. Connect and call `search_memory`:

```json
{"query": "direction"}
```

An empty results list is still a successful authorized search. To read a result,
call `read_memory` with the returned `request_id` and the result's `page_id` as
`selection`.

Verify failures as well:

- Remove the token: HTTP 401.
- Change a token character, use an expired token, or use a token for another
  API or subject: HTTP 401.
- Use a valid token whose issued `scope` omits `memory:read`: the tool refuses
  the search. Omitting `scope` from the token request may still grant default
  scopes; inspect the granted scope or use a test application without read access.

A signing-key lookup failure also refuses authentication. Check the issuer,
audience, allowed subject, token expiry, and network access to Auth0 when a
valid-looking token receives 401. A successful authenticated search proves the
complete Auth0-to-server path works.

References: [Auth0 access-token validation](https://auth0.com/docs/secure/tokens/access-tokens/validate-access-tokens),
[Auth0 test tokens](https://support.auth0.com/center/s/article/How-can-I-get-or-generate-an-access-token-for-testing),
[Postman MCP requests](https://learning.postman.com/docs/use/send-requests/protocols/mcp-requests/create).

## Automated launcher checks

After `uv sync --locked`, run `uv run pytest tests/mcp/test_server_process.py`.
These tests start the installed `personal-memory-server` command in a separate
process and call it through real loopback sockets. They verify missing-token
rejection, authenticated search/read, the two advertised retrieval tools, bad
signatures, wrong issuer/audience/owner, expiry, and insufficient scope.

A local HTTPS fixture serves synthetic signing keys. Only the launched test
process trusts the fixture certificate; normal server configuration continues to
use Auth0's HTTPS signing-key endpoint. No Auth0 credentials or external network
access are needed, but the test environment must permit local sockets.
