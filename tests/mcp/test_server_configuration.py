"""Reject invalid security configuration through the installed launcher."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


def assert_startup_rejected(
    workspace: Path, environment_changes: dict[str, str | None],
    arguments: tuple[str, ...] = (),
) -> str:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {
        **os.environ,
        "AUTH0_ISSUER": "https://tenant.invalid/",
        "AUTH0_AUDIENCE": "startup-test-api",
        "AUTH0_ALLOWED_SUBJECTS": "test-owner",
        "MCP_RESOURCE_URL": f"http://127.0.0.1:{port}/mcp",
        "MCP_HOST": "127.0.0.1",
    }
    for name, value in environment_changes.items():
        if value is None:
            environment.pop(name, None)
        else:
            environment[name] = value
    launcher_name = "personal-memory-server.exe" if os.name == "nt" else "personal-memory-server"
    launcher = Path(sys.executable).with_name(launcher_name)
    with (workspace / "startup.log").open("w+") as output:
        process = subprocess.Popen(
            [str(launcher), str(workspace), "--port", str(port), *arguments],
            cwd=workspace, env=environment, stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                        raise AssertionError("Invalid configuration opened the HTTP listener")
                except OSError:
                    time.sleep(0.02)
            assert process.poll() is not None, "Invalid configuration did not stop startup"
            assert process.returncode != 0
            output.seek(0)
            message = output.read()
            assert "Uvicorn running" not in message
            assert "Traceback" not in message
            return message
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def test_launcher_refuses_resource_url_with_credentials(tmp_path: Path) -> None:
    message = assert_startup_rejected(tmp_path, {
        "MCP_RESOURCE_URL": "http://user:password@127.0.0.1/mcp",
    })
    assert "resource" in message.lower()


@pytest.mark.parametrize("name", ["AUTH0_ISSUER", "AUTH0_AUDIENCE", "AUTH0_ALLOWED_SUBJECTS"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_launcher_refuses_missing_security_settings(
    tmp_path: Path, name: str, value: str | None,
) -> None:
    message = assert_startup_rejected(tmp_path, {name: value})
    assert name in message


@pytest.mark.parametrize("issuer", [
    "not-a-url", "http://tenant.invalid/", "https://tenant.invalid/path",
    "https://tenant.invalid:bad/", "https://bad host/",
])
def test_launcher_refuses_invalid_issuer(tmp_path: Path, issuer: str) -> None:
    assert_startup_rejected(tmp_path, {"AUTH0_ISSUER": issuer})


@pytest.mark.parametrize("resource", [
    "", "   ", "not-a-url", "file:///tmp/mcp", "http:///mcp",
    "http://127.0.0.1:bad/mcp", "http://127.0.0.1:65536/mcp",
    "http://127.0.0.1/mcp?token=secret", "http://127.0.0.1/mcp#fragment",
])
def test_launcher_refuses_invalid_resource_url(tmp_path: Path, resource: str) -> None:
    message = assert_startup_rejected(tmp_path, {"MCP_RESOURCE_URL": resource})
    assert "MCP_RESOURCE_URL" in message


@pytest.mark.parametrize("port", ["0", "-1", "65536", "not-a-port"])
def test_launcher_refuses_invalid_port(tmp_path: Path, port: str) -> None:
    message = assert_startup_rejected(tmp_path, {}, ("--port", port))
    assert "--port" in message
