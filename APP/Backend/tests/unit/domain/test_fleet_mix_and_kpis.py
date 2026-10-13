"""P7 (armado del problema del mix) y P9 (KPI)."""

from __future__ import annotations

import pytest

from builders import make_corridor, make_oee, make_type, pct
from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacityCalculator
from fleetplanner.domain.capacity.fleet_mix import (
    FleetMixProblemBuilder,
    FleetMixSolution,
    SolverStatus,
)
from fleetplanner.domain.capacity.fleet_requirement import FleetRequirementCalculator
from fleetplanner.domain.capacity.kpis import CapacityKpiCalculator
from fleetplanner.domain.capacity.models import CompatibilityMatrix
from fleetplanner.domain.shared.errors import InvalidValueError


class TestFleetMixProblemBuilder:
    @staticmethod
    def _builder() -> FleetMixProblemBuilder:
        return FleetMixProblemBuilder(EffectiveCapacityCalculator(make_oee()), pct(8), 26)

    def test_problem_data_by_hand(self) -> None:
        types = {
            "X": make_type("X", 10.0, 2_600_000, 5.0),
            "Y": make_type("Y", 20.0, 5_200_000, 8.0),
        }
        problem = self._builder().build(
            [make_corridor("R1", "X")],
            types,
            CompatibilityMatrix.of([("R1", "X"), ("R1", "Y")]),
            {"R1": 20.0},
        )
        assert problem.required_t["R1"] == pytest.approx(21.6)  # 20 · 1.08
        assert problem.capacity_t[("R1", "X")] == pytest.approx(8.0)
        assert problem.capacity_t[("R1", "Y")] == pytest.approx(16.0)  # doble capacidad
        assert problem.fixed_cost_per_day == {
            "X": pytest.approx(100_000),
            "Y": pytest.approx(200_000),
        }
        # km/día = 2 viajes · 0.5 OEE · 60 km = 60
        assert problem.variable_cost_per_day[("R1", "X")] == pytest.approx(5.0 * 60)
        assert problem.variable_cost_per_day[("R1", "Y")] == pytest.approx(8.0 * 60)
        assert problem.unservable_corridors() == []

    def test_incompatible_combinations_have_no_variable(self) -> None:
        problem = self._builder().build(
            [make_corridor("R1", "X")],
            {"X": make_type("X"), "Y": make_type("Y", 20.0)},
            CompatibilityMatrix.of([("R1", "X")]),
            {"R1": 20.0},
        )
        assert ("R1", "Y") not in problem.capacity_t

    def test_corridor_without_compatible_type_is_reported(self) -> None:
        problem = self._builder().build(
            [make_corridor("R1", "X")],
            {"X": make_type("X")},
            CompatibilityMatrix.of([]),
            {"R1": 20.0},
        )
        assert problem.unservable_corridors() == ["R1"]

    def test_zero_demand_without_compatibility_is_not_unservable(self) -> None:
        problem = self._builder().build(
            [make_corridor("R1", "X")],
            {"X": make_type("X")},
            CompatibilityMatrix.of([]),
            {"R1": 0.0},
        )
        assert problem.unservable_corridors() == []

    def test_missing_demand_is_error(self) -> None:
        with pytest.raises(InvalidValueError, match="no se asume cero"):
            self._builder().build(
                [make_corridor("R1", "X")], {"X": make_type("X")}, CompatibilityMatrix.of([]), {}
            )


class TestSolution:
    def test_only_optimal_or_feasible_have_solution(self) -> None:
        assert not FleetMixSolution(SolverStatus.INFEASIBLE).has_solution
        assert not FleetMixSolution(SolverStatus.ERROR).has_solution
        assert not FleetMixSolution(SolverStatus.TIME_LIMIT).has_solution
        assert FleetMixSolution(SolverStatus.OPTIMAL, fleet_by_type={"X": 2}).has_solution
        assert FleetMixSolution(SolverStatus.FEASIBLE, fleet_by_type={"X": 2}).has_solution

    def test_total_vehicles_sums_fleet(self) -> None:
        assert (
            FleetMixSolution(SolverStatus.OPTIMAL, fleet_by_type={"X": 2, "Y": 3}).total_vehicles
            == 5
        )


class TestKpis:
    def test_kpis_by_hand(self) -> None:
        corridor = make_corridor("R1", backhaul_pct=20)
        vehicle = make_type("X", 10.0, 2_600_000, 5.0)
        capacities = {"R1": EffectiveCapacityCalculator(make_oee()).calculate(corridor, vehicle)}
        requirement = FleetRequirementCalculator(pct(8)).calculate(
            [corridor], {"R1": 16.0}, capacities, {"X": 4}
        )
        kpis = CapacityKpiCalculator(26).calculate(
            [corridor], {"X": vehicle}, {"R1": 16.0}, capacities, requirement
        )
        # flota fraccional 16/8 = 2 ; requerida ceil(2.16) = 3 ; actual 4
        assert kpis.fleet_utilization == pytest.approx(0.5)
        assert kpis.oee == pytest.approx(0.5)
        assert kpis.fill_pct == pytest.approx(0.8)
        # viajes = 16/(10·0.8) = 2 ; km totales = 2·60 = 120 ; vacío = 2·30·0.8 = 48
        assert kpis.empty_km_pct == pytest.approx(48 / 120)
        # costo = 3 vehículos · 100 000 + 5 · 120 km
        assert kpis.daily_cost == pytest.approx(300_600)
        assert kpis.cost_per_ton == pytest.approx(300_600 / 16)
        assert kpis.cost_per_ton_km == pytest.approx(300_600 / (16 * 30))
        assert kpis.otif is None  # depende del módulo de ruteo: no se inventa

    def test_utilization_is_not_available_without_current_fleet(self) -> None:
        corridor = make_corridor("R1")
        vehicle = make_type()
        capacities = {"R1": EffectiveCapacityCalculator(make_oee()).calculate(corridor, vehicle)}
        requirement = FleetRequirementCalculator(pct(0)).calculate(
            [corridor], {"R1": 8.0}, capacities, {}
        )
        kpis = CapacityKpiCalculator(26).calculate(
            [corridor], {"X": vehicle}, {"R1": 8.0}, capacities, requirement
        )
        assert kpis.fleet_utilization is None
