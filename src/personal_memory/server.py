"""Run the read-only Personal Memory MCP server with Auth0 access tokens."""

import argparse
import asyncio
import os
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

import jwt
from dotenv import load_dotenv
from mcp.server.auth.provider import AccessToken, TokenVerifier

from personal_memory.mcp import create_mcp_server


class JwtTokenVerifier(TokenVerifier):
    """Verify Auth0 RS256 tokens against cached, rotating tenant signing keys."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        resource: str,
        allowed_subjects: frozenset[str],
    ) -> None:
        parsed = urlsplit(issuer)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Auth0 issuer must be an HTTPS tenant origin.")
        if not audience.strip():
            raise ValueError("Auth0 audience must not be blank.")
        if not allowed_subjects or any(not subject.strip() for subject in allowed_subjects):
            raise ValueError("At least one non-empty allowed subject is required.")
        self._issuer = issuer.rstrip("/") + "/"
        self._audience = audience
        self._resource = resource
        self._allowed_subjects = allowed_subjects
        self._jwks = jwt.PyJWKClient(
            f"{self._issuer}.well-known/jwks.json", timeout=5
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = await asyncio.to_thread(
                self._jwks.get_signing_key_from_jwt, token
            )
            claims = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            return None

        subject = claims.get("sub")
        if not isinstance(subject, str) or subject not in self._allowed_subjects:
            return None
        scope = claims.get("scope", "")
        client_id = claims.get("client_id", claims.get("azp", subject))
        expires_at = claims["exp"]
        if (
            not isinstance(scope, str)
            or not isinstance(client_id, str) or not client_id
            or type(expires_at) is not int
        ):
            return None
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scope.split(),
            expires_at=expires_at,
            resource=self._resource,
            subject=subject,
            claims={"iss": self._issuer},
        )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace_path", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--issuer", default=os.getenv("AUTH0_ISSUER"))
    parser.add_argument("--audience", default=os.getenv("AUTH0_AUDIENCE"))
    parser.add_argument("--resource-url", default=os.getenv("MCP_RESOURCE_URL"))
    parser.add_argument(
        "--allowed-subject", action="append",
        help="Allowed token sub; repeat for multiple users or test applications.",
    )
    args = parser.parse_args(argv)
    for name in ("issuer", "audience"):
        if not getattr(args, name) or not getattr(args, name).strip():
            parser.error(f"--{name} or AUTH0_{name.upper()} is required")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    subjects = args.allowed_subject
    if subjects is None:
        subjects = os.getenv("AUTH0_ALLOWED_SUBJECTS", "").split(",")
    args.allowed_subjects = frozenset(s.strip() for s in subjects if s.strip())
    if not args.allowed_subjects:
        parser.error("--allowed-subject or AUTH0_ALLOWED_SUBJECTS is required")
    args.resource_url = args.resource_url or f"http://127.0.0.1:{args.port}/mcp"
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        verifier = JwtTokenVerifier(
            issuer=args.issuer,
            audience=args.audience,
            resource=args.resource_url,
            allowed_subjects=args.allowed_subjects,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    server = create_mcp_server(
        args.workspace_path,
        token_verifier=verifier,
        issuer_url=args.issuer.rstrip("/") + "/",
        resource_server_url=args.resource_url,
        exposed_tools=frozenset({"search_memory", "read_memory"}),
    )
    server.run(transport="streamable-http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
