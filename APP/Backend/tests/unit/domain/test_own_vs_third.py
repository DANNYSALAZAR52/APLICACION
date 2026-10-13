"""P8. Propio vs. tercero."""

from __future__ import annotations

from datetime import date

import pytest

from builders import make_corridor, make_oee, make_series, make_type
from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacityCalculator
from fleetplanner.domain.capacity.own_vs_third import (
    OwnFleetCosts,
    OwnVsThirdPartyAnalyzer,
    cost_of_own_fleet,
    daily_required_vehicles,
)
from fleetplanner.domain.shared.errors import InsufficientDataError, InvalidValueError

COSTS = OwnFleetCosts(
    fixed_per_day=100.0, variable_per_used_vehicle_day=10.0, third_party_per_day=150.0
)
HISTORY = [1, 2, 3, 4]


@pytest.mark.parametrize(
    ("own", "expected"),
    [
        (0, 375.0),  # 150 · 2.5
        (1, 335.0),  # 100 + 10·1 + 150·1.5
        (2, 330.0),  # 200 + 10·1.75 + 150·0.75
        (3, 360.0),  # 300 + 10·2.25 + 150·0.25
        (4, 425.0),  # 400 + 10·2.5
    ],
)
def test_cost_curve_by_hand(own: int, expected: float) -> None:
    assert cost_of_own_fleet(HISTORY, own, COSTS) == pytest.approx(expected)


def test_optimal_own_fleet_minimizes_cost() -> None:
    result = OwnVsThirdPartyAnalyzer().analyze({"X": HISTORY}, {"X": COSTS})
    item = result.by_type["X"]
    assert item.optimal_own == 2
    assert item.optimal_cost_per_day == pytest.approx(330.0)
    assert item.all_third_party_cost_per_day == pytest.approx(375.0)
    assert item.all_own_cost_per_day == pytest.approx(425.0)
    assert item.days_used == 4
    assert result.total_own == 2


def test_search_range_comes_from_history_not_a_fixed_cap() -> None:
    history = [95, 100, 110]
    cheap_own = OwnFleetCosts(1.0, 0.0, 1000.0)
    item = OwnVsThirdPartyAnalyzer().analyze({"X": history}, {"X": cheap_own}).by_type["X"]
    assert len(item.curve) == max(history) + 1
    assert item.optimal_own == 110  # muy por encima de un tope fijo de 40


def test_tie_prefers_the_smaller_fleet() -> None:
    free = OwnFleetCosts(0.0, 0.0, 0.0)
    assert (
        OwnVsThirdPartyAnalyzer().analyze({"X": [3, 5]}, {"X": free}).by_type["X"].optimal_own == 0
    )


def test_types_are_optimized_independently() -> None:
    result = OwnVsThirdPartyAnalyzer().analyze(
        {"X": HISTORY, "Y": [5, 5]},
        {"X": COSTS, "Y": OwnFleetCosts(10.0, 0.0, 100.0)},
    )
    assert result.by_type["X"].optimal_own == 2
    assert result.by_type["Y"].optimal_own == 5
    assert result.total_own == 7


def test_empty_history_is_insufficient() -> None:
    with pytest.raises(InsufficientDataError):
        OwnVsThirdPartyAnalyzer().analyze({"X": []}, {"X": COSTS})


def test_negative_costs_are_rejected() -> None:
    with pytest.raises(InvalidValueError):
        OwnFleetCosts(-1.0, 0.0, 0.0)


class TestDailyRequiredVehicles:
    def test_only_days_complete_for_every_corridor_count(self) -> None:
        calc = EffectiveCapacityCalculator(make_oee())
        c1, c2 = make_corridor("R1"), make_corridor("R2")
        capacities = {c.code: calc.calculate(c, make_type()) for c in (c1, c2)}  # 8 t/veh
        demand = {
            "R1": make_series("R1", [16.0, 16.0, 16.0]),
            "R2": make_series("R2", [8.0, None, 24.0]),  # el día 2 falta: no es cero
        }
        window = (min(demand["R1"].observations), max(demand["R1"].observations))
        result = daily_required_vehicles([c1, c2], capacities, demand, window)
        # día 1: 2+1 = 3 ; día 3: 2+3 = 5 ; el día 2 se descarta
        assert result == {"X": [3, 5]}

    def test_no_complete_day_gives_empty_result(self) -> None:
        calc = EffectiveCapacityCalculator(make_oee())
        c1 = make_corridor("R1")
        capacities = {"R1": calc.calculate(c1, make_type())}
        demand = {"R1": make_series("R1", [None, None])}
        window = (date(2026, 10, 8), date(2026, 10, 9))
        assert daily_required_vehicles([c1], capacities, demand, window) == {}
