# Auth0 and Postman

Auth0 issues a signed access token. Postman sends it as a bearer token to the
MCP server. The server retrieves Auth0's public signing keys, checks the
signature, issuer, audience, expiration, and allowed subject, then requires
`memory:read` for retrieval tools and `memory:write` for update tools. Neither
a client secret nor a downloaded public-key file is needed by the server.

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

From the repository root, create a disposable workspace with one synthetic
Memory Page. The following commands use Bash (including WSL):

```bash
SMOKE_WORKSPACE="$(mktemp -d -t personal-memory-smoke-XXXXXX)"
mkdir "$SMOKE_WORKSPACE/memory"
cat > "$SMOKE_WORKSPACE/memory/smoke.md" <<'MARKDOWN'
---
title: Smoke verification
scope: individual_project
related_pages: []
---

Disposable memory used to verify live Auth0 retrieval.
MARKDOWN

uv sync --locked
uv run personal-memory-server "$SMOKE_WORKSPACE" --host 127.0.0.1 --port 8000
```

Keep that terminal running while using Postman. This run uses the normal Auth0
issuer configured in `.env`; do not replace it with the automated tests' issuer
or certificate settings. Use the same audience in `.env` and Postman, and put
the token's exact allowed subject in `AUTH0_ALLOWED_SUBJECTS`.

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

The launcher exposes `search_memory`, `read_memory`, `propose_update`, and
`apply_update`. A read-only token can list the tools and call the retrieval
tools. Calling either update tool requires `memory:write`.

Missing or blank issuer, audience, or allowed subjects stop startup before the
HTTP listener opens. Invalid issuer/resource URLs and ports also stop startup.
The issuer must be an HTTPS tenant origin. The resource must be an absolute
HTTP(S) URL without credentials, a query, or a fragment; omit it to derive the
URL from the bind address and port, rather than setting it to an empty string.

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
{"query": "Smoke verification", "scopes": ["individual_project"]}
```

The search must succeed and return `smoke.md`, titled `Smoke verification`, plus
a `request_id`. Copy that ID from this actual response. In the same MCP
connection, call `read_memory` with:

```json
{"request_id": "PASTE_THE_RETURNED_REQUEST_ID", "selection": "smoke.md"}
```

The read must succeed and return the complete Markdown above, including
`Disposable memory used to verify live Auth0 retrieval.` An empty search result
or a successful connection alone does not complete this smoke check. Search and
read must use the same Retrieval Request; if it expires or the server restarts,
search again and use the new ID.

Verify failures as well:

- Remove the token: HTTP 401.
- Change a token character, use an expired token, or use a token for another
  API or subject: HTTP 401.
- Use a valid token whose issued `scope` omits `memory:read`: the tool refuses
  the search. Omitting `scope` from the token request may still grant default
  scopes; inspect the granted scope or use a test application without read access.

A signing-key lookup failure also refuses authentication. Check the issuer,
audience, allowed subject, token expiry, and network access to Auth0 when a
valid-looking token receives 401. A successful search followed by the matching
read demonstrates live retrieval through the Auth0-to-server path.

## Record live smoke evidence

After the manual check, add a sanitized record to the pull request using this
template. Replace each placeholder with an observed result; these instructions
and passing automated tests are not evidence that a live Auth0 run happened.
Use `git rev-parse HEAD` to record the tested revision.

```text
Tested commit: <SHA>
UTC date/time: <timestamp>
Provider and grant: Auth0 / client_credentials
Token source: real Auth0 tenant, not synthetic test credentials
Issuer/audience/allowed subject matched server configuration: <yes/no>
MCP client: Postman <version>, Streamable HTTP
Endpoint: http://127.0.0.1:8000/mcp
Workspace: disposable workspace, only synthetic smoke.md
Advertised tools: <observed tool names>
Search: query="Smoke verification", scopes=["individual_project"]
Search result: <page_id and title>
Returned Retrieval Request ID: <actual ID>
Read: selection="smoke.md", request_id=<same actual ID>
Read outcome: <success/error; confirm complete Markdown and expected body>
Missing-token check: <observed HTTP status>
```

Record outcomes or sanitized response bodies, excluding Authorization headers,
access/refresh/ID tokens, client secrets, and personal Memory Pages. Do not attach
a Postman environment or collection export containing credentials. When finished,
stop the disposable server with Ctrl+C; the temporary workspace can be discarded.

References: [Auth0 access-token validation](https://auth0.com/docs/secure/tokens/access-tokens/validate-access-tokens),
[Auth0 test tokens](https://support.auth0.com/center/s/article/How-can-I-get-or-generate-an-access-token-for-testing),
[Postman MCP requests](https://learning.postman.com/docs/use/send-requests/protocols/mcp-requests/create).

## Automated launcher checks

After `uv sync --locked`, run `uv run pytest tests/mcp/test_server_process.py`.
These tests start the installed `personal-memory-server` command in a separate
process and call it through real loopback sockets. They verify missing-token
rejection, authenticated search/read, the four advertised tools, bad
signatures, wrong issuer/audience/owner, expiry, and insufficient scope.

A local HTTPS fixture serves synthetic signing keys. Only the launched test
process trusts the fixture certificate; normal server configuration continues to
use Auth0's HTTPS signing-key endpoint. No Auth0 credentials or external network
access are needed, but the test environment must permit local sockets.
