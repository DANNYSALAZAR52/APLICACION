"""Geografía, validaciones (criterio 11) y evaluación de rutas con cálculo a mano."""

from __future__ import annotations

import pytest

from fleetplanner.domain.routing.evaluation import evaluate_route
from fleetplanner.domain.routing.geo import GeoPoint, haversine_km, interpolate
from fleetplanner.domain.routing.models import Customer, Order, RoutingParams, RoutingVehicle
from fleetplanner.domain.routing.time_window import TimeWindow, format_clock, parse_clock
from fleetplanner.domain.shared.errors import InvalidValueError
from routing_builders import DEPOT_POINT, PARAMS, constant_travel, point, spec


class TestGeo:
    def test_one_degree_of_latitude_is_about_111_km(self) -> None:
        assert haversine_km(GeoPoint(4.0, -74.0), GeoPoint(5.0, -74.0)) == pytest.approx(
            111.19, abs=0.1
        )

    def test_distance_to_itself_is_zero(self) -> None:
        assert haversine_km(DEPOT_POINT, DEPOT_POINT) == 0

    def test_interpolation_midpoint(self) -> None:
        a, b = GeoPoint(4.0, -74.0), GeoPoint(5.0, -73.0)
        mid = interpolate(a, b, 0.5)
        assert (mid.lat, mid.lon) == (4.5, -73.5)

    def test_urban_area_flag(self) -> None:
        assert DEPOT_POINT.is_in_urban_area()
        assert not GeoPoint(6.2, -75.6).is_in_urban_area()  # Medellín: válido, pero fuera de Bogotá


class TestWindowsAndClock:
    def test_clock_formatting_and_parsing_round_trip(self) -> None:
        assert format_clock(375) == "06:15"
        assert parse_clock("06:15") == 375

    @pytest.mark.parametrize("bad", ["25:00", "6", "ab:cd", "10:75", ""])
    def test_invalid_clock_text_is_rejected(self, bad: str) -> None:
        with pytest.raises(InvalidValueError):
            parse_clock(bad)

    def test_window_that_ends_before_it_starts_is_rejected_with_explanation(self) -> None:
        with pytest.raises(InvalidValueError, match="posterior"):
            TimeWindow(14 * 60, 10 * 60)


class TestCriterion11CustomerValidation:
    """Criterio 11: latitud 40 y ventana 14:00–10:00 se rechazan, explicando qué corregir."""

    def test_latitude_40_and_inverted_window_are_both_reported(self) -> None:
        with pytest.raises(InvalidValueError) as err:
            Customer.create("C-77", "Cliente X", "Calle 1", 40.0, -74.1, 14 * 60, 10 * 60)
        message = str(err.value)
        assert "C-77" in message
        assert "latitud 40" in message and "fuera de Colombia" in message
        assert "14:00–10:00" in message and "posterior" in message

    def test_valid_customer_is_created_and_outside_bogota_is_flagged_for_review(self) -> None:
        ok = Customer.create("C-1", "A", "Calle 1", 4.65, -74.1, 8 * 60, 12 * 60)
        assert not ok.needs_location_review
        far = Customer.create("C-2", "B", "Calle 2", 6.2, -75.6, 8 * 60, 12 * 60)
        assert far.needs_location_review

    def test_non_positive_service_minutes_are_rejected(self) -> None:
        with pytest.raises(InvalidValueError, match="minutos de servicio"):
            Customer.create("C-3", "C", "x", 4.6, -74.1, 480, 720, service_minutes=0)


