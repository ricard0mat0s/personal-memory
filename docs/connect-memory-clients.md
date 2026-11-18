# Connect ChatGPT and Codex

Memory Clients sign in to the Authorized Connector with a one-time browser login as
the owner. No Auth0 credentials are copied, no token is requested in Postman, and
no bearer token is pasted into a client. See
[ADR 0001](adr/0001-mcp-oauth-user-login-via-auth0-dcr.md) for why.

How it works: the server's Protected Resource Metadata names Auth0 as the
authorization server and advertises the OAuth scopes `memory:read` and
`memory:write` (unrelated to a Memory Scope). The client
registers itself with Auth0 (Dynamic Client Registration), sends you to Auth0 to
log in (authorization code + PKCE), and refreshes its own tokens afterwards. The
server accepts only tokens whose `sub` is in `AUTH0_ALLOWED_SUBJECTS`; anyone can
register a client with Auth0, so that check, not registration, is the access
boundary. Each tool still requires its own OAuth scope.

## 1. Choose a stable public MCP URL

ChatGPT needs a public HTTPS URL, and clients send that URL as the OAuth `resource`.
Use a hostname you control, for example `https://memory.example.com/mcp`, served by
a named Cloudflare Tunnel or Tailscale Funnel pointing at `http://127.0.0.1:8000`.
Start the tunnel manually whenever you want the clients to reach the server. A URL
that changes on every restart will not work, because it must equal the Auth0 API
Identifier below.

Example with a named Cloudflare Tunnel (one-time setup, then the last command each
session):

```bash
cloudflared tunnel login
cloudflared tunnel create personal-memory
cloudflared tunnel route dns personal-memory memory.example.com
cloudflared tunnel run --url http://127.0.0.1:8000 personal-memory
```

Or with Tailscale Funnel, which gives a fixed `https://MACHINE.TAILNET.ts.net`
hostname: `tailscale funnel 8000`. The server checks the `Host` and `Origin` headers
against `MCP_RESOURCE_URL`; if requests through the tunnel are rejected, confirm
the tunnel forwards the public hostname rather than rewriting it. These commands
are examples to check against your tunnel provider's current documentation.

## 2. Configure Auth0 once

1. **API** (Applications → APIs): set the **Identifier** to the exact public MCP
   URL from step 1, use RS256, and add the `memory:read` and `memory:write`
   permissions. Enable **RBAC** and **Allow Offline Access**.
2. **Tenant settings → Advanced**: enable **OIDC Dynamic Application Registration**
   and the **Resource Parameter Compatibility Profile**, so a client's `resource`
   is treated as the API audience.
3. **Login connection** (Authentication → your database or social connection):
   promote it to **domain level**. Dynamically registered clients are third-party
   applications and can only use domain-level connections.
4. **Your user**: assign both permissions (directly or through a role). Copy the
   user's exact `sub`, such as `auth0|abc123`, from User Management.
5. Keep access tokens short-lived (for example one hour). Refresh-token rotation
   can be enabled per application in Auth0 (Applications → the application's Refresh
   Token Rotation setting, once a client has registered).

## 3. Configure and run the server

Copy `.env.example` to `.env`:

```dotenv
AUTH0_ISSUER=https://YOUR_TENANT.us.auth0.com/
AUTH0_AUDIENCE=https://memory.example.com/mcp
MCP_RESOURCE_URL=https://memory.example.com/mcp
MCP_HOST=127.0.0.1
AUTH0_ALLOWED_SUBJECTS=auth0|YOUR_USER_ID
```

`AUTH0_AUDIENCE` and `MCP_RESOURCE_URL` must be identical. Host and Origin checks
accept the `MCP_RESOURCE_URL` origin. Then start the server and the tunnel:

```bash
uv sync --locked
uv run personal-memory-server /path/to/memory-workspace
```

Try a disposable workspace first (see
[Auth0 and Postman](auth0-postman.md#run-the-server)); do not point initial
experiments at the canonical personal-memory repository.

## 4. Connect a Memory Client

**Codex**

```bash
codex mcp add personal-memory --url https://memory.example.com/mcp
codex mcp login personal-memory
```

Complete the Auth0 login in the browser that opens. Codex stores the tokens in its
credential store and refreshes them. If Auth0 rejects the request for a missing
resource, Codex's configuration has an optional `oauth_resource` setting for the
server's entry in `~/.codex/config.toml`; set it to the same URL (check Codex's
current documentation for the exact key).

**ChatGPT Work**: add a custom MCP connector from ChatGPT's connector settings (a
plan and developer mode that allow custom connectors are required), enter the
public MCP URL, choose OAuth, and complete the Auth0 login. Menu names change, so
follow ChatGPT's current documentation.

Then ask the client to search and read a page. The server marks `propose_update` as
a non-destructive write and `apply_update` as destructive, so clients prompt you
before calling `apply_update` (verified in Codex and Antigravity). Applying an
update is still your Explicit Approval of the diff.

## Troubleshooting

- **Login succeeds but every call returns 401**: the token's `sub` is not in
  `AUTH0_ALLOWED_SUBJECTS`, or the token's audience is not `AUTH0_AUDIENCE`.
- **Tools refuse with a missing-scope message**: the permission is not assigned to
  your user, or RBAC is not enabled on the API.
- **The client cannot register or log in**: check that Dynamic Application
  Registration is on and the login connection is domain-level.
- **`apply_update` fails with `Approved update could not be recorded in Git.`**:
  before modifying any file, the Git recorder checks that the workspace is the root
  of a Git repository (`git rev-parse --show-toplevel`), that `user.name` and
  `user.email` are configured, and that `memory/<page_id>` is already tracked and
  has no uncommitted changes (`git ls-files --error-unmatch`). Initialize Git,
  configure the author identity, and commit the initial Memory Page before calling
  `apply_update`.
- **No refresh token**: confirm Allow Offline Access on the API; some clients may
  also need `offline_access` in their requested scopes.

The [Postman guide](auth0-postman.md) remains available as an optional
smoke test that does not need a Memory Client.
