"""Traducción de estados del solver (sin depender de tiempos reales).

Un límite de tiempo real no se puede provocar de forma determinista, así que se prueba la
traducción con dobles. Esto verifica el mapeo, NO el comportamiento temporal real de SCIP.
"""

from __future__ import annotations

from typing import Any

from ortools.linear_solver import pywraplp

from fleetplanner.adapters.outbound.solver.ortools_fleet_mix import OrToolsFleetMixSolver
from fleetplanner.domain.capacity.fleet_mix import SolverStatus


class _Var:
    def __init__(self, value: float) -> None:
        self._value = value

    def solution_value(self) -> float:
        return self._value


class _Objective:
    def Value(self) -> float:  # noqa: N802 - nombre impuesto por OR-Tools
        return 123.0


class _Solver:
    def Objective(self) -> _Objective:  # noqa: N802
        return _Objective()


def _map(raw: int, x: dict[Any, Any] | None = None, y: dict[Any, Any] | None = None):  # type: ignore[no-untyped-def]
    return OrToolsFleetMixSolver._to_solution(_Solver(), raw, x or {}, y or {}, 5.0)  # type: ignore[arg-type]


def test_not_solved_is_time_limit_without_solution() -> None:
    solution = _map(pywraplp.Solver.NOT_SOLVED)
    assert solution.status is SolverStatus.TIME_LIMIT
    assert not solution.has_solution


def test_feasible_is_never_reported_as_optimal() -> None:
    solution = _map(pywraplp.Solver.FEASIBLE, {("R1", "A"): _Var(2.0)}, {"A": _Var(2.0)})
    assert solution.status is SolverStatus.FEASIBLE
    assert solution.status is not SolverStatus.OPTIMAL
    assert solution.fleet_by_type == {"A": 2}
    assert "sin prueba de optimalidad" in solution.message


def test_optimal_is_reported_when_proven() -> None:
    solution = _map(pywraplp.Solver.OPTIMAL, {("R1", "A"): _Var(2.0)}, {"A": _Var(2.0)})
    assert solution.status is SolverStatus.OPTIMAL
    assert solution.total_cost_per_day == 123.0


def test_infeasible_and_unknown_states() -> None:
    assert _map(pywraplp.Solver.INFEASIBLE).status is SolverStatus.INFEASIBLE
    assert _map(pywraplp.Solver.ABNORMAL).status is SolverStatus.ERROR
