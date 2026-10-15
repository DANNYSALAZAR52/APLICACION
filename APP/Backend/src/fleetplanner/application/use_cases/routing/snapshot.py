"""Vista de la torre de control: estado de vehículos, paradas, versiones, eventos y alertas."""

from __future__ import annotations

from fleetplanner.application.dto.routing import (
    INCIDENT_LABELS,
    Alert,
    ClockView,
    DepotView,
    OperationsSnapshot,
    PlanSummary,
    ReportView,
    StopView,
    UnassignedView,
    VehicleView,
)
from fleetplanner.application.ports.outbound.clock import SimulationClockPort
from fleetplanner.application.ports.outbound.routing import TrafficProviderControl
from fleetplanner.application.use_cases.routing.core import DEGRADED_NOTICE, RoutingCore
from fleetplanner.application.use_cases.routing.gps_support import GpsMonitor, GpsStatus
from fleetplanner.domain.routing.delivery import DeliveryConfirmation
from fleetplanner.domain.routing.evaluation import StopKind, StopTiming
from fleetplanner.domain.routing.events import ProposalStatus
from fleetplanner.domain.routing.plan import RoutePlan, RouteStatus, RouteView
from fleetplanner.domain.routing.time_window import format_clock
from fleetplanner.domain.routing.tracking import VehicleStatus
from fleetplanner.domain.shared.errors import ConflictError

_EPS = 1e-6


def summarize(plan: RoutePlan, views: dict[str, RouteView] | None = None) -> PlanSummary:
    """Con ``views`` usa los horarios vigentes; sin ellos, los guardados al crear la versión."""
    if views is not None:
        evals = [v.evaluation for v in views.values() if v.route.status is RouteStatus.ACTIVE]
        frozen_late = [t for v in views.values() for t in v.route.frozen if t.delay_min > _EPS]
    else:
        evals = [r.evaluation for r in plan.routes if r.status is RouteStatus.ACTIVE]
        frozen_late = [t for r in plan.routes for t in r.frozen if t.delay_min > _EPS]
    return PlanSummary(
        version=plan.version,
        base_version=plan.base_version,
        created_at=plan.created_at,
        created_by=plan.created_by,
        reason=plan.reason,
        engine=plan.engine,
        score=sum(e.score for e in evals),
        late_stops=sum(e.late_stops for e in evals) + len(frozen_late),
        delay_min=sum(e.delay_min for e in evals) + sum(t.delay_min for t in frozen_late),
        vehicles_in_use=sum(
            1
            for r in plan.routes
            if r.status is not RouteStatus.STANDBY and (r.pending or r.frozen)
        ),
        unassigned=len(plan.unassigned),
        notes=plan.notes,
        comparison=plan.comparison,
    )


def stop_views(
    view: RouteView,
    now: float,
    margin: float,
    confirmations: dict[str, DeliveryConfirmation],
) -> list[StopView]:
    """Paradas de una ruta con su estado en ``now`` (también la usa la hoja del conductor)."""
    route = view.route
    result: list[StopView] = []
    for i, t in enumerate(view.timings, start=1):
        if t.departure_min <= now:
            state = "completed"
        elif t.arrival_min <= now:
            state = "in_service"
        else:
            state = "pending"
        window = t.spec.window
        confirmation = confirmations.get(t.spec.order_id or "")
        at_risk = (
            state == "pending"
            and window is not None
            and (t.delay_min > _EPS or window.end_min - t.arrival_min < margin)
        )
        result.append(
            StopView(
                vehicle_id=route.vehicle_id,
                plate=route.plate,
                sequence=i,
                key=t.spec.key,
                kind=t.spec.kind.value,
                order_id=t.spec.order_id,
                customer_code=t.spec.customer_code,
                label=t.spec.label,
                lat=t.spec.point.lat,
                lon=t.spec.point.lon,
                window_start_min=window.start_min if window else None,
                window_end_min=window.end_min if window else None,
                arrival_min=t.arrival_min,
                service_start_min=t.service_start_min,
                departure_min=t.departure_min,
                delay_min=t.delay_min,
                wait_min=t.wait_min,
                kg=-t.spec.load_delta_kg if t.spec.kind is StopKind.DELIVERY else 0.0,
                state=state,
                at_risk=at_risk,
                confirmed_by=confirmation.source.value if confirmation else None,
                confirmed_min=confirmation.minute if confirmation else None,
            )
        )
    return result


