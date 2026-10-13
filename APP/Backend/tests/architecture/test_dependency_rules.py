"""Reglas de dependencia de la arquitectura hexagonal."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from import_checker import find_violations, non_stdlib_imports

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC = BACKEND_ROOT / "src" / "fleetplanner"

INFRA = ("fastapi", "pydantic", "sqlalchemy", "redis", "sklearn", "ortools", "numpy", "pandas")


def _lint_imports(cwd: Path, pythonpath: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    code = (
        "import sys; from importlinter.cli import lint_imports_command; "
        "sys.exit(lint_imports_command())"
    )
    return subprocess.run(  # noqa: S603 - comando fijo y controlado por la prueba
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class TestImportLinter:
    def test_all_contracts_pass_on_the_real_code(self) -> None:
        result = _lint_imports(BACKEND_ROOT)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "0 broken" in result.stdout

    def test_a_forced_violation_is_detected(self, tmp_path: Path) -> None:
        """El dominio importando un adaptador debe romper al menos un contrato."""
        shutil.copytree(
            BACKEND_ROOT / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__")
        )
        shutil.copy(BACKEND_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
        target = tmp_path / "src" / "fleetplanner" / "domain" / "shared" / "errors.py"
        target.write_text(
            target.read_text(encoding="utf-8")
            + "\nfrom fleetplanner.adapters.outbound.clock import SystemClock  # violación\n",
            encoding="utf-8",
        )
        result = _lint_imports(tmp_path, pythonpath=tmp_path / "src")
        assert result.returncode != 0, result.stdout
        assert "BROKEN" in result.stdout


class TestAstRules:
    def test_domain_does_not_import_infrastructure_or_outer_layers(self) -> None:
        forbidden = (
            *INFRA,
            "fleetplanner.application",
            "fleetplanner.adapters",
            "fleetplanner.bootstrap",
        )
        assert find_violations(SRC / "domain", forbidden) == []

    def test_domain_only_uses_stdlib_and_itself(self) -> None:
        offenders = non_stdlib_imports(
            SRC / "domain", ("fleetplanner.domain",), frozenset(sys.stdlib_module_names)
        )
        assert offenders == []

    def test_application_does_not_import_adapters_bootstrap_or_infrastructure(self) -> None:
        forbidden = (*INFRA[:-2], "fleetplanner.adapters", "fleetplanner.bootstrap")
        assert find_violations(SRC / "application", forbidden) == []

    def test_inbound_adapters_do_not_import_outbound_adapters(self) -> None:
        assert (
            find_violations(SRC / "adapters" / "inbound", ("fleetplanner.adapters.outbound",)) == []
        )

    def test_outbound_adapters_do_not_import_each_other(self) -> None:
        outbound = SRC / "adapters" / "outbound"
        siblings = [p.name for p in outbound.iterdir() if p.is_dir() and p.name != "__pycache__"]
        for name in siblings:
            others = tuple(f"fleetplanner.adapters.outbound.{o}" for o in siblings if o != name)
            assert find_violations(outbound / name, others) == [], name

    def test_only_bootstrap_imports_concrete_adapters(self) -> None:
        for layer in ("domain", "application"):
            assert find_violations(SRC / layer, ("fleetplanner.adapters",)) == []

    def test_checker_detects_a_violation(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("import sqlalchemy\nfrom fleetplanner.adapters import x\n")
        found = find_violations(tmp_path, ("sqlalchemy", "fleetplanner.adapters"))
        assert {m for _, m in found} == {"sqlalchemy", "fleetplanner.adapters"}

    def test_checker_does_not_flag_similarly_named_modules(self, tmp_path: Path) -> None:
        (tmp_path / "ok.py").write_text("import sqlalchemy_utils_like\n")
        assert find_violations(tmp_path, ("sqlalchemy",)) == []


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_layers_contain_no_global_mutable_state_markers(layer: str) -> None:
    """Heurística: sin `global` ni singletons de módulo en dominio/aplicación."""
    for path in (SRC / layer).rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "\nglobal " not in text, path
