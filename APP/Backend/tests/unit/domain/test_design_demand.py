"""P1. Demanda de diseño."""

from __future__ import annotations

from datetime import date

import pytest

from builders import make_series, pct
from fleetplanner.domain.capacity.design_demand import DesignDemandCalculator
from fleetplanner.domain.capacity.models import DemandSeries
from fleetplanner.domain.shared.errors import InsufficientDataError


def test_mean_std_and_p90_by_hand() -> None:
    series = make_series("R1", [float(v) for v in range(1, 11)])
    result = DesignDemandCalculator(pct(90)).calculate(series)
    assert result.mean_t == pytest.approx(5.5)
    assert result.std_t == pytest.approx(3.0276503540974917)
    assert result.design_t == pytest.approx(9.1)
    assert result.valid_days == 10
    assert result.window_end == date(2026, 10, 9)


def test_design_uses_percentile_not_the_mean() -> None:
    # media = (8·10 + 2·100)/10 = 28 ; P90 = posición 8.1 entre dos valores de 100 → 100
    result = DesignDemandCalculator(pct(90)).calculate(make_series("R1", [10.0] * 8 + [100.0] * 2))
    assert result.mean_t == pytest.approx(28.0)
    assert result.design_t == pytest.approx(100.0)


def test_missing_days_are_excluded_not_counted_as_zero() -> None:
    # 5 días con dato y 5 ausentes: si los ausentes fueran 0 el promedio sería 10, no 20.
    series = make_series("R1", [20.0, None, 20.0, None, 20.0, None, 20.0, None, 20.0, None])
    result = DesignDemandCalculator(pct(90)).calculate(series)
    assert result.valid_days == 5
    assert result.mean_t == pytest.approx(20.0)


def test_only_the_last_window_days_are_used() -> None:
    # 70 días: los 10 más antiguos valen 1000 t y quedan fuera de la ventana de 60.
    series = make_series("R1", [1000.0] * 10 + [10.0, 12.0] * 30)
    result = DesignDemandCalculator(pct(90), window_days=60).calculate(series)
    assert result.valid_days == 60
    assert result.mean_t == pytest.approx(11.0)
    assert result.design_t < 100


def test_empty_series_fails_with_clear_message() -> None:
    with pytest.raises(InsufficientDataError, match="no tiene demanda registrada"):
        DesignDemandCalculator().calculate(DemandSeries("R1"))


def test_single_valid_day_is_insufficient() -> None:
    with pytest.raises(InsufficientDataError, match="se requieren al menos 2"):
        DesignDemandCalculator().calculate(make_series("R1", [5.0]))


def test_constructor_rejects_unusable_settings() -> None:
    with pytest.raises(ValueError, match="ventana"):
        DesignDemandCalculator(window_days=0)
    with pytest.raises(ValueError, match="2 días"):
        DesignDemandCalculator(min_valid_days=1)


def test_window_for_reports_bounds() -> None:
    calculator = DesignDemandCalculator(window_days=60)
    assert calculator.window_for(DemandSeries("R1")) is None
    start, end = calculator.window_for(make_series("R1", [1.0, 2.0])) or (None, None)
    assert end == date(2026, 10, 9)
    assert start == date(2026, 8, 11)
