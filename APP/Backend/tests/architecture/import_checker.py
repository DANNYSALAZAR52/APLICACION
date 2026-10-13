"""Chequeo de imports por AST, independiente de import-linter (segunda línea de defensa)."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path


def imported_modules(path: Path) -> set[str]:
    """Nombres absolutos de los módulos importados en un archivo."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def find_violations(package_dir: Path, forbidden_prefixes: Iterable[str]) -> list[tuple[str, str]]:
    """Devuelve (archivo, módulo) por cada import cuyo nombre empiece por un prefijo prohibido."""
    prefixes = tuple(forbidden_prefixes)
    violations: list[tuple[str, str]] = []
    for path in sorted(package_dir.rglob("*.py")):
        for module in imported_modules(path):
            if any(module == p or module.startswith(p + ".") for p in prefixes):
                violations.append((str(path.relative_to(package_dir)), module))
    return violations


def non_stdlib_imports(
    package_dir: Path, allowed_prefixes: Iterable[str], stdlib: frozenset[str]
) -> list[tuple[str, str]]:
    """Imports que no son librería estándar ni pertenecen a los prefijos permitidos."""
    allowed = tuple(allowed_prefixes)
    offenders: list[tuple[str, str]] = []
    for path in sorted(package_dir.rglob("*.py")):
        for module in imported_modules(path):
            top = module.split(".")[0]
            if top in stdlib or any(module == a or module.startswith(a + ".") for a in allowed):
                continue
            offenders.append((str(path.relative_to(package_dir)), module))
    return offenders
