"""Seguimiento, congelamiento, cierres viales y heurística de ruteo."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fleetplanner.domain.routing.evaluation import TravelLeg, evaluate_route
from fleetplanner.domain.routing.events import Closure, closure_factor
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.heuristic import optimize_sequence, solve_with_heuristic
from fleetplanner.domain.routing.plan import (
    RouteAnchor,
    RoutePlan,
    RouteStatus,
    VehicleRoute,
    freeze_route,
    make_route,
    view_route,
)
from fleetplanner.domain.routing.problem import evaluate_solution, solution_score
from fleetplanner.domain.routing.tracking import VehicleStatus
from fleetplanner.domain.shared.errors import InvalidValueError
from routing_builders import (
    DEPOT_POINT,
    PARAMS,
    constant_travel,
    haversine_travel,
    node,
    point,
    problem,
    slot,
    spec,
)


def route_for(specs, load=300.0):  # type: ignore[no-untyped-def]
    travel = constant_travel()
    ev = evaluate_route(DEPOT_POINT, 360, load, specs, DEPOT_POINT, 4050, PARAMS, travel)
    return VehicleRoute(
        vehicle_id="V-1",
        plate="PL-1",
        vehicle_type="turbo",
        capacity_kg=4050,
        anchor=RouteAnchor(DEPOT_POINT, 360, "CEDI"),
        initial_load_kg=load,
        frozen=(),
        pending=tuple(specs),
        evaluation=ev,
    ), travel


class TestTracking:
    def test_vehicle_waits_at_depot_before_departure(self) -> None:
        route, travel = route_for([spec("A", 0, 1400, kg=300, where=point(1))])
        view = view_route(route, 340, DEPOT_POINT, PARAMS, travel)
        assert view.state.status is VehicleStatus.NOT_STARTED
        assert view.state.point == DEPOT_POINT

    def test_vehicle_is_halfway_after_half_the_leg(self) -> None:
        stop = spec("A", 0, 1400, kg=300, where=point(1))
        route, travel = route_for([stop])
        view = view_route(route, 365, DEPOT_POINT, PARAMS, travel)  # 5 de 10 min de viaje
        assert view.state.status is VehicleStatus.TRAVELING
        assert view.state.point.lat == pytest.approx((DEPOT_POINT.lat + stop.point.lat) / 2)
        assert view.state.next_stop_key == "A"

    def test_serving_then_returning_then_at_depot(self) -> None:
        route, travel = route_for([spec("A", 0, 1400, kg=300, where=point(1))])
        # llega 370, servicio 5 min -> sale 375, regresa 385
        assert (
            view_route(route, 372, DEPOT_POINT, PARAMS, travel).state.status
            is VehicleStatus.SERVING
        )
        returning = view_route(route, 380, DEPOT_POINT, PARAMS, travel).state
        assert returning.status is VehicleStatus.RETURNING and returning.completed_stops == 1
        done = view_route(route, 400, DEPOT_POINT, PARAMS, travel).state
        assert done.status is VehicleStatus.AT_DEPOT and done.point == DEPOT_POINT

    def test_waiting_state_when_arriving_before_window_opens(self) -> None:
        route, travel = route_for([spec("A", 420, 500, kg=300, where=point(1))])
        assert (
            view_route(route, 380, DEPOT_POINT, PARAMS, travel).state.status
            is VehicleStatus.WAITING
        )

    def test_broken_route_stays_where_it_broke(self) -> None:
        route, travel = route_for([spec("A", 0, 1400, kg=300, where=point(1))])
        broken = make_route(
            route,
            (),
            RouteAnchor(point(3), 400, "Avería"),
            0.0,
            (),
            DEPOT_POINT,
            PARAMS,
            travel,
            status=RouteStatus.BROKEN,
        )
        state = view_route(broken, 500, DEPOT_POINT, PARAMS, travel).state
        assert state.status is VehicleStatus.BROKEN and state.point == point(3)


class TestFreeze:
    def test_freezes_what_is_delivered_and_keeps_the_rest_pending(self) -> None:
        a, b, c = (spec(k, 0, 1400, kg=100, where=point(i)) for i, k in enumerate("ABC", 1))
        route, travel = route_for([a, b, c])
        # A: llega 370 sale 375; B: llega 385 sale 390; C: llega 400. En 380 está de camino a B.
        frozen = freeze_route(view_route(route, 380, DEPOT_POINT, PARAMS, travel), 380)
        assert [t.spec.key for t in frozen.frozen] == ["A"]
        assert [s.key for s in frozen.pending] == ["B", "C"]
        assert frozen.load_kg == 200  # 300 - 100 entregados
        assert frozen.anchor.time_min == 380 and frozen.anchor.label == "Posición actual"

    def test_a_stop_in_service_is_frozen_and_anchor_is_its_departure(self) -> None:
        a, b = (spec(k, 0, 1400, kg=100, where=point(i)) for i, k in enumerate("AB", 1))
        route, travel = route_for([a, b])
        frozen = freeze_route(view_route(route, 372, DEPOT_POINT, PARAMS, travel), 372)
        assert [t.spec.key for t in frozen.frozen] == ["A"]
        assert frozen.anchor.time_min == 375 and frozen.anchor.point == a.point

    def test_before_departure_nothing_is_frozen(self) -> None:
        a = spec("A", 0, 1400, kg=100, where=point(1))
        route, travel = route_for([a], load=100)
        frozen = freeze_route(view_route(route, 300, DEPOT_POINT, PARAMS, travel), 300)
        assert frozen.frozen == () and frozen.anchor.time_min == 360
        assert frozen.load_kg == 100

    def test_rebuilt_route_keeps_history_and_reevaluates_from_anchor(self) -> None:
        a, b, c = (spec(k, 0, 1400, kg=100, where=point(i)) for i, k in enumerate("ABC", 1))
        route, travel = route_for([a, b, c])
        frozen = freeze_route(view_route(route, 380, DEPOT_POINT, PARAMS, travel), 380)
        new = make_route(
            route, frozen.frozen, frozen.anchor, frozen.load_kg, [c, b], DEPOT_POINT, PARAMS, travel
        )
        assert [t.spec.key for t in new.frozen] == ["A"]
        assert [t.spec.key for t in new.evaluation.timings] == ["C", "B"]
        assert new.evaluation.timings[0].arrival_min == 390  # 380 + 10


class TestPlanVersioning:
    def test_plan_exposes_routes_and_score(self) -> None:
        route, _ = route_for([spec("A", 0, 1400, kg=300, where=point(1))])
        plan = RoutePlan(
            1, None, datetime(2026, 10, 14, 5, tzinfo=UTC), "sistema", "Plan inicial", (route,)
        )
        assert plan.route_of("V-1") is route and plan.route_of("X") is None
        assert plan.route_carrying("A") is route
        assert plan.score == route.evaluation.score


class TestClosures:
    center = GeoPoint(4.72, -74.10)

    def closure(self, **kw):  # type: ignore[no-untyped-def]
        base = {
            "id": "E1",
            "label": "Calle 80",
            "center": self.center,
            "radius_km": 2.5,
            "factor": 2.5,
            "start_min": 495,
            "end_min": 750,
        }
        return Closure(**{**base, **kw})

    def test_factor_applies_when_midpoint_is_inside_the_radius(self) -> None:
        far_a, far_b = GeoPoint(4.60, -74.20), GeoPoint(4.84, -74.00)  # extremos lejos, medio cerca
        assert closure_factor([self.closure()], far_a, far_b, 500) == 2.5

    def test_no_effect_outside_radius_or_outside_the_time_window(self) -> None:
        a, b = GeoPoint(4.55, -74.05), GeoPoint(4.56, -74.06)
        assert closure_factor([self.closure()], a, b, 500) == 1.0
        assert (
            closure_factor([self.closure()], self.center, self.center, 480) == 1.0
        )  # antes de 08:15
        assert closure_factor([self.closure()], self.center, self.center, 750) == 1.0  # ya terminó

    def test_with_two_closures_the_larger_factor_applies(self) -> None:
        both = [self.closure(factor=2.0), self.closure(id="E2", factor=3.0)]
        assert closure_factor(both, self.center, self.center, 600) == 3.0

    def test_invalid_closure_is_rejected(self) -> None:
        with pytest.raises(InvalidValueError):
            self.closure(radius_km=0)
        with pytest.raises(InvalidValueError):
            self.closure(factor=0.5)
        with pytest.raises(InvalidValueError):
            self.closure(end_min=400)


class TestHeuristic:
    def test_optimize_sequence_fixes_a_bad_order(self) -> None:
        # puntos en línea (0..4): el orden 4,0,3,1,2 es malo; el óptimo recorre en línea
        specs = [spec(str(i), 0, 1400, kg=50, where=point(i)) for i in (4, 0, 3, 1, 2)]
        travel = haversine_travel()

        def evaluate(seq):  # type: ignore[no-untyped-def]
            return evaluate_route(DEPOT_POINT, 360, 250, seq, DEPOT_POINT, 4050, PARAMS, travel)

        best = optimize_sequence([], specs, evaluate)
        assert evaluate(best).score <= evaluate(specs).score
        assert evaluate(best).score < evaluate(specs).score  # mejora estricta

    def test_prefix_stays_in_front(self) -> None:
        pre = spec("P", 0, 1400, kg=10, where=point(9))
        free = [spec(str(i), 0, 1400, kg=10, where=point(i)) for i in (1, 2, 3)]
        travel = haversine_travel()

        def evaluate(seq):  # type: ignore[no-untyped-def]
            return evaluate_route(DEPOT_POINT, 360, 40, seq, DEPOT_POINT, 4050, PARAMS, travel)

        assert optimize_sequence([pre], free, evaluate)[0] in free

    def test_assigns_every_order_when_capacity_allows(self) -> None:
        nodes = [node(f"P{i}", i, kg=300) for i in range(1, 9)]
        prob = problem(nodes, [slot("V1"), slot("V2")])
        sol = solve_with_heuristic(prob)
        assert sol.unassigned == {}
        assert sorted(i for ids in sol.routes.values() for i in ids) == sorted(n.id for n in nodes)
        assert all(e.capacity_ok for e in evaluate_solution(prob, sol).values())

    def test_is_deterministic(self) -> None:
        nodes = [node(f"P{i}", i, kg=250) for i in range(1, 11)]
        prob = problem(nodes, [slot("V1"), slot("V2"), slot("V3")])
        assert solve_with_heuristic(prob).routes == solve_with_heuristic(prob).routes

    def test_capacity_is_respected_and_the_excess_is_explained(self) -> None:
        nodes = [node(f"P{i}", i, kg=2000) for i in range(1, 5)]  # 8 t; un turbo carga 4,05 t
        prob = problem(nodes, [slot("V1")])
        sol = solve_with_heuristic(prob)
        assert sol.assigned_count == 2
        assert len(sol.unassigned) == 2
        assert all("capacidad" in reason for reason in sol.unassigned.values())
        assert all(e.capacity_ok for e in evaluate_solution(prob, sol).values())

    def test_order_heavier_than_any_vehicle_is_reported_with_its_weight(self) -> None:
        prob = problem([node("PESADO", 1, kg=9000)], [slot("V1")])
        sol = solve_with_heuristic(prob)
        assert "9000 kg" in sol.unassigned["PESADO"]

    def test_unreachable_window_is_explained(self) -> None:
        prob = problem(
            [node("TEMPRANO", 1, kg=100, start=100, end=200)], [slot("V1", start_min=360)]
        )
        sol = solve_with_heuristic(prob)
        # sale a las 06:00 y la ventana cerró a las 03:20: se asigna, con retraso y puntaje alto
        score = solution_score(prob, sol)
        assert sol.assigned_count == 1 and score >= 20 * 100

    def test_travel_leg_is_a_value_object(self) -> None:
        assert TravelLeg(1.0, 2.0) == TravelLeg(1.0, 2.0)
