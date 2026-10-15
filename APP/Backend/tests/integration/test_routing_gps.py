"""GPS simulado en el ruteo: posición con antigüedad, geocerca y alerta de "sin señal"."""

from __future__ import annotations

import pytest

from fleetplanner.application.dto.routing import SimControl, SimControlAction
from fleetplanner.domain.shared.errors import InvalidValueError, NotFoundError
from routing_flow_helpers import Flow, seeded


def day() -> Flow:
    flow = seeded(customers=10, vehicles=2)
    flow.ws.day.start("t")
    flow.ws.snapshot.execute()  # primera lectura de los dispositivos, a las 05:00
    return flow


def cut(flow: Flow, vehicle: str, enabled: bool) -> None:
    flow.ws.day.control(SimControl(SimControlAction.GPS_SIGNAL, 1.0 if enabled else 0.0, vehicle))


def codes(flow: Flow) -> set[str]:
    return {a.code for a in flow.ws.snapshot.execute().alerts}


class TestPositions:
    def test_vehicle_position_is_the_last_gps_fix_with_its_age(self) -> None:
        flow = day()
        flow.at(9)
        snap = flow.ws.snapshot.execute()
        for v in snap.vehicles:
            if v.route_status == "active":
                assert v.gps_status == "ok"
                assert v.gps_age_min is not None and 0 <= v.gps_age_min <= 2.0
                assert v.gps_signal_enabled

    def test_reserve_vehicles_do_not_report_before_they_are_used(self) -> None:
        flow = day()
        flow.at(9)
        reserve = next(v for v in flow.ws.snapshot.execute().vehicles if v.id == "V-03")
        assert reserve.gps_status == "n/a" and reserve.gps_age_min is None

    def test_fixes_are_recorded_every_two_simulated_minutes(self) -> None:
        flow = day()
        flow.at(7)
        fixes = flow.ws.core.gps.fixes_since("V-01", 300)
        gaps = {round(b.at_min - a.at_min, 6) for a, b in zip(fixes, fixes[1:], strict=False)}
        assert gaps == {2.0} and fixes[0].at_min == 300


class TestGeofence:
    def test_deliveries_are_confirmed_by_geofence_after_more_than_five_minutes(self) -> None:
        flow = day()
        flow.at(11)
        snap = flow.ws.snapshot.execute()
        done = [s for s in snap.stops if s.state == "completed" and s.kind == "delivery"]
        assert done, "debe haber entregas ya hechas a las 11:00"
        confirmed = [s for s in done if s.confirmed_by == "geofence"]
        assert len(confirmed) == len(done)
        for s in confirmed:
            assert s.confirmed_min is not None and s.confirmed_min - s.arrival_min > 5 - 2.0001

    def test_pending_deliveries_are_not_confirmed_yet(self) -> None:
        flow = day()
        flow.at(7)
        snap = flow.ws.snapshot.execute()
        assert all(s.confirmed_by is None for s in snap.stops if s.state == "pending")

    def test_the_first_confirmation_wins_and_is_not_overwritten(self) -> None:
        flow = day()
        flow.at(11)
        flow.ws.snapshot.execute()
        before = flow.ws.core.repo.confirmations()
        flow.at(12)
        flow.ws.snapshot.execute()
        after = flow.ws.core.repo.confirmations()
        assert all(after[k] == v for k, v in before.items())
        assert len(after) >= len(before)


class TestNoSignal:
    def test_alert_appears_only_after_more_than_15_minutes_and_keeps_the_plan(self) -> None:
        flow = day()
        flow.at(8)
        flow.ws.snapshot.execute()
        cut(flow, "V-01", False)
        flow.at(8, 10)
        assert "no_signal" not in codes(flow)  # 10 min: todavía no
        flow.at(8, 20)
        snap = flow.ws.snapshot.execute()
        alert = next(a for a in snap.alerts if a.code == "no_signal")
        assert alert.vehicle_id == "V-01" and "Se conserva el plan vigente" in alert.message
        assert "última posición hace" in alert.message
        assert snap.plan.version == 1 and snap.proposals == ()  # no re-planifica
        vehicle = next(v for v in snap.vehicles if v.id == "V-01")
        assert vehicle.gps_status == "no_signal" and vehicle.gps_signal_enabled is False
        assert vehicle.gps_age_min is not None and vehicle.gps_age_min > 15

    def test_other_vehicles_keep_reporting(self) -> None:
        flow = day()
        flow.at(8)
        flow.ws.snapshot.execute()
        cut(flow, "V-01", False)
        flow.at(8, 30)
        by_id = {v.id: v for v in flow.ws.snapshot.execute().vehicles}
        assert by_id["V-02"].gps_status == "ok"

    def test_the_displayed_position_is_the_stale_last_fix(self) -> None:
        flow = day()
        flow.at(8)
        flow.ws.snapshot.execute()
        cut(flow, "V-01", False)
        last = flow.ws.core.gps.latest_fix("V-01")
        flow.at(8, 40)
        vehicle = next(v for v in flow.ws.snapshot.execute().vehicles if v.id == "V-01")
        assert (vehicle.lat, vehicle.lon) == (last.point.lat, last.point.lon)

    def test_alert_clears_when_the_signal_returns(self) -> None:
        flow = day()
        flow.at(8)
        flow.ws.snapshot.execute()
        cut(flow, "V-01", False)
        flow.at(8, 30)
        assert "no_signal" in codes(flow)
        cut(flow, "V-01", True)
        flow.at(8, 34)
        assert "no_signal" not in codes(flow)

    def test_a_vehicle_that_has_not_left_the_depot_is_not_flagged(self) -> None:
        flow = day()
        flow.at(5, 30)
        cut(flow, "V-01", False)
        flow.at(5, 59)
        assert "no_signal" not in codes(flow)

    def test_restarting_the_day_restores_the_signal(self) -> None:
        flow = day()
        flow.at(8)
        flow.ws.snapshot.execute()
        cut(flow, "V-01", False)
        flow.ws.day.start("t")
        assert flow.ws.core.gps_control.signal_enabled("V-01")

    def test_cutting_the_signal_needs_a_known_vehicle(self) -> None:
        flow = day()
        with pytest.raises(NotFoundError):
            cut(flow, "V-99", False)
        with pytest.raises(InvalidValueError, match="vehículo"):
            flow.ws.day.control(SimControl(SimControlAction.GPS_SIGNAL, 0.0))
