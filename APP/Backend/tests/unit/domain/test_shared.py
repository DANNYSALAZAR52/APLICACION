"""Value objects y estadísticos compartidos."""

from __future__ import annotations

import math

import pytest

from fleetplanner.domain.shared.errors import InsufficientDataError, InvalidValueError
from fleetplanner.domain.shared.percentage import Percentage
from fleetplanner.domain.shared.stats import (
    ceil_fleet,
    mean,
    percentile_linear,
    percentile_nearest_rank,
    sample_std,
)


class TestPercentage:
    def test_percent_input_is_normalized_to_fraction(self) -> None:
        assert Percentage.from_percent(90).fraction == pytest.approx(0.9)
        assert Percentage.from_percent(90).percent == pytest.approx(90.0)

    @pytest.mark.parametrize("bad", [-1, 100.1, 250])
    def test_percent_out_of_range_is_rejected_with_spanish_message(self, bad: float) -> None:
        with pytest.raises(InvalidValueError, match="entre 0 y 100"):
            Percentage.from_percent(bad)

    @pytest.mark.parametrize("bad", [-0.01, 1.01])
    def test_fraction_out_of_range_is_rejected(self, bad: float) -> None:
        with pytest.raises(InvalidValueError):
            Percentage.from_fraction(bad)

    def test_boundaries_are_valid(self) -> None:
        assert Percentage.from_percent(0).fraction == 0.0
        assert Percentage.from_percent(100).fraction == 1.0


class TestStats:
    def test_mean_and_sample_std_by_hand(self) -> None:
        values = [float(v) for v in range(1, 11)]
        assert mean(values) == pytest.approx(5.5)
        # Σ(v-5.5)² = 82.5 ; /(n-1)=9 ; raíz
        assert sample_std(values) == pytest.approx(math.sqrt(82.5 / 9))

    def test_std_needs_two_values(self) -> None:
        with pytest.raises(InsufficientDataError):
            sample_std([4.0])

    def test_mean_of_empty_fails_instead_of_returning_zero(self) -> None:
        with pytest.raises(InsufficientDataError):
            mean([])

    def test_percentile_linear_matches_inclusive_definition(self) -> None:
        values = [float(v) for v in range(1, 11)]
        # posición = 0.9·9 = 8.1 → 9 + 0.1·(10−9)
        assert percentile_linear(values, 0.9) == pytest.approx(9.1)
        assert percentile_linear(values, 0.0) == 1.0
        assert percentile_linear(values, 1.0) == 10.0
        assert percentile_linear([5.0], 0.9) == 5.0

    def test_percentile_linear_ignores_input_order(self) -> None:
        assert percentile_linear([10.0, 1.0, 5.0], 0.5) == 5.0

    def test_percentile_nearest_rank_returns_observed_value(self) -> None:
        values = list(range(1, 101))
        assert percentile_nearest_rank(values, 0.95) == 95
        assert percentile_nearest_rank(values, 0.5) == 50
        assert percentile_nearest_rank([7], 0.99) == 7

    def test_percentile_rejects_bad_fraction(self) -> None:
        with pytest.raises(InvalidValueError):
            percentile_linear([1.0], 1.5)
        with pytest.raises(InvalidValueError):
            percentile_nearest_rank([1], 0.0)

    def test_ceil_fleet_does_not_inflate_on_float_noise(self) -> None:
        assert ceil_fleet(3.0000000000000004) == 3
        assert ceil_fleet(3.01) == 4
        assert ceil_fleet(0.0) == 0

    def test_ceil_fleet_rejects_negative(self) -> None:
        with pytest.raises(InvalidValueError):
            ceil_fleet(-0.5)
