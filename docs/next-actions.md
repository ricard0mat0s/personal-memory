# Next action

Run the live Auth0 smoke check described in [Auth0 and Postman](auth0-postman.md)
against the disposable `smoke.md` fixture, then record the sanitized evidence in
the implementation pull request for [issue #12](https://github.com/ricard0mat0s/personal-memory/issues/12).

1. Configure the Auth0 issuer, API audience, and exact allowed subject. For the
   documented M2M test, authorize the test application for `memory:read` and use
   its issued token's subject. Keep credentials in private local configuration.
2. Follow the guide to create the disposable workspace and launch the installed
   server with an explicit bind address and port.
3. Obtain a real Auth0-issued access token in Postman. Connect over Streamable
   HTTP, confirm only the two retrieval tools are advertised, search for
   `Smoke verification`, and read `smoke.md` with the same returned Retrieval
   Request ID. Confirm the complete expected Markdown is returned.
4. Confirm the missing-token request receives HTTP 401. Add the tested revision,
   timestamp, endpoint, search/read outcomes, matching request ID, and other
   fields from the guide's evidence template to the PR, excluding credentials.

Configurable binding, startup configuration rejection, and automated real-HTTP
retrieval coverage are implemented. The automated suite uses synthetic signing
keys and is not evidence of a successful live Auth0 run. The remaining check
requires the owner's real provider configuration and token.

Use issue #12's acceptance criteria when preparing the PR, and include
`Closes #12` once the work and live verification are complete. Cross-client
certification, approved-write demonstrations, and production hosting remain
subsequent increments.
