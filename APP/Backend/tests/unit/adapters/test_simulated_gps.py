"""Simulador de GPS: cadencia de lecturas, pérdida de señal y puesta al día."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fleetplanner.adapters.outbound.clock import BOGOTA_TZ, FixedClock
from fleetplanner.adapters.outbound.gps import SimulatedGps
from fleetplanner.domain.routing.gps import GpsSample
from routing_builders import point


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 14, hour, minute, tzinfo=BOGOTA_TZ)


def truth(vehicle_id: str, minute: float) -> GpsSample | None:
    if vehicle_id == "V-ZZ":
        return None
    return GpsSample(point(int(minute) % 90), 30.0, True)


SEVEN = at(7)


def make(start=SEVEN) -> tuple[SimulatedGps, FixedClock]:  # type: ignore[no-untyped-def]
    clock = FixedClock(start)
    return SimulatedGps(truth, clock, ["V-01", "V-ZZ"]), clock


class TestCadence:
    def test_first_read_records_a_fix_at_the_current_time(self) -> None:
        gps, _ = make()
        fix = gps.latest_fix("V-01")
        assert fix is not None and fix.at_min == 420

    def test_one_fix_every_two_simulated_minutes(self) -> None:
        gps, clock = make()
        gps.latest_fix("V-01")
        clock.advance(timedelta(minutes=10))
        minutes = [f.at_min for f in gps.fixes_since("V-01", 0)]
        assert minutes == [420, 422, 424, 426, 428, 430]

    def test_fixes_since_filters_by_time(self) -> None:
        gps, clock = make()
        gps.latest_fix("V-01")
        clock.advance(timedelta(minutes=10))
        assert [f.at_min for f in gps.fixes_since("V-01", 426)] == [426, 428, 430]

    def test_a_vehicle_without_truth_never_reports(self) -> None:
        gps, _ = make()
        assert gps.latest_fix("V-ZZ") is None

    def test_unknown_vehicle_has_no_fix(self) -> None:
        gps, _ = make()
        assert gps.latest_fix("NOPE") is None and gps.fixes_since("NOPE", 0) == []


class TestSignalLoss:
    def test_muted_vehicle_stops_reporting_and_its_last_fix_ages(self) -> None:
        gps, clock = make()
        gps.latest_fix("V-01")
        clock.advance(timedelta(minutes=4))  # 07:04
        gps.set_signal("V-01", False)
        assert not gps.signal_enabled("V-01")
        clock.advance(timedelta(minutes=30))
        last = gps.latest_fix("V-01")
        assert last is not None and last.at_min == 424  # nada nuevo desde que se cortó

    def test_signal_comes_back_and_reporting_resumes(self) -> None:
        gps, clock = make()
        gps.latest_fix("V-01")
        gps.set_signal("V-01", False)
        clock.advance(timedelta(minutes=20))
        gps.set_signal("V-01", True)
        clock.advance(timedelta(minutes=4))
        fix = gps.latest_fix("V-01")
        assert fix is not None and fix.at_min >= 440

    def test_muting_one_vehicle_does_not_affect_the_others(self) -> None:
        clock = FixedClock(at(7))
        gps = SimulatedGps(truth, clock, ["V-01", "V-02"])
        gps.latest_fix("V-01")
        gps.set_signal("V-01", False)
        clock.advance(timedelta(minutes=10))
        assert gps.latest_fix("V-02").at_min == 430  # type: ignore[union-attr]
        assert gps.latest_fix("V-01").at_min == 420  # type: ignore[union-attr]


class TestClockAndLimits:
    def test_going_back_in_time_discards_the_future_history(self) -> None:
        gps, clock = make()
        gps.latest_fix("V-01")
        clock.advance(timedelta(minutes=20))
        gps.latest_fix("V-01")
        clock._instant = at(6)  # noqa: SLF001 - FixedClock no retrocede: se fuerza para la prueba
        fix = gps.latest_fix("V-01")
        assert fix is not None and fix.at_min == 360
        assert [f.at_min for f in gps.fixes_since("V-01", 0)] == [360]

    def test_catch_up_is_capped_to_avoid_unbounded_work(self) -> None:
        gps, clock = make(at(0))
        gps.latest_fix("V-01")
        clock.advance(timedelta(hours=20))
        fixes = gps.fixes_since("V-01", 60)  # sin la lectura inicial de las 00:00
        assert fixes[0].at_min >= 20 * 60 - 300 - 2 and len(fixes) <= 151

    def test_reset_clears_history_and_signal_cuts(self) -> None:
        gps, _ = make()
        gps.latest_fix("V-01")
        gps.set_signal("V-01", False)
        gps.reset()
        assert gps.signal_enabled("V-01")
        # tras el reinicio solo existe la primera lectura nueva, a la hora del reloj
        assert [f.at_min for f in gps.fixes_since("V-01", 0)] == [420]

    @pytest.mark.parametrize("interval", [0.5, 6.0])
    def test_interval_must_be_between_1_and_5_minutes(self, interval: float) -> None:
        with pytest.raises(ValueError, match="1 a 5 minutos"):
            SimulatedGps(truth, FixedClock(at(7)), ["V-01"], interval_min=interval)
