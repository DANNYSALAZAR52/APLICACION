"""Flujos del ruteo dinámico de punta a punta (sin HTTP): plan, eventos, propuestas y versiones."""

from __future__ import annotations

import pytest

from fleetplanner.application.dto.routing import (
    BreakdownCommand,
    ChangeWindowCommand,
    CloseRoadCommand,
    SimControl,
    SimControlAction,
    UrgentOrderCommand,
)
from fleetplanner.domain.routing.events import EventType, ProposalStatus
from fleetplanner.domain.routing.plan import RouteStatus
from fleetplanner.domain.routing.tracking import VehicleStatus
from fleetplanner.domain.shared.errors import ConflictError, InvalidValueError, NotFoundError
from routing_flow_helpers import Flow, cust, custom, force_plan, seeded

H = 60


def started(flow: Flow):  # type: ignore[no-untyped-def]
    if flow.ws.core.repo.active_plan() is not None:
        return flow.ws.core.repo.active_plan()
    return flow.ws.day.start("test")


class TestMorningPlan:
    def test_version_1_assigns_every_order_within_capacity(self) -> None:
        flow = seeded(customers=10, vehicles=2)
        plan = started(flow)
        assert plan.version == 1 and plan.base_version is None
        assigned = [i for r in plan.routes for i in r.pending_order_ids()]
        assert sorted(assigned) == sorted(flow.ws.core.repo.orders())
        assert plan.unassigned == ()
        for route in plan.routes:
            assert route.evaluation.capacity_ok
            assert route.initial_load_kg <= route.capacity_kg

    def test_reserve_and_third_party_start_in_standby_without_stops(self) -> None:
        plan = started(seeded())
        standby = [r for r in plan.routes if r.status is RouteStatus.STANDBY]
        assert {r.vehicle_id for r in standby} == {"V-03", "V-TER"}
        assert all(not r.pending for r in standby)

    def test_plan_keeps_both_engines_when_both_run(self) -> None:
        # con el doble de prueba el "solver" es la misma heurística: igual aparecen dos filas
        plan = started(seeded())
        assert len(plan.comparison) == 2
        assert sum(1 for c in plan.comparison if c.chosen) == 1

    def test_cannot_build_a_second_plan_for_the_same_day(self) -> None:
        flow = seeded()
        started(flow)
        with pytest.raises(ConflictError, match="reinicie"):
            flow.ws.build_plan.execute("test")

    def test_restarting_the_day_discards_events_and_builds_version_1_again(self) -> None:
        flow = seeded()
        started(flow)
        flow.at(7)
        flow.ws.handle_event.execute("d", CloseRoadCommand("Calle 80", 4.72, -74.10, 2.5, 2.5, 120))
        plan = flow.ws.day.start("d")
        assert plan.version == 1
        assert flow.ws.core.repo.events() == [] and flow.ws.core.repo.closures() == []

    def test_day_starts_paused_at_0500(self) -> None:
        flow = seeded()
        started(flow)
        status = flow.container.clock.status()
        assert status.paused and (status.now.hour, status.now.minute) == (5, 0)


class TestVersionImmutability:
    def test_repository_rejects_a_non_consecutive_version(self) -> None:
        flow = seeded()
        plan = started(flow)
        from dataclasses import replace

        with pytest.raises(ConflictError, match="siguiente"):
            flow.ws.core.repo.add_plan(replace(plan, version=5))
        with pytest.raises(ConflictError):
            flow.ws.core.repo.add_plan(plan)  # repetir la 1 tampoco se permite


def closure_case() -> Flow:
    """Plan forzado P1→P2. P2 tiene una ventana corta (08:00–08:30); P1 queda dentro del cierre.

    Sin el cierre, P1→P2 llega a tiempo. Con el cierre sobre P1 (los tramos que lo tocan se
    triplican), ese orden llega muy tarde a P2 y conviene atender primero P2.
    """
    p1 = cust("C-1", 4.678, -74.155, 6 * H + 30, 18 * H)
    p2 = cust("C-2", 4.600, -74.080, 8 * H, 8 * H + 30)
    flow = custom([p1, p2], [500.0, 300.0], vehicles=1)
    force_plan(flow, {"V-01": ["P-001", "P-002"]})
    return flow


