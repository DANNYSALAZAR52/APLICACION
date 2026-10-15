"""Geocerca de 100 m > 5 min y alerta de "sin señal" a los 15 min."""

from __future__ import annotations

from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.gps import (
    GpsFix,
    distance_m,
    fix_age_min,
    geofence_arrival,
    has_no_signal,
)
from routing_builders import point

TARGET = point(5)


def fix(minute: float, where: GeoPoint, vehicle: str = "V-01") -> GpsFix:
    return GpsFix(vehicle, minute, where, 0.0, False)


def near(meters: float) -> GeoPoint:
    """Punto a ~``meters`` metros al norte del objetivo (1° de latitud ≈ 111 195 m)."""
    return GeoPoint(TARGET.lat + meters / 111_195.0, TARGET.lon)


class TestGeofence:
    def test_distance_is_in_meters(self) -> None:
        assert 99 < distance_m(TARGET, near(100)) < 101

    def test_staying_inside_100_m_for_more_than_5_minutes_confirms_arrival(self) -> None:
        fixes = [fix(m, near(40)) for m in (600, 602, 604, 606)]
        assert geofence_arrival(fixes, TARGET, 100, 5) == 606  # 606 - 600 = 6 > 5

    def test_exactly_5_minutes_is_not_enough(self) -> None:
        fixes = [fix(m, near(40)) for m in (600, 602, 604, 605)]
        assert geofence_arrival(fixes, TARGET, 100, 5) is None

    def test_being_just_outside_the_radius_does_not_count(self) -> None:
        fixes = [fix(m, near(150)) for m in range(600, 620, 2)]
        assert geofence_arrival(fixes, TARGET, 100, 5) is None

    def test_leaving_the_circle_restarts_the_count(self) -> None:
        fixes = [
            fix(600, near(10)),
            fix(602, near(10)),
            fix(604, near(500)),  # salió
            fix(606, near(10)),
            fix(608, near(10)),
            fix(610, near(10)),
        ]
        assert geofence_arrival(fixes, TARGET, 100, 5) is None  # 606→610 son solo 4 min
        assert geofence_arrival([*fixes, fix(612, near(10))], TARGET, 100, 5) == 612

    def test_unordered_fixes_are_sorted_first(self) -> None:
        fixes = [fix(606, near(40)), fix(600, near(40)), fix(603, near(40))]
        assert geofence_arrival(fixes, TARGET, 100, 5) == 606

    def test_no_fixes_means_no_confirmation(self) -> None:
        assert geofence_arrival([], TARGET, 100, 5) is None


class TestNoSignal:
    def test_fresh_fix_is_fine(self) -> None:
        assert not has_no_signal(fix(600, TARGET), 610, 15)

    def test_exactly_15_minutes_is_still_fine_and_16_is_no_signal(self) -> None:
        assert not has_no_signal(fix(600, TARGET), 615, 15)
        assert has_no_signal(fix(600, TARGET), 616, 15)

    def test_never_reported_counts_as_no_signal(self) -> None:
        assert has_no_signal(None, 600, 15)

    def test_age_is_never_negative(self) -> None:
        assert fix_age_min(fix(610, TARGET), 600) == 0
        assert fix_age_min(fix(600, TARGET), 618) == 18
