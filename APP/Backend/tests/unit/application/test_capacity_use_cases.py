"""Casos de uso de capacidad con dobles de los puertos."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from builders import make_corridor, make_inputs, make_series
from fleetplanner.application.dto.capacity import CapacityInputs
from fleetplanner.application.use_cases.build_capacity_dashboard import BuildCapacityDashboard
from fleetplanner.application.use_cases.capacity_common import prepare_capacity
from fleetplanner.application.use_cases.optimize_fleet_mix import OptimizeFleetMix
from fleetplanner.application.use_cases.project_five_years import ProjectFiveYears
from fleetplanner.application.use_cases.run_capacity_analysis import RunCapacityAnalysis
from fleetplanner.application.use_cases.simulate_monte_carlo import SimulateMonteCarlo
from fleetplanner.domain.capacity.fleet_mix import FleetMixProblem, FleetMixSolution, SolverStatus
from fleetplanner.domain.capacity.models import CompatibilityMatrix
from fleetplanner.domain.capacity.results import (
    ALGORITHM_VERSION,
    CapacityMethod,
    CapacityResult,
)
from fleetplanner.domain.shared.errors import InsufficientDataError, InvalidValueError

NOW = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)


class FakeClock:
    def now(self) -> datetime:
        return NOW


class FakeReader:
    def __init__(self, inputs: CapacityInputs) -> None:
        self._inputs = inputs
        self.loads = 0

    def load(self) -> CapacityInputs:
        self.loads += 1
        return self._inputs


class FakeWriter:
    def __init__(self) -> None:
        self.saved: list[CapacityResult] = []

    def save_all(self, results: Sequence[CapacityResult]) -> None:
        self.saved.extend(results)


class FakeSolver:
    def __init__(self, solution: FleetMixSolution) -> None:
        self._solution = solution
        self.problems: list[FleetMixProblem] = []
        self.time_limits: list[float] = []

    def solve(self, problem: FleetMixProblem, time_limit_s: float) -> FleetMixSolution:
        self.problems.append(problem)
        self.time_limits.append(time_limit_s)
        return self._solution


OPTIMAL = FleetMixSolution(
    SolverStatus.OPTIMAL,
    assignments={("R1", "X"): 3, ("R2", "Y"): 1},
    fleet_by_type={"X": 3, "Y": 1},
    total_cost_per_day=1234.5,
)


def _dashboard(
    inputs: CapacityInputs, solution: FleetMixSolution = OPTIMAL
) -> tuple[BuildCapacityDashboard, FakeWriter, FakeReader, FakeSolver]:
    reader, writer, clock, solver = (
        FakeReader(inputs),
        FakeWriter(),
        FakeClock(),
        FakeSolver(solution),
    )
    use_case = BuildCapacityDashboard(
        reader,
        RunCapacityAnalysis(reader, writer, clock),
        ProjectFiveYears(reader, writer, clock),
        SimulateMonteCarlo(reader, writer, clock),
        OptimizeFleetMix(reader, solver, writer, clock),
        clock,
    )
    return use_case, writer, reader, solver


class TestPrepare:
    def test_corridor_without_enough_data_is_excluded_with_warning(self) -> None:
        inputs = make_inputs({"R1": [19.0, 21.0] * 15, "R2": [5.0]})
        prepared = prepare_capacity(inputs)
        assert [c.code for c in prepared.corridors] == ["R1"]
        assert "R2" in prepared.excluded
        assert any("R2" in w for w in prepared.warnings)

    def test_no_usable_corridor_is_an_error(self) -> None:
        with pytest.raises(InsufficientDataError, match="Ningún corredor"):
            prepare_capacity(make_inputs({"R1": [1.0], "R2": [1.0]}))

    def test_assigned_type_must_be_compatible(self) -> None:
        inputs = make_inputs()
        broken = CapacityInputs(
            vehicle_types=inputs.vehicle_types,
            corridors=inputs.corridors,
            compatibility=CompatibilityMatrix.of([("R2", "Y")]),  # R1→X no es compatible
            demand=inputs.demand,
            current_fleet=inputs.current_fleet,
            parameters=inputs.parameters,
            scenarios=inputs.scenarios,
        )
        with pytest.raises(InvalidValueError, match="no está marcada como compatible"):
            prepare_capacity(broken)

    def test_unknown_vehicle_type_is_an_error(self) -> None:
        inputs = make_inputs()
        broken = CapacityInputs(
            vehicle_types={"X": inputs.vehicle_types["X"]},
            corridors=inputs.corridors,  # R2 usa Y, que no existe
            compatibility=inputs.compatibility,
            demand=inputs.demand,
            current_fleet=inputs.current_fleet,
            parameters=inputs.parameters,
            scenarios=inputs.scenarios,
        )
        with pytest.raises(InvalidValueError, match="no existe"):
            prepare_capacity(broken)


class TestRunCapacityAnalysis:
    def test_calculates_and_persists_with_provenance(self) -> None:
        inputs = make_inputs()
        writer = FakeWriter()
        analysis = RunCapacityAnalysis(FakeReader(inputs), writer, FakeClock()).execute()

        # Demanda de diseño R1: valores 19/21 → P90 = 21 ; capacidad 8 t/veh → 2.625 veh
        # R2: 9.5/10.5 → P90 = 10.5 ; cap Y = 20·0.8·2·0.5 = 16 → 0.65625 veh
        requirement = analysis.balance.requirement
        assert requirement.fractional_by_type["X"] == pytest.approx(21 / 8)
        assert requirement.required_by_type["X"] == 3  # 2.625 · 1.08 = 2.835 → 3
        assert requirement.required_by_type["Y"] == 1

        methods = {r.method for r in writer.saved}
        assert methods == {
            CapacityMethod.BALANCE,
            CapacityMethod.LEAN,
            CapacityMethod.OWN_VS_THIRD_PARTY,
        }
        balance_x = next(
            r for r in writer.saved if r.method is CapacityMethod.BALANCE and r.vehicle_type == "X"
        )
        assert balance_x.run_at == NOW
        assert balance_x.algorithm_version == ALGORITHM_VERSION
        assert balance_x.parameters["reserve"] == pytest.approx(0.08)
        assert balance_x.parameters["valid_days_by_corridor"] == {"R1": 30, "R2": 30}

    def test_missing_days_reduce_valid_days_and_are_reported(self) -> None:
        values: list[float | None] = [19.0, None, 21.0, None] * 8
        inputs = make_inputs({"R1": values, "R2": [9.5, 10.5] * 16})
        writer = FakeWriter()
        RunCapacityAnalysis(FakeReader(inputs), writer, FakeClock()).execute()
        balance = next(r for r in writer.saved if r.method is CapacityMethod.BALANCE)
        valid = balance.parameters["valid_days_by_corridor"]
        assert isinstance(valid, dict)
        assert valid["R1"] == 16  # 32 días de calendario, la mitad sin dato

    def test_kpis_are_available_but_otif_is_not(self) -> None:
        analysis = RunCapacityAnalysis(
            FakeReader(make_inputs()), FakeWriter(), FakeClock()
        ).execute()
        assert analysis.balance.kpis.otif is None
        assert analysis.balance.kpis.daily_cost > 0


class TestProjectionAndMonteCarlo:
    def test_projection_persists_every_scenario_year_and_type(self) -> None:
        writer = FakeWriter()
        projections = ProjectFiveYears(FakeReader(make_inputs()), writer, FakeClock()).execute()
        assert [p.scenario for p in projections] == ["base", "optimista"]
        rows = [r for r in writer.saved if r.method is CapacityMethod.PROJECTION]
        assert len(rows) == 2 * 5 * 2  # escenarios · años · tipos
        assert {r.year for r in rows} == {2027, 2028, 2029, 2030, 2031}
        assert {r.parameters["scenario"] for r in rows} == {"base", "optimista"}

    def test_base_year_defaults_to_clock_year(self) -> None:
        from dataclasses import replace

        inputs = make_inputs()
        inputs = replace(inputs, parameters=replace(inputs.parameters, base_year=None))
        projections = ProjectFiveYears(FakeReader(inputs), FakeWriter(), FakeClock()).execute()
        assert projections[0].years[0].year == NOW.year + 1

    def test_monte_carlo_stores_seed_and_percentiles(self) -> None:
        writer = FakeWriter()
        result = SimulateMonteCarlo(FakeReader(make_inputs()), writer, FakeClock()).execute()
        assert result.seed == 7
        row = next(r for r in writer.saved if r.method is CapacityMethod.MONTE_CARLO)
        assert row.parameters["seed"] == 7
        assert row.parameters["days"] == 200
        assert row.required_fleet == row.parameters["percentiles"]["p95"]  # type: ignore[index]


class TestOptimizeFleetMix:
    def test_builds_problem_with_reserve_and_passes_time_limit(self) -> None:
        inputs = make_inputs()
        writer, solver = FakeWriter(), FakeSolver(OPTIMAL)
        solution = OptimizeFleetMix(FakeReader(inputs), solver, writer, FakeClock()).execute()
        assert solution is OPTIMAL
        problem = solver.problems[0]
        assert problem.required_t["R1"] == pytest.approx(21.0 * 1.08)
        assert ("R1", "Y") in problem.capacity_t  # compatibilidad respetada
        assert ("R2", "X") not in problem.capacity_t
        assert solver.time_limits == [5.0]
        rows = [r for r in writer.saved if r.method is CapacityMethod.MIX_OPTIMIZATION]
        assert {r.vehicle_type: r.required_fleet for r in rows} == {"X": 3, "Y": 1}
        assert all(r.parameters["solver_status"] == "optimal" for r in rows)

    def test_infeasible_solution_is_not_persisted(self) -> None:
        writer = FakeWriter()
        solver = FakeSolver(FleetMixSolution(SolverStatus.INFEASIBLE, message="sin tipo"))
        solution = OptimizeFleetMix(
            FakeReader(make_inputs()), solver, writer, FakeClock()
        ).execute()
        assert solution.status is SolverStatus.INFEASIBLE
        assert writer.saved == []


class TestDashboard:
    def test_loads_inputs_once_and_consolidates_everything(self) -> None:
        use_case, writer, reader, _ = _dashboard(make_inputs())
        dashboard = use_case.execute()
        assert reader.loads == 1
        assert dashboard.run_at == NOW
        assert dashboard.base_year == 2026
        assert dashboard.balance.requirement.total_required == 4
        assert dashboard.mix.status is SolverStatus.OPTIMAL
        assert {r.method for r in writer.saved} == set(CapacityMethod)

    def test_ml_forecast_is_declared_unavailable(self) -> None:
        dashboard = _dashboard(make_inputs())[0].execute()
        assert dashboard.ml_forecast_available is False
        assert any("ML no disponible" in w for w in dashboard.warnings)

    def test_non_optimal_solver_is_flagged_and_never_called_optimal(self) -> None:
        feasible = FleetMixSolution(
            SolverStatus.FEASIBLE,
            fleet_by_type={"X": 3, "Y": 1},
            total_cost_per_day=1.0,
            message="Sin prueba de optimalidad.",
        )
        dashboard = _dashboard(make_inputs(), feasible)[0].execute()
        assert any("'feasible'" in w for w in dashboard.warnings)
        mix_findings = [f for f in dashboard.findings if f.startswith("Mix de flota")]
        assert mix_findings == ["Mix de flota (feasible): 4 vehículos."]

    def test_deficit_and_first_deficit_year_appear_in_findings(self) -> None:
        dashboard = _dashboard(make_inputs(current_fleet={"X": 1, "Y": 0}))[0].execute()
        assert any(f.startswith("Déficit actual de") and "tipo X" in f for f in dashboard.findings)
        assert any("deja de alcanzar" in f for f in dashboard.findings)

    def test_findings_end_with_recommendation_disclaimer(self) -> None:
        dashboard = _dashboard(make_inputs())[0].execute()
        assert "no disparan compras ni contratos" in dashboard.findings[-1]

    def test_corridor_missing_data_is_reported_as_warning(self) -> None:
        inputs = make_inputs({"R1": [19.0, 21.0] * 15, "R2": [3.0]})
        dashboard = _dashboard(inputs)[0].execute()
        assert any("R2 excluido" in w for w in dashboard.warnings)
        assert dashboard.balance.requirement.required_by_type.keys() == {"X"}


def test_make_series_and_corridor_helpers_are_consistent() -> None:
    series = make_series("R1", [1.0, None, 3.0])
    assert len(series.observations) == 2
    assert make_corridor("Z").code == "Z"