class TestOrdersAndVehicles:
    def test_order_requires_positive_kg_and_valid_priority(self) -> None:
        window = TimeWindow(480, 720)
        with pytest.raises(InvalidValueError):
            Order("P-1", "C-1", 0, 1, window)
        with pytest.raises(InvalidValueError):
            Order("P-1", "C-1", 10, 1, window, priority=9)

    def test_turbo_operational_capacity_is_4050_kg(self) -> None:
        turbo = RoutingVehicle("V-1", "AAA111", "turbo", 4500)
        assert PARAMS.operational_capacity_kg(turbo) == pytest.approx(4050)

    def test_service_minutes_are_15_plus_kg_over_50(self) -> None:
        cust = Customer.create("C-1", "A", "x", 4.6, -74.1, 480, 720)
        assert PARAMS.service_minutes_for(cust, 500) == pytest.approx(25.0)

    def test_params_reject_invalid_values(self) -> None:
        with pytest.raises(InvalidValueError):
            RoutingParams(max_fill=1.5)
        with pytest.raises(InvalidValueError):
            RoutingParams(weight_delay=-1)


class TestEvaluateRouteByHand:
    """Viaje constante de 10 min / 5 km; salida 06:00 (360)."""

    def run(self, specs, load=300.0, capacity=4050.0, depart=360.0):  # type: ignore[no-untyped-def]
        return evaluate_route(
            DEPOT_POINT, depart, load, specs, DEPOT_POINT, capacity, PARAMS, constant_travel()
        )

    def test_early_arrival_waits_until_window_opens(self) -> None:
        # llegada 370; ventana abre 400 -> espera 30; servicio 5 -> sale 405; regreso 415
        ev = self.run([spec("A", 400, 500, kg=300)])
        stop = ev.timings[0]
        assert (stop.arrival_min, stop.service_start_min, stop.departure_min) == (370, 400, 405)
        assert (stop.wait_min, stop.delay_min) == (30, 0)
        assert ev.return_arrival_min == 415
        # puntaje = viaje 20 + 0,2·30 espera = 26
        assert ev.score == pytest.approx(26.0)
        assert ev.capacity_ok

    def test_late_arrival_is_penalized_20_per_minute(self) -> None:
        # llegada 370; ventana termina 360 -> retraso 10; sin espera; sale 375; regreso 385
        ev = self.run([spec("A", 300, 360, kg=300)])
        stop = ev.timings[0]
        assert stop.delay_min == 10 and stop.is_late
        assert ev.late_stops == 1
        assert ev.score == pytest.approx(20 + 20 * 10)

    def test_two_stops_chain_departure_to_arrival(self) -> None:
        # A: llega 370 sale 375. B: llega 385 (ventana 380-390) sale 390. regreso 400
        ev = self.run([spec("A", 360, 400, kg=100), spec("B", 380, 390, kg=200)])
        a, b = ev.timings
        assert (a.arrival_min, a.departure_min) == (370, 375)
        assert (b.arrival_min, b.departure_min) == (385, 390)
        assert b.load_after_kg == 0
        assert ev.return_arrival_min == 400
        assert ev.km == 15

    def test_overtime_after_shift_end_costs_2_per_minute(self) -> None:
        late_start = 17 * 60 - 5  # sale 16:55; llegada 17:05; sale 17:10; regreso 17:20
        ev = self.run([spec("A", 0, 1400, kg=300)], depart=late_start)
        assert ev.overtime_min == pytest.approx(20.0)
        assert ev.score == pytest.approx(20 + 2 * 20)

    def test_load_above_capacity_marks_plan_as_infeasible(self) -> None:
        ev = self.run([spec("A", 0, 1400, kg=300)], load=5000.0, capacity=4050.0)
        assert not ev.capacity_ok

    def test_delivering_more_than_on_board_is_infeasible(self) -> None:
        ev = self.run([spec("A", 0, 1400, kg=500)], load=300.0)
        assert not ev.capacity_ok

    def test_empty_route_returns_immediately(self) -> None:
        ev = self.run([], load=0.0)
        assert ev.return_arrival_min == 360 and ev.score == 0

    def test_broken_vehicle_does_not_return(self) -> None:
        ev = evaluate_route(
            DEPOT_POINT,
            400,
            0,
            [],
            DEPOT_POINT,
            4050,
            PARAMS,
            constant_travel(),
            return_to_depot=False,
        )
        assert ev.return_arrival_min == 400 and ev.km == 0


def test_points_helper_is_inside_the_city() -> None:
    assert all(point(i).is_in_urban_area() for i in range(50))
