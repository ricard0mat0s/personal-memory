"""Tool-level OAuth scope authorization and protected-resource scope metadata."""

from collections.abc import Sequence
from typing import Any

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.routes import create_protected_resource_routes
from mcp.server.mcpserver.exceptions import ToolError
from starlette.applications import Starlette
from starlette.routing import Route

DEFAULT_READ_SCOPE = "memory:read"
DEFAULT_WRITE_SCOPE = "memory:write"


def validate_scopes(read_scope: str, write_scope: str) -> tuple[str, str]:
    """Ensure read and write scope names are non-empty, trimmed, and distinct."""
    configured_scopes = (read_scope, write_scope)
    if (
        any(
            not isinstance(scope, str)
            or not scope
            or scope != scope.strip()
            for scope in configured_scopes
        )
        or read_scope == write_scope
    ):
        raise ValueError(
            "read_scope and write_scope must be distinct non-empty strings."
        )
    return configured_scopes


def require_scope(scope: str) -> AccessToken:
    """Require an authenticated access token carrying the given scope."""
    access_token = get_access_token()
    if access_token is None:
        raise ToolError("Authentication is required.")
    if scope not in access_token.scopes:
        raise ToolError(f"The {scope!r} scope is required.")
    return access_token


class ScopeAdvertisingServer(MCPServer):
    """MCPServer whose resource metadata advertises scopes it does not require.

    The SDK derives the metadata's ``scopes_supported`` from
    ``AuthSettings.required_scopes``, which the transport also enforces on every
    request. Each tool checks its own scope, so a read-only token must still be
    able to connect; only the advertisement is replaced here.
    """

    def __init__(
        self,
        *args: Any,
        advertised_scopes: Sequence[str],
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._advertised_scopes = list(advertised_scopes)

    def streamable_http_app(  # type: ignore[override]
        self, *args: Any, **kwargs: Any
    ) -> Starlette:
        app = super().streamable_http_app(*args, **kwargs)
        auth = self.settings.auth
        if auth is None or auth.resource_server_url is None:
            return app
        replacements = {
            route.path: route
            for route in create_protected_resource_routes(
                resource_url=auth.resource_server_url,
                authorization_servers=[auth.issuer_url],
                scopes_supported=self._advertised_scopes,
            )
        }
        routes = app.router.routes
        for index, route in enumerate(routes):
            if isinstance(route, Route) and route.path in replacements:
                routes[index] = replacements.pop(route.path)
        return app
