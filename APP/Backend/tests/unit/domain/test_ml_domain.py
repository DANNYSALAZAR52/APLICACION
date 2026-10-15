"""Dominio de ML: festivos de Colombia, métricas puras, partición temporal y tipos."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fleetplanner.domain.ml.calendar_co import (
    colombia_holidays,
    easter_sunday,
    is_holiday,
    is_quincena,
)
from fleetplanner.domain.ml.metrics import auc, brier, mae, mape, precision_recall, temporal_cutoff
from fleetplanner.domain.ml.records import OperationalHistory, ServiceVisit
from fleetplanner.domain.ml.results import Anomaly, DelayRisk, Forecast
from fleetplanner.domain.shared.errors import InsufficientDataError, InvalidValueError


class TestColombiaHolidays:
    @pytest.mark.parametrize(
        ("year", "expected"),
        [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5))],
    )
    def test_easter(self, year: int, expected: date) -> None:
        assert easter_sunday(year) == expected

    def test_2026_calendar_matches_the_official_list(self) -> None:
        expected = {
            date(2026, 1, 1),
            date(2026, 1, 12),
            date(2026, 3, 23),
            date(2026, 4, 2),
            date(2026, 4, 3),
            date(2026, 5, 1),
            date(2026, 5, 18),
            date(2026, 6, 8),
            date(2026, 6, 15),
            date(2026, 6, 29),
            date(2026, 7, 20),
            date(2026, 8, 7),
            date(2026, 8, 17),
            date(2026, 10, 12),
            date(2026, 11, 2),
            date(2026, 11, 16),
            date(2026, 12, 8),
            date(2026, 12, 25),
        }
        assert colombia_holidays(2026) == expected

    def test_movable_holidays_always_land_on_a_monday(self) -> None:
        for year in (2025, 2026, 2027):
            moved = [
                date(year, 1, 6),
                date(year, 3, 19),
                date(year, 6, 29),
                date(year, 8, 15),
                date(year, 10, 12),
                date(year, 11, 1),
                date(year, 11, 11),
            ]
            for original in moved:
                shifted = original + timedelta(days=(7 - original.weekday()) % 7)
                assert shifted in colombia_holidays(year)
                assert shifted.weekday() == 0
        assert date(2025, 1, 6) in colombia_holidays(2025)  # lunes
        assert date(2025, 3, 24) in colombia_holidays(2025)  # San José, lunes

    def test_is_holiday_and_quincena(self) -> None:
        assert is_holiday(date(2026, 12, 25))
        assert not is_holiday(date(2026, 12, 26))
        assert is_quincena(date(2026, 10, 15))
        assert is_quincena(date(2026, 10, 31))
        assert not is_quincena(date(2026, 10, 7))


class TestMetrics:
    def test_mae(self) -> None:
        assert mae([10, 20], [12, 17]) == 2.5

    def test_mape_skips_zero_denominators_and_says_how_many(self) -> None:
        value, skipped = mape([100, 0, 50], [110, 5, 40])
        assert skipped == 1
        assert value == pytest.approx(15.0)

    def test_mape_without_usable_data_is_none(self) -> None:
        assert mape([0, 0], [1, 2]) == (None, 2)

    def test_brier_and_auc(self) -> None:
        assert brier([True, False], [1.0, 0.0]) == 0.0
        assert brier([True, False], [0.5, 0.5]) == 0.25
        assert auc([True, False, True, False], [0.9, 0.1, 0.8, 0.3]) == 1.0
        assert auc([True, False], [0.5, 0.5]) == 0.5
        assert auc([True, True], [0.2, 0.9]) is None

    def test_precision_recall_with_zero_denominators(self) -> None:
        assert precision_recall([True, False, True], [0.9, 0.8, 0.1], 0.5) == (0.5, 0.5)
        assert precision_recall([False, False], [0.1, 0.2], 0.5) == (None, None)

    def test_length_mismatch_is_rejected(self) -> None:
        with pytest.raises(InvalidValueError):
            mae([1.0], [1.0, 2.0])

    def test_empty_inputs_are_insufficient_data(self) -> None:
        with pytest.raises(InsufficientDataError):
            mae([], [])
        with pytest.raises(InsufficientDataError):
            brier([], [])


class TestTemporalCutoff:
    def test_everything_before_the_cutoff_trains_and_everything_after_tests(self) -> None:
        days = [date(2026, 1, 1) + timedelta(days=i) for i in range(100)]
        cutoff = temporal_cutoff(days, 0.2)
        train = [d for d in days if d < cutoff]
        test = [d for d in days if d >= cutoff]
        assert len(test) == 20
        assert max(train) < min(test)  # sin fuga: ningún día de prueba precede al entrenamiento

    def test_unordered_and_duplicated_days_do_not_matter(self) -> None:
        base = date(2026, 1, 1)
        days = [base + timedelta(days=i % 10) for i in range(50)]
        assert temporal_cutoff(days, 0.3) == temporal_cutoff(sorted(days, reverse=True), 0.3)

    def test_invalid_fraction_and_too_few_days(self) -> None:
        with pytest.raises(InvalidValueError):
            temporal_cutoff([date(2026, 1, 1), date(2026, 1, 2)], 1.0)
        with pytest.raises(InsufficientDataError):
            temporal_cutoff([date(2026, 1, 1)], 0.2)


class TestTypes:
    def test_forecast_requires_p90_not_below_p50(self) -> None:
        with pytest.raises(InvalidValueError):
            Forecast("C1", date(2026, 1, 1), p50_t=10, p90_t=9, baseline_t=None)

    def test_delay_probability_is_bounded(self) -> None:
        with pytest.raises(InvalidValueError):
            DelayRisk("C", "Cliente", 8, 1.2, 1.1, 3, 100)

    def test_visit_validation(self) -> None:
        good = {
            "customer_code": "C", "corridor_code": "R", "day": date(2026, 1, 5), "hour": 9,
            "wait_min": 5.0, "service_min": 10.0, "order_kg": 100.0, "window_width_min": 120,
            "traffic_factor": 1.1, "stops_remaining": 2, "late": False,
        }  # fmt: skip
        ServiceVisit(**good)  # type: ignore[arg-type]
        for patch in (
            {"hour": 24},
            {"wait_min": -1.0},
            {"window_width_min": 0},
            {"traffic_factor": 0.0},
            {"stops_remaining": -1},
        ):
            with pytest.raises(InvalidValueError):
                ServiceVisit(**{**good, **patch})  # type: ignore[arg-type]

    def test_anomaly_message_is_plain_spanish_and_does_not_claim_causality(self) -> None:
        anomaly = Anomaly("C-7", "Cliente 7", "espera", 4, 10, 12, 12, 24.0, 8.0, 5.0)
        text = anomaly.message
        assert "los viernes entre las 10:00 y las 12:00" in text
        assert "3,0 veces" in text
        assert "no demuestra la causa" in text
        assert anomaly.ratio == 3.0

    def test_history_spans_and_names(self) -> None:
        history = OperationalHistory(demand={}, visits=(), provenance="x")
        assert history.span_days == 0
        assert history.first_day is None and history.last_day is None
        assert history.customer_name("C-1") == "C-1"
