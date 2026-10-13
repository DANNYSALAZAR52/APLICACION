"""Invariantes de los modelos de capacidad."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from builders import make_corridor, make_oee, make_type, pct
from fleetplanner.domain.capacity.models import (
    CompatibilityMatrix,
    DemandSeries,
    OeeFactors,
    VehicleType,
)
from fleetplanner.domain.capacity.results import CapacityMethod, CapacityResult
from fleetplanner.domain.shared.errors import InvalidValueError


class TestVehicleType:
    def test_monthly_fixed_cost_converts_to_daily(self) -> None:
        assert make_type(fixed_month=2_600_000).fixed_cost_per_day(26) == pytest.approx(100_000)

    def test_rejects_non_positive_capacity(self) -> None:
        with pytest.raises(InvalidValueError, match="capacidad"):
            VehicleType("X", 0, 10, 1, 0, 0, 0)

    def test_rejects_negative_costs(self) -> None:
        with pytest.raises(InvalidValueError):
            VehicleType("X", 5, 10, 1, -1, 0, 0)

    def test_rejects_zero_days_per_month(self) -> None:
        with pytest.raises(InvalidValueError):
            make_type().fixed_cost_per_day(0)


class TestOee:
    def test_oee_is_product_of_factors(self) -> None:
        oee = OeeFactors(pct(90), pct(85), pct(95))
        assert oee.oee == pytest.approx(0.9 * 0.85 * 0.95)

    def test_zero_factor_is_rejected(self) -> None:
        with pytest.raises(InvalidValueError, match="mayor que 0"):
            OeeFactors(pct(0), pct(80), pct(90))


class TestCorridor:
    @pytest.mark.parametrize("field", ["km", "speed", "hours"])
    def test_non_positive_values_rejected(self, field: str) -> None:
        with pytest.raises(InvalidValueError):
            make_corridor(**{field: 0})

    def test_zero_fill_rejected(self) -> None:
        with pytest.raises(InvalidValueError, match="llenado"):
            make_corridor(fill_pct=0)


class TestCompatibilityAndDemand:
    def test_compatibility_lookup(self) -> None:
        matrix = CompatibilityMatrix.of([("R1", "X"), ("R1", "Y")])
        assert matrix.is_allowed("R1", "X")
        assert not matrix.is_allowed("R2", "X")
        assert matrix.types_for("R1") == ["X", "Y"]

    def test_negative_demand_rejected(self) -> None:
        with pytest.raises(InvalidValueError, match="negativa"):
            DemandSeries("R1", {date(2026, 1, 1): -1.0})

    def test_empty_series_has_no_last_date(self) -> None:
        assert DemandSeries("R1").last_date() is None


class TestCapacityResult:
    def test_naive_datetime_is_rejected(self) -> None:
        with pytest.raises(InvalidValueError, match="zona horaria"):
            CapacityResult(datetime(2026, 1, 1), CapacityMethod.BALANCE, "X", None, 1, "v", {})

    def test_negative_fleet_rejected(self) -> None:
        with pytest.raises(InvalidValueError):
            CapacityResult(
                datetime(2026, 1, 1, tzinfo=UTC), CapacityMethod.BALANCE, "X", None, -1, "v", {}
            )


def test_make_oee_default_is_half() -> None:
    assert make_oee().oee == 0.5