class TestRoadClosure:
    def test_closure_forces_a_resequence_and_removes_the_lateness(self) -> None:
        flow = closure_case()
        plan = started(flow)
        assert [s.order_id for s in plan.route_of("V-01").pending] == ["P-001", "P-002"]
        flow.at(6, 15)
        result = flow.ws.handle_event.execute(
            "desp", CloseRoadCommand("Calle de prueba", 4.678, -74.155, 1.0, 3.0, 300)
        )
        proposal = result.proposal
        assert proposal.status is ProposalStatus.PENDING
        assert proposal.impact.late_stops_before >= 1
        assert proposal.impact.late_stops_after == 0
        assert proposal.impact.delay_min_after < proposal.impact.delay_min_before
        new_route = proposal.proposed_plan.route_of("V-01")
        assert [s.order_id for s in new_route.pending] == ["P-002", "P-001"]
        assert proposal.impact.affected_vehicles == ("V-01",)

    def test_proposing_does_not_change_the_active_plan(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        flow.ws.handle_event.execute("d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300))
        assert flow.ws.core.repo.active_plan().version == 1

    def test_approval_creates_version_2_and_keeps_version_1_intact(self) -> None:
        flow = closure_case()
        v1 = started(flow)
        flow.at(6, 15)
        proposal = flow.ws.handle_event.execute(
            "d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300)
        ).proposal
        decision = flow.ws.approve.execute("jefe", proposal.id, True, "adelante")
        assert decision.plan.version == 2 and decision.plan.base_version == 1
        assert decision.plan.created_by == "jefe"
        assert decision.proposal.status is ProposalStatus.APPROVED
        assert decision.proposal.applied_version == 2
        stored = flow.ws.core.repo.plans()
        assert [p.version for p in stored] == [1, 2]
        assert stored[0] == v1  # la versión 1 no se tocó
        assert [s.order_id for s in stored[0].route_of("V-01").pending] == ["P-001", "P-002"]

    def test_rejection_keeps_the_plan_and_records_who_decided(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        proposal = flow.ws.handle_event.execute(
            "d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300)
        ).proposal
        decision = flow.ws.approve.execute("jefe", proposal.id, False, "no")
        assert decision.plan is None
        assert decision.proposal.status is ProposalStatus.REJECTED
        assert decision.proposal.decided_by == "jefe" and decision.proposal.decision_comment == "no"
        assert flow.ws.core.repo.active_plan().version == 1

    def test_a_decided_proposal_cannot_be_decided_again(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        proposal = flow.ws.handle_event.execute(
            "d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300)
        ).proposal
        flow.ws.approve.execute("jefe", proposal.id, False)
        with pytest.raises(ConflictError):
            flow.ws.approve.execute("jefe", proposal.id, True)

    def test_clock_is_paused_while_a_proposal_waits(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        flow.container.clock.resume()
        flow.ws.handle_event.execute("d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300))
        assert flow.container.clock.status().paused

    def test_closure_far_from_every_route_needs_no_changes(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        result = flow.ws.handle_event.execute(
            "d", CloseRoadCommand("lejos", 4.80, -74.00, 0.5, 3.0, 60)
        )
        assert result.proposal.status is ProposalStatus.NONE_NEEDED
        assert result.proposal.proposed_plan is None

    def test_event_is_recorded_with_actor_and_linked_to_its_proposal(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        result = flow.ws.handle_event.execute(
            "desp", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300)
        )
        assert result.event.created_by == "desp" and result.event.type is EventType.ROAD_CLOSURE
        assert result.event.proposal_ids == (result.proposal.id,)
        assert flow.ws.core.repo.events()[0].id == result.event.id

    def test_invalid_closure_inputs_are_rejected_with_a_message(self) -> None:
        flow = closure_case()
        started(flow)
        with pytest.raises(InvalidValueError, match="latitud 40"):
            flow.ws.handle_event.execute("d", CloseRoadCommand("x", 40.0, -74.1, 1.0, 2.0, 60))
        with pytest.raises(InvalidValueError, match="nombre del cierre"):
            flow.ws.handle_event.execute("d", CloseRoadCommand(" ", 4.7, -74.1, 1.0, 2.0, 60))


class TestStaleProposals:
    def test_approving_after_the_plan_changed_regenerates_instead_of_applying(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        first = flow.ws.handle_event.execute(
            "d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300)
        ).proposal
        # otra decisión cambia el plan antes de que se resuelva la primera
        flow.ws.core.repo.add_plan(
            __import__("dataclasses").replace(
                flow.ws.core.repo.active_plan(), version=2, base_version=1
            )
        )
        result = flow.ws.approve.execute("jefe", first.id, True)
        assert result.plan is None
        assert result.proposal.status is ProposalStatus.SUPERSEDED
        assert result.replacement is not None
        assert result.replacement.status is ProposalStatus.PENDING
        assert result.replacement.base_version == 2
        assert flow.ws.core.repo.active_plan().version == 2  # nada se aplicó a ciegas

    def test_approving_after_the_clock_moved_a_lot_regenerates(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        first = flow.ws.handle_event.execute(
            "d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300)
        ).proposal
        flow.container.clock.advance(20)
        result = flow.ws.approve.execute("jefe", first.id, True)
        assert result.replacement is not None and result.plan is None


class TestUrgentOrder:
    def test_chooses_the_cheapest_viable_option_and_compares_reserve(self) -> None:
        flow = seeded(customers=8, vehicles=2)
        started(flow)
        flow.at(7)
        result = flow.ws.handle_event.execute(
            "d", UrgentOrderCommand("C-003", 300, 1.0, 8 * H, 16 * H)
        )
        proposal = result.proposal
        assert proposal.status is ProposalStatus.PENDING
        assert any("Se compararon" in n for n in proposal.impact.notes)
        plan = proposal.proposed_plan
        carriers = [r for r in plan.routes if "URG-001" in r.pending_order_ids()]
        assert len(carriers) == 1
        # el urgente se entrega dentro de su ventana
        stop = next(t for t in carriers[0].evaluation.timings if t.spec.order_id == "URG-001")
        assert stop.delay_min == 0
        assert proposal.impact.activates_reserve == (
            carriers[0].status is RouteStatus.ACTIVE and carriers[0].vehicle_id in {"V-03", "V-TER"}
        )

    def test_urgent_order_is_registered_so_it_can_be_found_later(self) -> None:
        flow = seeded(customers=8, vehicles=2)
        started(flow)
        flow.at(7)
        flow.ws.handle_event.execute("d", UrgentOrderCommand("C-003", 300, 1.0, 8 * H, 16 * H))
        order = flow.ws.core.repo.orders()["URG-001"]
        assert order.urgent and order.priority == 1

    def test_if_nothing_is_viable_the_order_is_postponed_and_flagged(self) -> None:
        flow = seeded(customers=8, vehicles=2)
        started(flow)
        flow.at(9)
        # ventana que cierra en 30 min: ningún vehículo recarga en el CEDI y llega a tiempo
        result = flow.ws.handle_event.execute(
            "d", UrgentOrderCommand("C-003", 300, 1.0, 9 * H, 9 * H + 30)
        )
        impact = result.proposal.impact
        assert impact.unattended_orders == ("URG-001",)
        assert result.proposal.requires_confirmation
        assert "día siguiente" in result.proposal.summary
        decision = flow.ws.approve.execute("d", result.proposal.id, True)
        assert any(u.order_id == "URG-001" for u in decision.plan.unassigned)

    def test_unknown_customer_and_expired_window_are_rejected(self) -> None:
        flow = seeded(customers=8, vehicles=2)
        started(flow)
        flow.at(9)
        with pytest.raises(NotFoundError):
            flow.ws.handle_event.execute("d", UrgentOrderCommand("NO-EXISTE", 100, 1, 600, 900))
        with pytest.raises(InvalidValueError, match="ya terminó"):
            flow.ws.handle_event.execute("d", UrgentOrderCommand("C-001", 100, 1, 6 * H, 8 * H))


class TestWindowChange:
    def test_delivered_orders_cannot_change_window(self) -> None:
        flow = seeded(customers=8, vehicles=2)
        plan = started(flow)
        first = plan.routes[0].pending[0].order_id
        flow.at(16)
        with pytest.raises(ConflictError, match="ya fue entregado"):
            flow.ws.handle_event.execute("d", ChangeWindowCommand(first, 17 * H, 18 * H))

    def test_unknown_order_is_not_found(self) -> None:
        flow = seeded()
        started(flow)
        with pytest.raises(NotFoundError):
            flow.ws.handle_event.execute("d", ChangeWindowCommand("NOPE", 8 * H, 9 * H))

    def test_new_window_is_applied_to_the_pending_stop_even_if_the_plan_is_unchanged(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6)
        flow.ws.handle_event.execute("d", ChangeWindowCommand("P-001", 9 * H, 10 * H))
        snap = flow.ws.snapshot.execute()
        stop = next(s for s in snap.stops if s.order_id == "P-001")
        assert (stop.window_start_min, stop.window_end_min) == (9 * H, 10 * H)


class TestBreakdown:
    def test_reserve_takes_the_cargo_after_a_25_minute_transfer(self) -> None:
        flow = seeded(customers=10, vehicles=2)
        started(flow)
        flow.at(8)
        result = flow.ws.handle_event.execute("d", BreakdownCommand("V-01"))
        proposal = result.proposal
        assert proposal.requires_confirmation and proposal.impact.activates_reserve
        assert proposal.impact.reserve_vehicle == "V-03"
        plan = proposal.proposed_plan
        assert plan.route_of("V-01").status is RouteStatus.BROKEN
        assert plan.route_of("V-01").pending == ()
        reserve = plan.route_of("V-03")
        transfer = reserve.evaluation.timings[0]
        assert transfer.spec.kind.value == "transfer"
        assert transfer.departure_min - transfer.service_start_min == pytest.approx(25.0)
        delivered_by_reserve = reserve.pending_order_ids()
        assert delivered_by_reserve  # atiende lo que le quedaba al averiado
        assert proposal.impact.unattended_before == len(delivered_by_reserve)

    def test_cargo_never_moves_between_vehicles_without_a_transfer(self) -> None:
        flow = seeded(customers=10, vehicles=2)
        v1 = started(flow)
        flow.at(8)
        proposal = flow.ws.handle_event.execute("d", BreakdownCommand("V-01")).proposal
        plan = proposal.proposed_plan
        moved = set(v1.route_of("V-01").pending_order_ids()) & set(
            plan.route_of("V-03").pending_order_ids()
        )
        for order_id in moved:
            # solo puede estar en la reserva si esa ruta empieza con un transbordo
            assert plan.route_of("V-03").pending[0].kind.value == "transfer"
            assert order_id not in plan.route_of("V-02").pending_order_ids()

    def test_after_approval_the_broken_vehicle_stays_put(self) -> None:
        flow = seeded(customers=10, vehicles=2)
        started(flow)
        flow.at(8)
        proposal = flow.ws.handle_event.execute("d", BreakdownCommand("V-01")).proposal
        flow.ws.approve.execute("d", proposal.id, True)
        snap = flow.ws.snapshot.execute()
        broken = next(v for v in snap.vehicles if v.id == "V-01")
        assert broken.status == VehicleStatus.BROKEN.value
        assert any(a.code == "breakdown" for a in snap.alerts)

    def test_without_capacity_in_any_reserve_the_deliveries_are_flagged(self) -> None:
        c1 = cust("C-1", 4.70, -74.12, 7 * H, 18 * H)
        c2 = cust("C-2", 4.62, -74.15, 7 * H, 18 * H)
        flow = custom(
            [c1, c2], [3000.0, 900.0], vehicles=1, reserve_capacity=1000.0, third_capacity=None
        )
        started(flow)
        flow.at(6, 15)
        proposal = flow.ws.handle_event.execute("d", BreakdownCommand("V-01")).proposal
        assert set(proposal.impact.unattended_orders) == {"P-001", "P-002"}
        assert not proposal.impact.activates_reserve
        assert "sin atender" in proposal.summary

    def test_only_a_vehicle_in_operation_can_break_down(self) -> None:
        flow = seeded()
        started(flow)
        flow.at(8)
        with pytest.raises(ConflictError, match="no está en operación"):
            flow.ws.handle_event.execute("d", BreakdownCommand("V-03"))
        with pytest.raises(NotFoundError):
            flow.ws.handle_event.execute("d", BreakdownCommand("V-99"))
        assert flow.ws.core.repo.events() == []  # los intentos fallidos no dejan eventos huérfanos


class TestTravelProviderFailure:
    """Criterio 12: si falla el proveedor de tiempos se usa el perfil y se avisa."""

    def test_fallback_is_used_and_the_notice_is_shown(self) -> None:
        flow = seeded()
        started(flow)
        flow.ws.day.control(SimControl(SimControlAction.PROVIDER, 0.0))
        snap = flow.ws.snapshot.execute()
        assert snap.travel_notice == "Tiempos estimados sin tráfico"
        assert snap.provider_available is False
        assert any(a.code == "degraded_times" for a in snap.alerts)

    def test_notice_disappears_when_the_provider_comes_back(self) -> None:
        flow = seeded()
        started(flow)
        flow.ws.day.control(SimControl(SimControlAction.PROVIDER, 0.0))
        flow.ws.day.control(SimControl(SimControlAction.PROVIDER, 1.0))
        assert flow.ws.snapshot.execute().travel_notice is None

    def test_plan_can_still_be_built_with_the_provider_down(self) -> None:
        flow = seeded()
        flow.container.provider.set_available(False)
        flow.ws.core.repo.reset(flow.container.clock.now().date(), flow.ws.core.dataset.orders)
        plan = flow.ws.build_plan.execute("test")
        assert any("sin tráfico" in n for n in plan.notes)
        assert plan.unassigned == ()

    def test_without_live_traffic_times_differ_only_by_the_simulated_congestion(self) -> None:
        up = seeded()
        down = seeded()
        down.container.provider.set_available(False)
        for f in (up, down):
            f.ws.core.repo.reset(f.container.clock.now().date(), f.ws.core.dataset.orders)
        plan_up = up.ws.build_plan.execute("t")
        plan_down = down.ws.build_plan.execute("t")
        end_up = max(r.evaluation.return_arrival_min for r in plan_up.routes)
        end_down = max(r.evaluation.return_arrival_min for r in plan_down.routes)
        assert end_down <= end_up  # sin la congestión inventada, no es más lento


class TestTracking:
    def test_late_stop_triggers_a_resequence_proposal_and_alert(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        # el cierre se registra pero el despachador rechaza re-secuenciar: queda el retraso
        proposal = flow.ws.handle_event.execute(
            "d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300)
        ).proposal
        flow.ws.approve.execute("d", proposal.id, False)
        snap = flow.ws.snapshot.execute()
        assert any(a.code == "late_deliveries" for a in snap.alerts)

    def test_tracking_does_not_repeat_a_proposal_the_dispatcher_rejected(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        proposal = flow.ws.handle_event.execute(
            "d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300)
        ).proposal
        flow.ws.approve.execute("d", proposal.id, False)
        assert flow.ws.track.execute() == []  # el cierre ya tuvo su propuesta y fue rechazada

    def test_tracking_proposes_on_its_own_when_a_stop_falls_behind(self) -> None:
        from fleetplanner.domain.routing.events import Closure
        from fleetplanner.domain.routing.geo import GeoPoint

        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        # el cierre llega por otra vía (sin pasar por HandleEvent): nadie propuso nada todavía
        flow.ws.core.repo.add_closure(
            Closure("EXT-1", "Cierre externo", GeoPoint(4.678, -74.155), 1.0, 3.0, 375.0, 675.0)
        )
        created = flow.ws.track.execute()
        assert len(created) == 1
        proposal = created[0]
        assert proposal.event_type is EventType.DELAY_RISK
        assert proposal.impact.late_stops_before >= 1 and proposal.impact.late_stops_after == 0
        assert flow.container.clock.status().paused
        assert flow.ws.track.execute() == []  # ya hay una propuesta pendiente para ese vehículo
        applied = flow.ws.approve.execute("desp", proposal.id, True)
        assert applied.plan.version == 2
        assert applied.plan.created_by == "desp"


class TestSnapshot:
    def test_snapshot_reports_every_vehicle_and_a_demo_depot(self) -> None:
        flow = seeded()
        started(flow)
        snap = flow.ws.snapshot.execute()
        assert {v.id for v in snap.vehicles} == {"V-01", "V-02", "V-03", "V-TER"}
        assert snap.plan.version == 1 and snap.travel_notice is None
        assert snap.depot.name.startswith("CEDI")
        assert all(v.status == "not_started" or v.route_status == "standby" for v in snap.vehicles)

    def test_vehicles_move_and_stops_complete_as_the_clock_advances(self) -> None:
        flow = seeded(customers=10, vehicles=2)
        started(flow)
        before = flow.ws.snapshot.execute()
        flow.at(9)
        mid = flow.ws.snapshot.execute()
        flow.at(18)
        end = flow.ws.snapshot.execute()
        done = lambda s: sum(1 for x in s.stops if x.state == "completed")  # noqa: E731
        assert done(before) == 0 < done(mid) < done(end) == len(end.stops)
        assert all(v.status in {"at_depot", "standby"} for v in end.vehicles)

    def test_pending_proposals_raise_an_info_alert(self) -> None:
        flow = closure_case()
        started(flow)
        flow.at(6, 15)
        flow.ws.handle_event.execute("d", CloseRoadCommand("x", 4.678, -74.155, 1.0, 3.0, 300))
        snap = flow.ws.snapshot.execute()
        assert any(a.code == "pending_proposal" for a in snap.alerts)
        assert snap.proposals and snap.events

    def test_simulation_speed_must_be_one_of_the_allowed_values(self) -> None:
        flow = seeded()
        started(flow)
        flow.ws.day.control(SimControl(SimControlAction.SPEED, 60.0))
        assert flow.container.clock.status().speed == 60.0
        with pytest.raises(InvalidValueError, match="Velocidad no permitida"):
            flow.ws.day.control(SimControl(SimControlAction.SPEED, 7.0))
        with pytest.raises(InvalidValueError):
            flow.ws.day.control(SimControl(SimControlAction.ADVANCE, 0.0))
