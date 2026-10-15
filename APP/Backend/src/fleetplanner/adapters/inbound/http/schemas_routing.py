"""Esquemas HTTP del ruteo. Rechazan campos desconocidos: ningún `tenant_id` viaja en el cuerpo."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from fleetplanner.adapters.inbound.http.schemas import DEMO_LABEL, StrictModel
from fleetplanner.application.dto.routing import (
    BreakdownCommand,
    ChangeWindowCommand,
    CloseRoadCommand,
    ConfirmationResult,
    DecisionResult,
    DriverRouteView,
    EventCommand,
    HandleEventResult,
    IndicatorsView,
    OperationsSnapshot,
    PlanDetail,
    PlanSummary,
    ReportView,
    SimControl,
    SimControlAction,
    StopView,
    UnassignedView,
    UrgentOrderCommand,
    VehicleView,
)
from fleetplanner.domain.routing.events import OperationalEvent, RerouteProposal
from fleetplanner.domain.routing.time_window import parse_clock


# --------------------------------------------------------------------- entradas
class ClosureIn(StrictModel):
    type: Literal["road_closure"]
    label: str = Field(min_length=1, max_length=80)
    lat: float
    lon: float
    radius_km: float = Field(gt=0, le=25)
    factor: float = Field(ge=1, le=10)
    duration_min: float = Field(gt=0, le=720)


class UrgentOrderIn(StrictModel):
    type: Literal["urgent_order"]
    customer_code: str = Field(min_length=1, max_length=20)
    kg: float = Field(gt=0, le=50000)
    m3: float = Field(ge=0, le=500)
    window_start: str = Field(min_length=4, max_length=5)
    window_end: str = Field(min_length=4, max_length=5)


class WindowChangeIn(StrictModel):
    type: Literal["window_change"]
    order_id: str = Field(min_length=1, max_length=20)
    window_start: str = Field(min_length=4, max_length=5)
    window_end: str = Field(min_length=4, max_length=5)


class BreakdownIn(StrictModel):
    type: Literal["breakdown"]
    vehicle_id: str = Field(min_length=1, max_length=20)


EventIn = Annotated[
    ClosureIn | UrgentOrderIn | WindowChangeIn | BreakdownIn, Field(discriminator="type")
]


def event_command(body: ClosureIn | UrgentOrderIn | WindowChangeIn | BreakdownIn) -> EventCommand:
    if isinstance(body, ClosureIn):
        return CloseRoadCommand(
            body.label, body.lat, body.lon, body.radius_km, body.factor, body.duration_min
        )
    if isinstance(body, UrgentOrderIn):
        return UrgentOrderCommand(
            body.customer_code,
            body.kg,
            body.m3,
            parse_clock(body.window_start),
            parse_clock(body.window_end),
        )
    if isinstance(body, WindowChangeIn):
        return ChangeWindowCommand(
            body.order_id, parse_clock(body.window_start), parse_clock(body.window_end)
        )
    return BreakdownCommand(body.vehicle_id)


class DecisionIn(StrictModel):
    decision: Literal["approve", "reject"]
    comment: str = Field(default="", max_length=500)


class SimulationIn(StrictModel):
    action: Literal["pause", "resume", "speed", "advance", "provider", "gps_signal"]
    value: float | None = None
    target: str | None = Field(default=None, min_length=1, max_length=20)


def sim_control(body: SimulationIn) -> SimControl:
    return SimControl(SimControlAction(body.action), body.value, body.target)


# --------------------------------------------------------------------- salidas
class ClockOut(BaseModel):
    now: datetime
    minute: float
    speed: float
    paused: bool
    simulated: bool


class DepotOut(BaseModel):
    name: str
    lat: float
    lon: float


class EngineOut(BaseModel):
    engine: str
    score: float
    assigned_orders: int
    unassigned_orders: int
    elapsed_s: float
    chosen: bool


class PlanSummaryOut(BaseModel):
    version: int
    base_version: int | None
    created_at: datetime
    created_by: str
    reason: str
    engine: str
    score: float
    late_stops: int
    delay_min: float
    vehicles_in_use: int
    unassigned: int
    notes: list[str]
    comparison: list[EngineOut]


class VehicleOut(BaseModel):
    id: str
    plate: str
    vehicle_type: str
    kind: str
    route_status: str
    status: str
    lat: float
    lon: float
    load_kg: float
    capacity_kg: float
    completed_stops: int
    pending_stops: int
    next_stop_label: str | None
    next_eta_min: float | None
    return_min: float | None
    delay_min: float
    late_stops: int
    note: str
    gps_status: str
    gps_age_min: float | None
    gps_signal_enabled: bool


class StopOut(BaseModel):
    vehicle_id: str
    plate: str
    sequence: int
    key: str
    kind: str
    order_id: str | None
    customer_code: str | None
    label: str
    lat: float
    lon: float
    window_start_min: float | None
    window_end_min: float | None
    arrival_min: float
    service_start_min: float
    departure_min: float
    delay_min: float
    wait_min: float
    kg: float
    state: str
    at_risk: bool
    confirmed_by: str | None = None
    confirmed_min: float | None = None


class UnassignedOut(BaseModel):
    order_id: str
    customer_code: str
    reason: str


class AlertOut(BaseModel):
    level: str
    code: str
    message: str
    vehicle_id: str | None


class EventOut(BaseModel):
    id: str
    type: str
    occurred_at: datetime
    minute: float
    created_by: str
    summary: str
    outcome: str
    proposal_ids: list[str]


class ImpactOut(BaseModel):
    late_stops_before: int
    delay_min_before: float
    late_stops_after: int
    delay_min_after: float
    score_before: float
    score_after: float
    affected_vehicles: list[str]
    activates_reserve: bool
    reserve_vehicle: str | None
    unattended_before: int
    unattended_orders: list[str]
    notes: list[str]


class ProposalStopOut(BaseModel):
    label: str
    kind: str
    arrival_min: float
    delay_min: float


class ProposalRouteOut(BaseModel):
    vehicle_id: str
    plate: str
    status: str
    return_min: float
    stops: list[ProposalStopOut]


class ProposalOut(BaseModel):
    id: str
    event_id: str
    event_type: str
    base_version: int
    proposed_version: int | None
    created_at: datetime
    reason: str
    summary: str
    status: str
    requires_confirmation: bool
    impact: ImpactOut
    routes: list[ProposalRouteOut]
    decided_by: str | None
    decided_at: datetime | None
    decision_comment: str
    applied_version: int | None


class ReportOut(BaseModel):
    id: str
    vehicle_id: str
    plate: str
    minute: float
    kind: str
    detail: str
    by: str
    order_id: str | None


class SnapshotOut(BaseModel):
    demo_label: str
    clock: ClockOut
    depot: DepotOut
    plan: PlanSummaryOut
    versions: list[PlanSummaryOut]
    vehicles: list[VehicleOut]
    stops: list[StopOut]
    unassigned: list[UnassignedOut]
    events: list[EventOut]
    proposals: list[ProposalOut]
    alerts: list[AlertOut]
    travel_notice: str | None
    provider_available: bool
    customers: list[tuple[str, str]]
    pending_orders: list[tuple[str, str]]
    reports: list[ReportOut]


class EventResultOut(BaseModel):
    event: EventOut
    proposal: ProposalOut


class DecisionOut(BaseModel):
    proposal: ProposalOut
    replacement: ProposalOut | None
    plan_version: int | None
    message: str


class PlanRouteOut(BaseModel):
    vehicle_id: str
    plate: str
    status: str
    note: str
    stops: list[StopOut]


class PlanDetailOut(BaseModel):
    summary: PlanSummaryOut
    routes: list[PlanRouteOut]
    unassigned: list[UnassignedOut]


# ---------------------------------------------------------------------- mapeos
def _summary(s: PlanSummary) -> PlanSummaryOut:
    return PlanSummaryOut(
        version=s.version,
        base_version=s.base_version,
        created_at=s.created_at,
        created_by=s.created_by,
        reason=s.reason,
        engine=s.engine,
        score=s.score,
        late_stops=s.late_stops,
        delay_min=s.delay_min,
        vehicles_in_use=s.vehicles_in_use,
        unassigned=s.unassigned,
        notes=list(s.notes),
        comparison=[
            EngineOut(
                engine=e.engine,
                score=e.score,
                assigned_orders=e.assigned_orders,
                unassigned_orders=e.unassigned_orders,
                elapsed_s=e.elapsed_s,
                chosen=e.chosen,
            )
            for e in s.comparison
        ],
    )


def _vehicle(v: VehicleView) -> VehicleOut:
    return VehicleOut(**v.__dict__)


def _stop(s: StopView) -> StopOut:
    return StopOut(**s.__dict__)


def _unassigned(u: UnassignedView) -> UnassignedOut:
    return UnassignedOut(order_id=u.order_id, customer_code=u.customer_code, reason=u.reason)


def event_out(e: OperationalEvent) -> EventOut:
    return EventOut(
        id=e.id,
        type=e.type.value,
        occurred_at=e.occurred_at,
        minute=e.minute,
        created_by=e.created_by,
        summary=e.summary,
        outcome=e.outcome,
        proposal_ids=list(e.proposal_ids),
    )


def proposal_out(p: RerouteProposal) -> ProposalOut:
    i = p.impact
    routes: list[ProposalRouteOut] = []
    if p.proposed_plan is not None:
        for r in p.proposed_plan.routes:
            if r.vehicle_id not in i.affected_vehicles:
                continue
            routes.append(
                ProposalRouteOut(
                    vehicle_id=r.vehicle_id,
                    plate=r.plate,
                    status=r.status.value,
                    return_min=r.evaluation.return_arrival_min,
                    stops=[
                        ProposalStopOut(
                            label=t.spec.label,
                            kind=t.spec.kind.value,
                            arrival_min=t.arrival_min,
                            delay_min=t.delay_min,
                        )
                        for t in r.evaluation.timings
                    ],
                )
            )
    return ProposalOut(
        id=p.id,
        event_id=p.event_id,
        event_type=p.event_type.value,
        base_version=p.base_version,
        proposed_version=p.proposed_plan.version if p.proposed_plan else None,
        created_at=p.created_at,
        reason=p.reason,
        summary=p.summary,
        status=p.status.value,
        requires_confirmation=p.requires_confirmation,
        impact=ImpactOut(
            late_stops_before=i.late_stops_before,
            delay_min_before=i.delay_min_before,
            late_stops_after=i.late_stops_after,
            delay_min_after=i.delay_min_after,
            score_before=i.score_before,
            score_after=i.score_after,
            affected_vehicles=list(i.affected_vehicles),
            activates_reserve=i.activates_reserve,
            reserve_vehicle=i.reserve_vehicle,
            unattended_before=i.unattended_before,
            unattended_orders=list(i.unattended_orders),
            notes=list(i.notes),
        ),
        routes=routes,
        decided_by=p.decided_by,
        decided_at=p.decided_at,
        decision_comment=p.decision_comment,
        applied_version=p.applied_version,
    )


def snapshot_out(s: OperationsSnapshot) -> SnapshotOut:
    return SnapshotOut(
        demo_label=DEMO_LABEL,
        clock=ClockOut(**s.clock.__dict__),
        depot=DepotOut(name=s.depot.name, lat=s.depot.lat, lon=s.depot.lon),
        plan=_summary(s.plan),
        versions=[_summary(v) for v in s.versions],
        vehicles=[_vehicle(v) for v in s.vehicles],
        stops=[_stop(x) for x in s.stops],
        unassigned=[_unassigned(u) for u in s.unassigned],
        events=[event_out(e) for e in s.events],
        proposals=[proposal_out(p) for p in s.proposals],
        alerts=[AlertOut(**a.__dict__) for a in s.alerts],
        travel_notice=s.travel_notice,
        provider_available=s.provider_available,
        customers=list(s.customers),
        pending_orders=list(s.pending_orders),
        reports=[ReportOut(**r.__dict__) for r in s.reports],
    )


def event_result_out(r: HandleEventResult) -> EventResultOut:
    return EventResultOut(event=event_out(r.event), proposal=proposal_out(r.proposal))


def decision_out(r: DecisionResult) -> DecisionOut:
    return DecisionOut(
        proposal=proposal_out(r.proposal),
        replacement=proposal_out(r.replacement) if r.replacement else None,
        plan_version=r.plan.version if r.plan else None,
        message=r.message,
    )


def plan_detail_out(detail: PlanDetail) -> PlanDetailOut:
    plan, summary = detail.plan, detail.summary
    routes: list[PlanRouteOut] = []
    for r in plan.routes:
        stops = []
        for seq, t in enumerate((*r.frozen, *r.evaluation.timings), start=1):
            w = t.spec.window
            stops.append(
                StopOut(
                    vehicle_id=r.vehicle_id,
                    plate=r.plate,
                    sequence=seq,
                    key=t.spec.key,
                    kind=t.spec.kind.value,
                    order_id=t.spec.order_id,
                    customer_code=t.spec.customer_code,
                    label=t.spec.label,
                    lat=t.spec.point.lat,
                    lon=t.spec.point.lon,
                    window_start_min=w.start_min if w else None,
                    window_end_min=w.end_min if w else None,
                    arrival_min=t.arrival_min,
                    service_start_min=t.service_start_min,
                    departure_min=t.departure_min,
                    delay_min=t.delay_min,
                    wait_min=t.wait_min,
                    kg=-t.spec.load_delta_kg if t.spec.kind.value == "delivery" else 0.0,
                    state="planned",
                    at_risk=False,
                )
            )
        routes.append(
            PlanRouteOut(
                vehicle_id=r.vehicle_id,
                plate=r.plate,
                status=r.status.value,
                note=r.note,
                stops=stops,
            )
        )
    return PlanDetailOut(
        summary=_summary(summary),
        routes=routes,
        unassigned=[
            UnassignedOut(order_id=u.order_id, customer_code=u.customer_code, reason=u.reason)
            for u in plan.unassigned
        ],
    )


class KpiOut(BaseModel):
    committed_orders: int
    delivered_orders: int
    on_time_orders: int
    otif_orders: int
    late_orders: int
    unattended_orders: int
    incomplete_orders: int
    total_delay_min: float
    punctuality: float | None
    otif: float | None


class ScenarioOut(BaseModel):
    key: str
    title: str
    description: str
    mode: str
    incomplete_rate: float
    kpis: KpiOut
    plan_versions: int
    reserve_activations: int
    events: list[str]


class LiveOut(BaseModel):
    minute: float
    plan_version: int
    projected: KpiOut
    delivered_so_far: int
    on_time_so_far: int


class IndicatorsOut(BaseModel):
    demo_label: str
    live: LiveOut
    scenarios: list[ScenarioOut]
    definitions: list[str]


def indicators_out(view: IndicatorsView) -> IndicatorsOut:
    return IndicatorsOut(
        demo_label=DEMO_LABEL,
        live=LiveOut(
            minute=view.live.minute,
            plan_version=view.live.plan_version,
            projected=KpiOut(**view.live.projected.__dict__),
            delivered_so_far=view.live.delivered_so_far,
            on_time_so_far=view.live.on_time_so_far,
        ),
        scenarios=[
            ScenarioOut(
                key=s.key,
                title=s.title,
                description=s.description,
                mode=s.mode,
                incomplete_rate=s.incomplete_rate,
                kpis=KpiOut(**s.kpis.__dict__),
                plan_versions=s.plan_versions,
                reserve_activations=s.reserve_activations,
                events=list(s.events),
            )
            for s in view.scenarios
        ],
        definitions=list(view.definitions),
    )


# ---------------------------------------------------------------- conductor
class ReportIn(StrictModel):
    kind: Literal["customer_absent", "access_blocked", "damaged_goods", "vehicle_issue", "other"]
    detail: str = Field(min_length=3, max_length=300)
    order_id: str | None = Field(default=None, min_length=1, max_length=20)


class NavLinkOut(BaseModel):
    label: str
    url: str
    stops: int


class DriverStopOut(BaseModel):
    stop: StopOut
    address: str


class DriverRouteOut(BaseModel):
    demo_label: str
    vehicle_id: str
    plate: str
    vehicle_status: str
    route_status: str
    plan_version: int
    clock: ClockOut
    depot: DepotOut
    stops: list[DriverStopOut]
    next_key: str | None
    nav_links: list[NavLinkOut]
    load_kg: float
    capacity_kg: float
    return_min: float | None
    delay_min: float
    notices: list[str]
    reports: list[ReportOut]


class ConfirmationOut(BaseModel):
    order_id: str
    source: str
    minute: float
    already_confirmed: bool


def driver_route_out(v: DriverRouteView) -> DriverRouteOut:
    return DriverRouteOut(
        demo_label=DEMO_LABEL,
        vehicle_id=v.vehicle_id,
        plate=v.plate,
        vehicle_status=v.vehicle_status,
        route_status=v.route_status,
        plan_version=v.plan_version,
        clock=ClockOut(**v.clock.__dict__),
        depot=DepotOut(name=v.depot.name, lat=v.depot.lat, lon=v.depot.lon),
        stops=[DriverStopOut(stop=_stop(d.stop), address=d.address) for d in v.stops],
        next_key=v.next_key,
        nav_links=[NavLinkOut(label=n.label, url=n.url, stops=n.stops) for n in v.nav_links],
        load_kg=v.load_kg,
        capacity_kg=v.capacity_kg,
        return_min=v.return_min,
        delay_min=v.delay_min,
        notices=list(v.notices),
        reports=[ReportOut(**r.__dict__) for r in v.reports],
    )


def confirmation_out(r: ConfirmationResult) -> ConfirmationOut:
    return ConfirmationOut(**r.__dict__)


def report_out(r: ReportView) -> ReportOut:
    return ReportOut(**r.__dict__)
