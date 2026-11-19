"""Verify module dependency boundaries across personal_memory."""

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "personal_memory"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def _package_imports(package_dir: Path) -> set[str]:
    imports: set[str] = set()
    for file_path in sorted(package_dir.rglob("*.py")):
        imports |= _imported_modules(file_path)
    return imports


def _has_prefix(imports: set[str], prefixes: tuple[str, ...]) -> set[str]:
    return {
        name
        for name in imports
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)
    }


def test_workspace_has_no_mcp_git_server_or_auth_dependencies() -> None:
    imports = _package_imports(SOURCE_ROOT / "workspace")
    forbidden = _has_prefix(
        imports,
        (
            "personal_memory.mcp",
            "personal_memory.git",
            "personal_memory.server",
            "mcp",
            "jwt",
            "auth0",
            "starlette",
            "pydantic",
        ),
    )
    assert forbidden == set()


def test_git_has_no_workspace_mcp_server_or_auth_dependencies() -> None:
    imports = _imported_modules(SOURCE_ROOT / "git.py")
    forbidden = _has_prefix(
        imports,
        (
            "personal_memory.workspace",
            "personal_memory.mcp",
            "personal_memory.server",
            "mcp",
            "jwt",
            "auth0",
        ),
    )
    assert forbidden == set()


def test_mcp_depends_only_on_public_workspace_and_git_boundaries() -> None:
    imports = _package_imports(SOURCE_ROOT / "mcp")
    forbidden = _has_prefix(
        imports,
        (
            "personal_memory.server",
            "jwt",
            "auth0",
        ),
    ) | {
        name
        for name in imports
        if name.startswith("personal_memory.workspace._")
    }
    assert forbidden == set()
