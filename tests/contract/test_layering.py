"""Hexagonal dependency rule: imports may only point inwards.

    entrypoints / bootstrap  ->  infrastructure  ->  application  ->  domain

The domain is also kept free of I/O: besides its own package it may import only the standard
library and pydantic. Checked with ``ast``, so a wrong import fails CI without running any code.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PACKAGE = "real_estate_price_tracking_systems"
PKG_DIR = Path(__file__).resolve().parents[2] / "src" / PACKAGE

FORBIDDEN: dict[str, tuple[str, ...]] = {
    "domain": ("application", "infrastructure", "entrypoints", "bootstrap"),
    "application": ("infrastructure", "entrypoints", "bootstrap"),
    "infrastructure": ("entrypoints", "bootstrap"),
}
DOMAIN_THIRD_PARTY = {"pydantic", "pydantic_core", "typing_extensions"}


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path, root: Path) -> set[str]:
    """Absolute names of every module imported by ``path``; relative imports are resolved."""
    module = _module_name(path, root)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - (node.level - 1)])
                base = f"{base}.{node.module}" if node.module else base
            if node.module:
                names.add(base)
            else:  # "from .. import infrastructure": the names are the modules
                names |= {f"{base}.{alias.name}" for alias in node.names}
    return names


def violations(root: Path, layer: str) -> list[str]:
    found: list[str] = []
    for path in sorted((root / layer).rglob("*.py")):
        for name in sorted(_imports(path, root)):
            parts = name.split(".")
            where = path.relative_to(root).as_posix()
            if parts[0] == root.name:
                if len(parts) > 1 and parts[1] in FORBIDDEN[layer]:
                    found.append(f"{where} imports {name}")
            elif (
                layer == "domain"
                and parts[0] not in sys.stdlib_module_names
                and parts[0] not in DOMAIN_THIRD_PARTY
            ):
                found.append(f"{where} imports third-party {name}")
    return found


def test_package_layout_is_where_the_test_looks() -> None:
    # Guards against the rule passing vacuously after a rename.
    assert (PKG_DIR / "domain" / "__init__.py").is_file()


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layer_only_imports_inwards(layer: str) -> None:
    found = violations(PKG_DIR, layer)
    assert not found, "\n".join(found)


def test_checker_catches_absolute_relative_and_io_imports(tmp_path: Path) -> None:
    root = tmp_path / PACKAGE
    (root / "domain" / "sub").mkdir(parents=True)
    (root / "domain" / "__init__.py").write_text("")
    (root / "domain" / "sub" / "bad.py").write_text(
        f"import {PACKAGE}.infrastructure.config\n"
        "from ...application import ports\n"
        "import psycopg\n"
        "import json\n"
        "from pydantic import BaseModel\n"
        "from . import sibling\n"
        "from ... import bootstrap\n",
        encoding="utf-8",
    )
    found = violations(root, "domain")
    assert sorted(found) == sorted(
        [
            f"domain/sub/bad.py imports {PACKAGE}.application",
            f"domain/sub/bad.py imports {PACKAGE}.bootstrap",
            f"domain/sub/bad.py imports {PACKAGE}.infrastructure.config",
            "domain/sub/bad.py imports third-party psycopg",
        ]
    )
