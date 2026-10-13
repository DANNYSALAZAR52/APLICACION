"""Contrato reutilizable de `FleetMixSolverPort`.

Cualquier adaptador (real o simulado) debe pasar estas pruebas. Se parametriza por fábrica para
que un futuro adaptador se agregue sin tocar los casos.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from fleetplanner.adapters.outbound.solver import OrToolsFleetMixSolver
from fleetplanner.application.ports.outbound.capacity import FleetMixSolverPort
from fleetplanner.domain.capacity.fleet_mix import FleetMixProblem, SolverStatus

SOLVER_FACTORIES: list[Callable[[], FleetMixSolverPort]] = [OrToolsFleetMixSolver]


def _problem(required: dict[str, float] | None = None) -> FleetMixProblem:
    """Corredor R1 con tipos A (8 t, barato) y B (20 t, un solo vehículo cubre 20 t)."""
    return FleetMixProblem(
        corridors=("R1",),
        vehicle_types=("A", "B"),
        required_t=required or {"R1": 20.0},
        capacity_t={("R1", "A"): 8.0, ("R1", "B"): 20.0},
        fixed_cost_per_day={"A": 100.0, "B": 250.0},
        variable_cost_per_day={("R1", "A"): 10.0, ("R1", "B"): 20.0},
    )


@pytest.fixture(params=SOLVER_FACTORIES, ids=lambda f: f.__name__)
def solver(request: pytest.FixtureRequest) -> FleetMixSolverPort:
    return request.param()


def test_finds_the_cheapest_feasible_mix_and_reports_optimal(solver: FleetMixSolverPort) -> None:
    # 3·A = 3·100 + 3·10 = 330 ; 1·B = 250 + 20 = 270 → B
    solution = solver.solve(_problem(), time_limit_s=10)
    assert solution.status is SolverStatus.OPTIMAL
    assert solution.fleet_by_type == {"B": 1}
    assert solution.assignments == {("R1", "B"): 1}
    assert solution.total_cost_per_day == pytest.approx(270.0)


def test_solution_satisfies_capacity_constraint(solver: FleetMixSolverPort) -> None:
    problem = _problem({"R1": 50.0})
    solution = solver.solve(problem, time_limit_s=10)
    assert solution.status is SolverStatus.OPTIMAL
    delivered = sum(problem.capacity_t[pair] * n for pair, n in solution.assignments.items())
    assert delivered >= 50.0
    for vehicle_type, fleet in solution.fleet_by_type.items():
        used = sum(n for (_, t), n in solution.assignments.items() if t == vehicle_type)
        assert fleet >= used


def test_shared_type_fleet_covers_all_corridors(solver: FleetMixSolverPort) -> None:
    problem = FleetMixProblem(
        corridors=("R1", "R2"),
        vehicle_types=("A",),
        required_t={"R1": 10.0, "R2": 10.0},
        capacity_t={("R1", "A"): 8.0, ("R2", "A"): 8.0},
        fixed_cost_per_day={"A": 100.0},
        variable_cost_per_day={("R1", "A"): 1.0, ("R2", "A"): 1.0},
    )
    solution = solver.solve(problem, time_limit_s=10)
    assert solution.status is SolverStatus.OPTIMAL
    assert solution.fleet_by_type == {"A": 4}  # 2 por corredor


def test_corridor_without_compatible_type_is_infeasible_not_optimal(
    solver: FleetMixSolverPort,
) -> None:
    problem = FleetMixProblem(
        corridors=("R1", "R2"),
        vehicle_types=("A",),
        required_t={"R1": 10.0, "R2": 10.0},
        capacity_t={("R1", "A"): 8.0},
        fixed_cost_per_day={"A": 100.0},
        variable_cost_per_day={("R1", "A"): 1.0},
    )
    solution = solver.solve(problem, time_limit_s=10)
    assert solution.status is SolverStatus.INFEASIBLE
    assert "R2" in solution.message
    assert not solution.has_solution
    assert solution.fleet_by_type == {}


def test_zero_demand_needs_no_vehicles(solver: FleetMixSolverPort) -> None:
    solution = solver.solve(_problem({"R1": 0.0}), time_limit_s=10)
    assert solution.status is SolverStatus.OPTIMAL
    assert solution.total_vehicles == 0
    assert solution.total_cost_per_day == pytest.approx(0.0)
