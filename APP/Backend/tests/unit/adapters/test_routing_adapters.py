"""Adaptadores de ruteo: reloj acelerado, tiempos de viaje, datos sintéticos y solver."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fleetplanner.adapters.outbound.clock import BOGOTA_TZ, SimulatedClock
from fleetplanner.adapters.outbound.demo_data import (
    DemoRoutingInputsReader,
    routing_reader_for_slug,
)
from fleetplanner.adapters.outbound.demo_data.routing_dataset import PROFILE_A
from fleetplanner.adapters.outbound.persistence_memory import InMemoryRoutingRepository
from fleetplanner.adapters.outbound.solver import OrToolsRoutingSolver
from fleetplanner.adapters.outbound.traffic import (
    DEFAULT_SPEED_PROFILE,
    SimulatedTrafficProvider,
    SpeedProfileTimeEstimator,
)
from fleetplanner.application.ports.outbound.routing import TrafficProviderUnavailable
from fleetplanner.domain.routing.events import (
    BreakdownData,
    Closure,
    EventType,
    OperationalEvent,
)
from fleetplanner.domain.routing.geo import GeoPoint, haversine_km
from fleetplanner.domain.routing.heuristic import solve_with_heuristic
from fleetplanner.domain.routing.models import VehicleKind
from fleetplanner.domain.routing.plan import RoutePlan
from fleetplanner.domain.routing.problem import (
    RoutingProblem,
    VehicleSlot,
    evaluate_solution,
    make_node,
    solution_score,
)
from fleetplanner.domain.shared.errors import ConflictError, InvalidValueError, NotFoundError
from routing_builders import (
    DEPOT_POINT,
    PARAMS,
    haversine_travel,
    node,
    point,
    problem,
    slot,
)

START = datetime(2026, 10, 14, 5, 0, tzinfo=BOGOTA_TZ)


class FakeMonotonic:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class TestSimulatedClock:
    def make(self, **kw):  # type: ignore[no-untyped-def]
        mono = FakeMonotonic()
        return SimulatedClock(START, monotonic=mono, **kw), mono

    def test_starts_paused_and_does_not_move_with_real_time(self) -> None:
        clock, mono = self.make()
        mono.t += 600
        assert clock.now() == START and clock.status().paused

    def test_one_real_minute_is_thirty_simulated_minutes_by_default(self) -> None:
        clock, mono = self.make()
        clock.resume()
        mono.t += 60
        assert clock.now() == START + timedelta(minutes=30)

    def test_pausing_freezes_the_current_instant(self) -> None:
        clock, mono = self.make()
        clock.resume()
        mono.t += 30
        clock.pause()
        frozen = clock.now()
        mono.t += 500
        assert clock.now() == frozen == START + timedelta(minutes=15)

    def test_changing_speed_does_not_jump_the_time(self) -> None:
        clock, mono = self.make()
        clock.resume()
        mono.t += 60  # +30 min
        clock.set_speed(60)
        assert clock.now() == START + timedelta(minutes=30)
        mono.t += 60  # +60 min a la nueva velocidad
        assert clock.now() == START + timedelta(minutes=90)

    def test_advance_moves_forward_even_when_paused(self) -> None:
        clock, _ = self.make()
        clock.advance(45)
        assert clock.now() == START + timedelta(minutes=45) and clock.status().paused

    def test_reset_returns_to_the_start_and_pauses(self) -> None:
        clock, mono = self.make()
        clock.resume()
        mono.t += 120
        clock.reset(START)
        assert clock.now() == START and clock.status().paused

    def test_naive_datetimes_and_non_positive_speeds_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="zona horaria"):
            SimulatedClock(datetime(2026, 1, 1))
        clock, _ = self.make()
        with pytest.raises(ValueError, match="positiva"):
            clock.set_speed(0)


class TestTrafficTimes:
    a, b = GeoPoint(4.60, -74.10), GeoPoint(4.65, -74.10)

    def test_distance_is_haversine_times_1_35(self) -> None:
        leg = SpeedProfileTimeEstimator().estimate(self.a, self.b, 360, [])
        assert leg.km == pytest.approx(haversine_km(self.a, self.b) * 1.35)

    def test_minutes_follow_the_speed_of_the_departure_hour(self) -> None:
        est = SpeedProfileTimeEstimator()
        leg = est.estimate(self.a, self.b, 6 * 60 + 10, [])  # 06:10 -> 24 km/h
        assert leg.minutes == pytest.approx(leg.km / DEFAULT_SPEED_PROFILE[6] * 60)
        peak = est.estimate(self.a, self.b, 8 * 60, [])  # 08:00 -> 16 km/h
        assert peak.minutes > leg.minutes

    def test_an_active_closure_multiplies_the_time_only_while_active(self) -> None:
        est = SpeedProfileTimeEstimator()
        closure = Closure("E1", "Calle 80", self.a, 2.5, 2.5, 495, 750)
        base = est.estimate(self.a, self.b, 500, []).minutes
        assert est.estimate(self.a, self.b, 500, [closure]).minutes == pytest.approx(base * 2.5)
        assert est.estimate(self.a, self.b, 480, [closure]).minutes == pytest.approx(
            est.estimate(self.a, self.b, 480, []).minutes
        )

    def test_closure_far_away_has_no_effect(self) -> None:
        est = SpeedProfileTimeEstimator()
        far = Closure("E2", "Lejos", GeoPoint(4.80, -74.00), 1.0, 5.0, 0, 1440)
        assert est.estimate(self.a, self.b, 500, [far]).minutes == pytest.approx(
            est.estimate(self.a, self.b, 500, []).minutes
        )

    def test_provider_adds_simulated_congestion_in_rush_hours_only(self) -> None:
        provider, fallback = SimulatedTrafficProvider(), SpeedProfileTimeEstimator()
        rush = provider.estimate(self.a, self.b, 8 * 60, []).minutes
        assert rush == pytest.approx(fallback.estimate(self.a, self.b, 8 * 60, []).minutes * 1.15)
        calm = provider.estimate(self.a, self.b, 10 * 60, []).minutes
        assert calm == pytest.approx(fallback.estimate(self.a, self.b, 10 * 60, []).minutes)

    def test_provider_can_be_switched_off_and_on(self) -> None:
        provider = SimulatedTrafficProvider()
        provider.set_available(False)
        assert not provider.is_available()
        with pytest.raises(TrafficProviderUnavailable):
            provider.estimate(self.a, self.b, 360, [])
        provider.set_available(True)
        assert provider.estimate(self.a, self.b, 360, []).minutes > 0

    def test_fallback_never_fails(self) -> None:
        assert SpeedProfileTimeEstimator().estimate(self.a, self.b, 360, []).minutes > 0

    def test_speed_profile_must_be_complete_and_between_5_and_90(self) -> None:
        with pytest.raises(InvalidValueError, match="24 horas"):
            SpeedProfileTimeEstimator({0: 30.0})
        bad = {**DEFAULT_SPEED_PROFILE, 3: 120.0}
        with pytest.raises(InvalidValueError, match="entre 5 y 90"):
            SpeedProfileTimeEstimator(bad)


class TestRoutingRepository:
    def test_ids_are_sequential_per_prefix_and_reset_restarts_them(self) -> None:
        repo = InMemoryRoutingRepository()
        assert [repo.next_id("EV"), repo.next_id("EV"), repo.next_id("PR")] == [
            "EV-001",
            "EV-002",
            "PR-001",
        ]
        repo.reset(START.date(), [])
        assert repo.next_id("EV") == "EV-001"

    def test_updating_an_unknown_event_fails(self) -> None:
        repo = InMemoryRoutingRepository()
        event = OperationalEvent(
            "EV-9", EventType.BREAKDOWN, START, 0, "x", "s", BreakdownData("V")
        )
        with pytest.raises(NotFoundError):
            repo.update_event(event)

    def test_plans_are_append_only_and_consecutive(self) -> None:
        repo = InMemoryRoutingRepository()
        assert repo.active_plan() is None
        with pytest.raises(ConflictError):
            repo.add_plan(RoutePlan(2, 1, START, "x", "r", ()))


class TestDemoRoutingData:
    def test_empresa_a_matches_the_documented_size(self) -> None:
        data = DemoRoutingInputsReader(PROFILE_A).read()
        assert len(data.customers) == 36 and len(data.orders) == 36
        own = [v for v in data.vehicles if v.kind is VehicleKind.OWN]
        assert len(own) == 4 and all(v.vehicle_type == "turbo" for v in own)
        assert {v.kind for v in data.vehicles} == {
            VehicleKind.OWN,
            VehicleKind.RESERVE,
            VehicleKind.THIRD_PARTY,
        }

    def test_is_reproducible_with_the_same_seed(self) -> None:
        assert (
            DemoRoutingInputsReader(PROFILE_A).read() == DemoRoutingInputsReader(PROFILE_A).read()
        )

    def test_companies_have_different_data_and_size(self) -> None:
        a = routing_reader_for_slug("empresa-demo-a").read()
        b = routing_reader_for_slug("empresa-demo-b").read()
        assert len(a.customers) != len(b.customers)
        assert {c.point for c in a.customers} != {c.point for c in b.customers}

    def test_unknown_company_gets_a_stable_derived_profile(self) -> None:
        one = routing_reader_for_slug("nueva-empresa").read()
        two = routing_reader_for_slug("nueva-empresa").read()
        assert one == two

    def test_every_customer_is_valid_unique_and_in_the_city(self) -> None:
        data = DemoRoutingInputsReader(PROFILE_A).read()
        assert len({c.code for c in data.customers}) == 36
        assert not any(c.needs_location_review for c in data.customers)
        assert all(o.kg > 0 and o.window.end_min > o.window.start_min for o in data.orders)
        assert len({o.id for o in data.orders}) == 36

    def test_total_demand_fits_the_active_fleet(self) -> None:
        data = DemoRoutingInputsReader(PROFILE_A).read()
        demand = sum(o.kg for o in data.orders)
        capacity = sum(
            PARAMS.operational_capacity_kg(v) for v in data.vehicles if v.kind is VehicleKind.OWN
        )
        assert demand < capacity


@pytest.mark.parametrize("use_ortools", [True, False], ids=["ortools", "heuristica"])
class TestRoutingSolverContract:
    """Cualquier motor debe respetar capacidad, asignar lo asignable y explicar lo demás."""

    @staticmethod
    def solve(use_ortools: bool, prob: RoutingProblem):  # type: ignore[no-untyped-def]
        if use_ortools:
            return OrToolsRoutingSolver().solve(prob, 3.0)
        return solve_with_heuristic(prob)

    def test_assigns_every_order_within_capacity(self, use_ortools: bool) -> None:
        nodes = [node(f"P{i}", i, kg=400) for i in range(1, 11)]
        prob = problem(nodes, [slot("V1"), slot("V2")])
        sol = self.solve(use_ortools, prob)
        assert sol.unassigned == {}
        assert sorted(i for ids in sol.routes.values() for i in ids) == sorted(n.id for n in nodes)
        assert all(e.capacity_ok for e in evaluate_solution(prob, sol).values())

    def test_overweight_orders_are_left_out_with_a_reason(self, use_ortools: bool) -> None:
        nodes = [node("A", 1, kg=3000), node("B", 2, kg=3000), node("C", 3, kg=100)]
        prob = problem(nodes, [slot("V1")])
        sol = self.solve(use_ortools, prob)
        assert sol.assigned_count == 2 and len(sol.unassigned) == 1
        assert all(e.capacity_ok for e in evaluate_solution(prob, sol).values())
        assert all(reason for reason in sol.unassigned.values())

    def test_no_vehicles_means_nothing_is_assigned(self, use_ortools: bool) -> None:
        sol = self.solve(use_ortools, problem([node("A", 1)], []))
        assert sol.routes == {} and "A" in sol.unassigned

    def test_respects_time_windows_when_possible(self, use_ortools: bool) -> None:
        early = node("E", 1, kg=100, start=420, end=480)
        late = node("L", 2, kg=100, start=600, end=700)
        prob = problem([early, late], [slot("V1")])
        sol = self.solve(use_ortools, prob)
        evaluation = next(iter(evaluate_solution(prob, sol).values()))
        assert evaluation.delay_min == 0
        assert sol.routes["V1"][0] == "E"


class TestSolverComparison:
    def test_both_engines_are_feasible_on_the_demo_day_and_scores_are_comparable(self) -> None:
        data = DemoRoutingInputsReader(PROFILE_A).read()
        customers = {c.code: c for c in data.customers}
        nodes = tuple(make_node(o, customers[o.customer_code], PARAMS) for o in data.orders)
        slots = tuple(
            VehicleSlot(v, PARAMS.operational_capacity_kg(v), DEPOT_POINT, PARAMS.departure_min)
            for v in data.vehicles
            if v.kind is VehicleKind.OWN
        )
        prob = RoutingProblem(DEPOT_POINT, slots, nodes, PARAMS, haversine_travel(22.0))
        exact = OrToolsRoutingSolver().solve(prob, 2.0)
        heur = solve_with_heuristic(prob)
        for sol in (exact, heur):
            assert sol.unassigned == {}
            assert all(e.capacity_ok for e in evaluate_solution(prob, sol).values())
        # no se afirma que uno gane siempre; solo que ambos puntajes son finitos y positivos
        assert 0 < solution_score(prob, exact) < float("inf")
        assert 0 < solution_score(prob, heur) < float("inf")


def test_helper_points_exist() -> None:
    assert point(1) != point(2)
