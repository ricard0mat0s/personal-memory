"""Local process and identity-provider fixtures for launcher contract tests."""

import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from .support import write_memory_page


@dataclass(frozen=True)
class RunningServer:
    url: str
    issuer: str
    signing_key: rsa.RSAPrivateKey

    def sign(self, **overrides: Any) -> str:
        now = int(time.time())
        claims = {
            "iss": self.issuer, "aud": "process-test-api", "sub": "test-owner",
            "azp": "process-test-client", "scope": "memory:read",
            "iat": now, "exp": now + 300,
        }
        claims.update(overrides)
        return jwt.encode(claims, self.signing_key, algorithm="RS256", headers={"kid": "test-key"})


@contextmanager
def signing_issuer(workspace: Path) -> Iterator[tuple[str, rsa.RSAPrivateKey, Path]]:
    """Serve synthetic JWKS over TLS, trusted only by this test's subprocess."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tls_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "process-test")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(tls_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([
            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
        ]), critical=False)
        .sign(tls_key, hashes.SHA256())
    )
    certificate_path = workspace / "issuer-ca.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path = workspace / "issuer-tls-key.pem"
    key_path.write_bytes(tls_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update(kid="test-key", use="sig", alg="RS256")
    body = json.dumps({"keys": [jwk]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/.well-known/jwks.json":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as issuer:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate_path, key_path)
        issuer.socket = context.wrap_socket(issuer.socket, server_side=True)
        thread = Thread(target=issuer.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"https://127.0.0.1:{issuer.server_port}/", key, certificate_path
        finally:
            issuer.shutdown()
            thread.join(timeout=5)


@contextmanager
def running_server(
    workspace: Path, *, host: str = "127.0.0.1", cli_host: str | None = None,
) -> Iterator[RunningServer]:
    with signing_issuer(workspace) as (issuer, key, certificate):
        with _server_process(workspace, issuer, key, certificate, host, cli_host) as server:
            yield server


@contextmanager
def _server_process(
    workspace: Path, issuer: str, key: rsa.RSAPrivateKey, certificate: Path,
    host: str, cli_host: str | None,
) -> Iterator[RunningServer]:
    write_memory_page(workspace)
    bind_host = cli_host or host
    with socket.socket() as listener:
        listener.bind((bind_host, 0))
        port = listener.getsockname()[1]
    url = f"http://{bind_host}:{port}/mcp"
    environment = {
        **os.environ,
        "AUTH0_ISSUER": issuer,
        "SSL_CERT_FILE": str(certificate),
        "AUTH0_AUDIENCE": "process-test-api",
        "AUTH0_ALLOWED_SUBJECTS": "test-owner",
        "MCP_RESOURCE_URL": url,
        "MCP_HOST": host,
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    launcher_name = "personal-memory-server.exe" if os.name == "nt" else "personal-memory-server"
    launcher = Path(sys.executable).with_name(launcher_name)
    with (workspace / "server.log").open("w+") as output:
        process = subprocess.Popen(
            [str(launcher), str(workspace), "--port", str(port)]
            + (["--host", cli_host] if cli_host else []),
            cwd=workspace, env=environment, stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None or time.monotonic() >= deadline:
                    output.seek(0)
                    raise AssertionError(f"Launcher failed to become ready:\n{output.read()}")
                try:
                    with socket.create_connection((bind_host, port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.05)
            yield RunningServer(url, issuer, key)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
