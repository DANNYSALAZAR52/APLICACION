"""P4. Proyección a cinco años."""

from __future__ import annotations

import pytest

from builders import make_corridor, make_oee, make_type, pct
from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacityCalculator
from fleetplanner.domain.capacity.fleet_requirement import FleetRequirementCalculator
from fleetplanner.domain.capacity.projection import (
    FiveYearProjector,
    GrowthScenario,
    project_demand,
)
from fleetplanner.domain.shared.errors import InvalidValueError


def test_projected_demand_by_hand() -> None:
    scenario = GrowthScenario("base", cagr=0.06)
    # 100 · 1.06^5
    assert project_demand(100.0, "R1", scenario, 2026, 2031) == pytest.approx(133.82255776)


def test_route_adjustment_is_added_to_cagr() -> None:
    scenario = GrowthScenario("base", cagr=0.06, route_adjustments={"R1": 0.02})
    assert project_demand(100.0, "R1", scenario, 2026, 2027) == pytest.approx(108.0)
    assert project_demand(100.0, "R2", scenario, 2026, 2027) == pytest.approx(106.0)


def test_new_volume_applies_from_entry_year_inclusive() -> None:
    scenario = GrowthScenario("base", cagr=0.0, new_volume_t={"R1": 10.0}, entry_year=2029)
    assert project_demand(100.0, "R1", scenario, 2026, 2028) == pytest.approx(100.0)
    assert project_demand(100.0, "R1", scenario, 2026, 2029) == pytest.approx(110.0)
    assert project_demand(100.0, "R1", scenario, 2026, 2031) == pytest.approx(110.0)


def test_negative_cagr_is_allowed_but_not_below_minus_100_percent() -> None:
    assert project_demand(100.0, "R1", GrowthScenario("p", cagr=-0.1), 2026, 2027) == pytest.approx(
        90.0
    )
    with pytest.raises(InvalidValueError, match="−100 %"):
        project_demand(100.0, "R1", GrowthScenario("x", cagr=-1.0), 2026, 2027)


def test_year_before_base_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        project_demand(100.0, "R1", GrowthScenario("x", cagr=0.0), 2026, 2025)


def test_negative_new_volume_rejected() -> None:
    with pytest.raises(InvalidValueError):
        GrowthScenario("x", cagr=0.0, new_volume_t={"R1": -1.0})


def _projector() -> tuple[FiveYearProjector, EffectiveCapacityCalculator]:
    return (
        FiveYearProjector(FleetRequirementCalculator(pct(8))),
        EffectiveCapacityCalculator(make_oee()),
    )


def test_first_deficit_year_is_detected() -> None:
    projector, calc = _projector()
    corridor = make_corridor("R1")
    capacities = {"R1": calc.calculate(corridor, make_type())}  # 8 t/día por vehículo
    # Diseño 20 t = 2.5 veh. Con 20 %: 2027 → 24 t = 3.0 veh ×1.08 = 3.24 → 4 > 3 actuales.
    projection = projector.project(
        GrowthScenario("agresivo", cagr=0.20), 2026, [corridor], {"R1": 20.0}, capacities, {"X": 3}
    )
    assert [y.year for y in projection.years] == [2027, 2028, 2029, 2030, 2031]
    assert projection.years[0].requirement.required_by_type["X"] == 4
    assert projection.first_deficit_year == 2027
    assert projection.first_deficit_year_by_type == {"X": 2027}


def test_no_deficit_returns_none() -> None:
    projector, calc = _projector()
    corridor = make_corridor("R1")
    capacities = {"R1": calc.calculate(corridor, make_type())}
    projection = projector.project(
        GrowthScenario("plano", cagr=0.0), 2026, [corridor], {"R1": 20.0}, capacities, {"X": 3}
    )
    # 2.5 × 1.08 = 2.7 → 3 ≤ 3
    assert projection.first_deficit_year is None
    assert projection.first_deficit_year_by_type == {"X": None}


def test_horizon_must_be_positive() -> None:
    with pytest.raises(InvalidValueError):
        FiveYearProjector(FleetRequirementCalculator(pct(8)), horizon_years=0)
