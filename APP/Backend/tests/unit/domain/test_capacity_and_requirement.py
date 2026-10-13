"""P2 (ciclo y capacidad efectiva) y P3 (flota por balance)."""

from __future__ import annotations

import pytest

from builders import make_corridor, make_oee, make_type, pct
from fleetplanner.domain.capacity.effective_capacity import (
    EffectiveCapacityCalculator,
    trip_cycle_hours,
    vehicle_daily_km,
)
from fleetplanner.domain.capacity.fleet_requirement import FleetRequirementCalculator
from fleetplanner.domain.shared.errors import InvalidValueError


class TestEffectiveCapacity:
    def test_cycle_by_hand(self) -> None:
        # 1 + 0.5 + 2·(30/30) + 4·15/60 + 0.5 = 5
        assert trip_cycle_hours(make_corridor()) == pytest.approx(5.0)

    def test_effective_capacity_by_hand(self) -> None:
        result = EffectiveCapacityCalculator(make_oee(50)).calculate(make_corridor(), make_type())
        assert result.cycle_h == pytest.approx(5.0)
        assert result.trips_per_day == pytest.approx(2.0)
        assert result.oee == pytest.approx(0.5)
        # 10 t · 0.8 · 2 viajes · 0.5 OEE
        assert result.effective_t_per_day == pytest.approx(8.0)

    def test_daily_km_uses_effective_trips(self) -> None:
        corridor = make_corridor()
        capacity = EffectiveCapacityCalculator(make_oee(50)).calculate(corridor, make_type())
        # 2 viajes · 0.5 OEE · 60 km ida y vuelta
        assert vehicle_daily_km(corridor, capacity) == pytest.approx(60.0)

    def test_slower_speed_lowers_capacity(self) -> None:
        calc = EffectiveCapacityCalculator(make_oee())
        fast = calc.calculate(make_corridor(speed=60), make_type())
        slow = calc.calculate(make_corridor(speed=20), make_type())
        assert slow.effective_t_per_day < fast.effective_t_per_day


class TestFleetRequirement:
    @staticmethod
    def _capacities(*corridors):  # type: ignore[no-untyped-def]
        calc = EffectiveCapacityCalculator(make_oee())
        return {c.code: calc.calculate(c, make_type()) for c in corridors}

    def test_rounding_happens_once_after_summing_by_type_with_reserve(self) -> None:
        r1, r2 = make_corridor("R1"), make_corridor("R2")
        result = FleetRequirementCalculator(pct(8)).calculate(
            [r1, r2], {"R1": 20.0, "R2": 10.0}, self._capacities(r1, r2), {"X": 4}
        )
        # 20/8 + 10/8 = 3.75 ; ×1.08 = 4.05 → 5 (redondear por corredor daría 3+2=5 → ×1.08 → 6)
        assert result.fractional_by_type["X"] == pytest.approx(3.75)
        assert result.required_by_type["X"] == 5
        assert result.total_required == 5
        assert result.gap_by_type == {"X": -1}
        assert result.total_gap == -1

    def test_exact_integer_is_not_inflated(self) -> None:
        r1 = make_corridor("R1")
        result = FleetRequirementCalculator(pct(0)).calculate(
            [r1], {"R1": 16.0}, self._capacities(r1), {"X": 2}
        )
        assert result.required_by_type["X"] == 2
        assert result.total_gap == 0

    def test_positive_gap_is_surplus_and_types_without_demand_appear(self) -> None:
        r1 = make_corridor("R1")
        result = FleetRequirementCalculator(pct(0)).calculate(
            [r1], {"R1": 8.0}, self._capacities(r1), {"X": 3, "Z": 2}
        )
        assert result.gap_by_type == {"X": 2, "Z": 2}

    def test_missing_demand_is_an_error_not_zero(self) -> None:
        r1 = make_corridor("R1")
        with pytest.raises(InvalidValueError, match="no se asume cero"):
            FleetRequirementCalculator(pct(8)).calculate([r1], {}, self._capacities(r1), {})
