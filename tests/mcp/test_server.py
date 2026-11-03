"""Auth0 verification with real signatures and synthetic JWKS; no network."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from personal_memory.server import JwtTokenVerifier, _parse_args

from .support import (
    RESOURCE_SERVER_URL,
)

ISSUER = "https://tenant.example.com/"
AUDIENCE = "https://memory.example.com/mcp"
SUBJECT = "test-client@clients"


@pytest.fixture
def auth0(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update(kid="test-key", use="sig", alg="RS256")
    # Keep PyJWKClient's key selection and JWT validation real; replace only I/O.
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [jwk]})
    verifier = JwtTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, resource=RESOURCE_SERVER_URL,
        allowed_subjects=frozenset({SUBJECT}),
    )

    def sign(**overrides):
        now = int(time.time())
        claims = {
            "iss": ISSUER, "aud": AUDIENCE, "sub": SUBJECT,
            "azp": "test-client", "scope": "memory:read",
            "iat": now, "exp": now + 300,
        }
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})

    return verifier, sign


@pytest.mark.anyio
async def test_valid_token_maps_verified_identity_scopes_and_expiry(auth0):
    verifier, sign = auth0
    token = await verifier.verify_token(sign())
    assert token is not None
    assert token.subject == SUBJECT
    assert token.client_id == "test-client"
    assert token.scopes == ["memory:read"]
    assert token.resource == RESOURCE_SERVER_URL
    assert token.expires_at > time.time()
    assert token.claims["iss"] == ISSUER


@pytest.mark.anyio
@pytest.mark.parametrize("overrides", [
    {"iss": "https://other.example.com/"}, {"aud": "wrong-api"},
    {"sub": "another-owner"}, {"sub": ""}, {"exp": 1}, {"exp": None},
    {"iat": int(time.time()) + 3600}, {"scope": ["memory:read"]},
    {"azp": ""},
])
async def test_refuses_invalid_claims(auth0, overrides):
    verifier, sign = auth0
    assert await verifier.verify_token(sign(**overrides)) is None


@pytest.mark.anyio
async def test_refuses_invalid_signature_and_malformed_token(auth0):
    verifier, sign = auth0
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(sign(), options={"verify_signature": False})
    forged = jwt.encode(claims, other_key, algorithm="RS256", headers={"kid": "test-key"})
    assert await verifier.verify_token(forged) is None
    assert await verifier.verify_token("malformed") is None
    unsigned = jwt.encode(claims, key="", algorithm="none", headers={"kid": "test-key"})
    assert await verifier.verify_token(unsigned) is None


@pytest.mark.anyio
async def test_refuses_unknown_key_and_jwks_outage(auth0, monkeypatch):
    verifier, sign = auth0
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": []})
    assert await verifier.verify_token(sign()) is None

    def unavailable(self):
        raise jwt.PyJWKClientConnectionError("synthetic outage")

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", unavailable)
    assert await verifier.verify_token(sign()) is None


def test_missing_auth_configuration_fails_at_startup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("AUTH0_ISSUER", "AUTH0_AUDIENCE", "AUTH0_ALLOWED_SUBJECTS"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit):
        _parse_args([str(tmp_path)])


def test_dotenv_and_command_line_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("AUTH0_ISSUER", "AUTH0_AUDIENCE", "AUTH0_ALLOWED_SUBJECTS", "MCP_RESOURCE_URL"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        f"AUTH0_ISSUER={ISSUER}\nAUTH0_AUDIENCE={AUDIENCE}\n"
        f"AUTH0_ALLOWED_SUBJECTS={SUBJECT}\n"
    )
    args = _parse_args([str(tmp_path), "--port", "9000", "--allowed-subject", "owner"])
    assert args.issuer == ISSUER
    assert args.resource_url == "http://127.0.0.1:9000/mcp"
    assert args.allowed_subjects == frozenset({"owner"})


@pytest.mark.parametrize("issuer", ["http://tenant.example.com/", "https://tenant.example.com/path"])
def test_refuses_insecure_or_invalid_issuer(issuer):
    with pytest.raises(ValueError, match="HTTPS tenant origin"):
        JwtTokenVerifier(issuer=issuer, audience=AUDIENCE, resource=RESOURCE_SERVER_URL,
                         allowed_subjects=frozenset({SUBJECT}))