class GetOperationsSnapshot:
    def __init__(
        self,
        core: RoutingCore,
        sim_clock: SimulationClockPort | None = None,
        provider: TrafficProviderControl | None = None,
        monitor: GpsMonitor | None = None,
    ) -> None:
        self._core = core
        self._sim_clock = sim_clock
        self._provider = provider
        self._monitor = monitor

    def execute(self) -> OperationsSnapshot:
        core = self._core
        plan = core.repo.active_plan()
        if plan is None:
            raise ConflictError("Aún no hay plan del día; cree el plan de la mañana primero.")
        now = core.now_min()
        resolver = core.resolver()
        views = {r.vehicle_id: core.view(r, resolver, now) for r in plan.routes}
        if self._monitor is not None:
            self._monitor.evaluate_geofence(
                views, now
            )  # idempotente: solo agrega confirmaciones nuevas
        confirmations = core.repo.confirmations()

        stops: list[StopView] = []
        vehicles: list[VehicleView] = []
        alerts: list[Alert] = []
        for route in plan.routes:
            view = views[route.vehicle_id]
            gps = self._monitor.status(view, now) if self._monitor else None
            stops.extend(stop_views(view, now, core.params.risk_margin_min, confirmations))
            vehicles.append(self._vehicle(view, now, gps))
            alerts.extend(self._vehicle_alerts(view, now, gps))

        reports = self._reports()
        alerts.extend(self._report_alerts(reports))
        proposals = core.repo.proposals()
        for p in proposals:
            if p.status is ProposalStatus.PENDING:
                alerts.append(
                    Alert(
                        "info",
                        "pending_proposal",
                        f"Propuesta pendiente: {p.reason}. Requiere su decisión.",
                    )
                )
        for u in plan.unassigned:
            alerts.append(
                Alert("critical", "unassigned", f"Pedido {u.order_id} sin asignar: {u.reason}")
            )
        alerts.sort(key=lambda a: {"critical": 0, "warning": 1, "info": 2}[a.level])

        notice = DEGRADED_NOTICE if resolver.degraded else None
        if notice:
            alerts.insert(0, Alert("warning", "degraded_times", notice))

        still_pending = {s.order_id for s in stops if s.state == "pending" and s.order_id}
        pending_orders = tuple(
            (oid, core.customer(o.customer_code).name)
            for oid, o in sorted(core.repo.orders().items())
            if oid in still_pending
        )
        return OperationsSnapshot(
            clock=self._clock_view(now),
            depot=DepotView(core.dataset.depot.name, core.depot_point.lat, core.depot_point.lon),
            plan=summarize(plan, views),
            versions=tuple(summarize(p, None) for p in core.repo.plans()),
            vehicles=tuple(vehicles),
            stops=tuple(stops),
            unassigned=tuple(
                UnassignedView(u.order_id, u.customer_code, u.reason) for u in plan.unassigned
            ),
            events=tuple(reversed(core.repo.events())),
            proposals=tuple(reversed(proposals)),
            alerts=tuple(alerts),
            travel_notice=notice,
            provider_available=self._provider.is_available() if self._provider else True,
            customers=tuple((c.code, c.name) for c in core.dataset.customers),
            pending_orders=pending_orders,
            reports=tuple(reports),
        )

    # ------------------------------------------------------------------ piezas
    def _reports(self) -> list[ReportView]:
        core = self._core
        plates = {v.id: v.plate for v in core.dataset.vehicles}
        return [
            ReportView(
                id=r.id,
                vehicle_id=r.vehicle_id,
                plate=plates.get(r.vehicle_id, r.vehicle_id),
                minute=r.minute,
                kind=r.kind.value,
                detail=r.detail,
                by=r.by,
                order_id=r.order_id,
            )
            for r in reversed(core.repo.reports())
        ]

    @staticmethod
    def _report_alerts(reports: list[ReportView]) -> list[Alert]:
        """Las últimas novedades del conductor avisan al despachador; no cambian el plan."""
        return [
            Alert(
                "critical" if r.kind == "vehicle_issue" else "warning",
                "driver_report",
                f"{r.plate}: novedad del conductor ({INCIDENT_LABELS.get(r.kind, r.kind)}): "
                f"{r.detail}",
                r.vehicle_id,
            )
            for r in reports[:5]
        ]

    def _clock_view(self, now_min: float) -> ClockView:
        core = self._core
        if self._sim_clock is not None:
            status = self._sim_clock.status()
            return ClockView(status.now, now_min, status.speed, status.paused, True)
        return ClockView(core.clock.now(), now_min, 1.0, False, False)

    def _vehicle(self, view: RouteView, now: float, gps: GpsStatus | None) -> VehicleView:
        core = self._core
        route = view.route
        vehicle = core.vehicle(route.vehicle_id)
        pending = [t for t in view.timings if t.departure_min > now]
        next_stop: StopTiming | None = pending[0] if pending else None
        done = [t for t in view.timings if t.departure_min <= now]
        load = route.initial_load_kg if not done else done[-1].load_after_kg
        if next_stop is not None and next_stop.arrival_min <= now:
            load = next_stop.load_after_kg + (
                -next_stop.spec.load_delta_kg if next_stop.spec.kind is StopKind.DELIVERY else 0
            )
        broken = route.status is RouteStatus.BROKEN
        # Con GPS la posición mostrada es la ÚLTIMA lectura (puede tener minutos de antigüedad).
        fix = gps.fix if gps and gps.fix else None
        point = fix.point if fix else view.state.point
        return VehicleView(
            id=route.vehicle_id,
            plate=route.plate,
            vehicle_type=route.vehicle_type,
            kind=vehicle.kind.value,
            route_status=route.status.value,
            status=view.state.status.value,
            lat=point.lat,
            lon=point.lon,
            load_kg=max(load, 0.0),
            capacity_kg=route.capacity_kg,
            completed_stops=view.state.completed_stops,
            pending_stops=view.state.pending_stops,
            next_stop_label=next_stop.spec.label if next_stop else None,
            next_eta_min=next_stop.arrival_min if next_stop else None,
            return_min=None
            if broken or view.state.status is VehicleStatus.STANDBY
            else view.evaluation.return_arrival_min,
            delay_min=view.evaluation.delay_min,
            late_stops=view.evaluation.late_stops,
            note=route.note,
            gps_status=gps.label if gps else "n/a",
            gps_age_min=gps.age_min if gps else None,
            gps_signal_enabled=gps.signal_enabled if gps else True,
        )

    def _vehicle_alerts(self, view: RouteView, now: float, gps: GpsStatus | None) -> list[Alert]:
        route = view.route
        alerts: list[Alert] = []
        if gps is not None and gps.no_signal:
            when = (
                f"última posición hace {gps.age_min:.0f} min ({format_clock(gps.fix.at_min)})"
                if gps.fix and gps.age_min is not None
                else "nunca reportó posición"
            )
            alerts.append(
                Alert(
                    "critical",
                    "no_signal",
                    f"{route.plate} sin señal GPS: {when}. Se conserva el plan vigente.",
                    route.vehicle_id,
                )
            )
        if route.status is RouteStatus.BROKEN:
            alerts.append(
                Alert(
                    "critical", "breakdown", f"Vehículo {route.plate} averiado.", route.vehicle_id
                )
            )
            return alerts
        late = [t for t in view.evaluation.timings if t.delay_min > _EPS and t.departure_min > now]
        if late:
            total = sum(t.delay_min for t in late)
            alerts.append(
                Alert(
                    "critical",
                    "late_deliveries",
                    f"{route.plate}: {len(late)} entrega(s) llegarían tarde "
                    f"({total:.0f} min de retraso en total).",
                    route.vehicle_id,
                )
            )
        else:
            margin = self._core.params.risk_margin_min
            risky = [
                t
                for t in view.evaluation.timings
                if t.spec.window is not None
                and t.departure_min > now
                and t.spec.window.end_min - t.arrival_min < margin
            ]
            if risky:
                first = risky[0]
                alerts.append(
                    Alert(
                        "warning",
                        "at_risk",
                        f"{route.plate}: la entrega a {first.spec.label} llega con menos de "
                        f"{margin:g} min de holgura (ventana hasta "
                        f"{format_clock(first.spec.window.end_min if first.spec.window else 0)}).",
                        route.vehicle_id,
                    )
                )
        return alerts
