"""Hoja de ruta del conductor: su ruta, confirmar entregas y reportar novedades.

El vehículo del conductor sale de su usuario guardado (`Principal.vehicle_id`); ningún dato de la
solicitud puede cambiarlo, así que un conductor solo ve y toca SU ruta.
"""

from __future__ import annotations

from fleetplanner.application.dto.routing import (
    ClockView,
    ConfirmationResult,
    DepotView,
    DriverRouteView,
    DriverStopView,
    NavLinkView,
    ReportView,
)
from fleetplanner.application.ports.outbound.clock import SimulationClockPort
from fleetplanner.application.use_cases.routing.core import DEGRADED_NOTICE, RoutingCore
from fleetplanner.application.use_cases.routing.snapshot import stop_views
from fleetplanner.domain.routing.delivery import (
    ConfirmationSource,
    DeliveryConfirmation,
    DriverReport,
    IncidentKind,
)
from fleetplanner.domain.routing.evaluation import StopKind
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.navigation import navigation_legs
from fleetplanner.domain.routing.plan import RouteStatus
from fleetplanner.domain.routing.tracking import VehicleStatus
from fleetplanner.domain.shared.errors import ConflictError, InvalidValueError, NotFoundError

MAX_DETAIL = 300
MIN_DETAIL = 3


class DriverService:
    def __init__(self, core: RoutingCore, sim_clock: SimulationClockPort | None = None) -> None:
        self._core = core
        self._sim_clock = sim_clock

    def _clock_view(self, now_min: float) -> ClockView:
        if self._sim_clock is not None:
            status = self._sim_clock.status()
            return ClockView(status.now, now_min, status.speed, status.paused, True)
        return ClockView(self._core.clock.now(), now_min, 1.0, False, False)

    # ------------------------------------------------------------------ ruta
    def route(self, vehicle_id: str) -> DriverRouteView:
        core = self._core
        plan = core.repo.active_plan()
        if plan is None:
            raise ConflictError("Aún no hay plan del día.")
        route = plan.route_of(vehicle_id)
        if route is None:
            raise NotFoundError("Su vehículo no tiene ruta en este plan.")
        now = core.now_min()
        resolver = core.resolver()
        view = core.view(route, resolver, now)
        confirmations = core.repo.confirmations()
        stops = stop_views(view, now, core.params.risk_margin_min, confirmations)
        driver_stops = tuple(
            DriverStopView(s, self._address(s.customer_code, s.kind)) for s in stops
        )
        remaining = [s for s in stops if s.state != "completed"]
        points = [GeoPoint(s.lat, s.lon) for s in remaining]
        legs = navigation_legs(points)
        links = tuple(
            NavLinkView(
                label=(
                    "Abrir la ruta en Google Maps"
                    if len(legs) == 1
                    else f"Tramo {i} de {len(legs)} en Google Maps (paradas "
                    f"{remaining[leg.first].sequence} a {remaining[leg.last - 1].sequence})"
                ),
                url=leg.url,
                stops=leg.last - leg.first,
            )
            for i, leg in enumerate(legs, start=1)
        )
        vehicle_state = view.state.status
        done = [t for t in view.timings if t.departure_min <= now]
        load = route.initial_load_kg if not done else done[-1].load_after_kg
        reports = [r for r in self._reports() if r.vehicle_id == vehicle_id]
        return DriverRouteView(
            vehicle_id=vehicle_id,
            plate=route.plate,
            vehicle_status=vehicle_state.value,
            route_status=route.status.value,
            plan_version=plan.version,
            clock=self._clock_view(now),
            depot=DepotView(core.dataset.depot.name, core.depot_point.lat, core.depot_point.lon),
            stops=driver_stops,
            next_key=remaining[0].key if remaining else None,
            nav_links=links,
            load_kg=max(load, 0.0),
            capacity_kg=route.capacity_kg,
            return_min=None
            if route.status is RouteStatus.BROKEN
            else view.evaluation.return_arrival_min,
            delay_min=view.evaluation.delay_min,
            notices=tuple(
                self._notices(
                    plan.version, plan.reason, route.status, vehicle_state, stops, resolver.degraded
                )
            ),
            reports=tuple(reports),
        )

    # ------------------------------------------------------------- confirmar
    def confirm(self, vehicle_id: str, username: str, order_id: str) -> ConfirmationResult:
        core = self._core
        plan = core.repo.active_plan()
        route = plan.route_of(vehicle_id) if plan else None
        if route is None:
            raise NotFoundError("Su vehículo no tiene ruta en este plan.")
        now = core.now_min()
        view = core.view(route, core.resolver(), now)
        stop = next(
            (
                t
                for t in view.timings
                if t.spec.order_id == order_id and t.spec.kind is StopKind.DELIVERY
            ),
            None,
        )
        if stop is None:
            raise NotFoundError("Ese pedido no está en su ruta.")
        if stop.arrival_min > now:
            raise ConflictError(
                "Aún no llega a esta parada: confirme la entrega cuando esté en el cliente."
            )
        existing = core.repo.confirmations().get(order_id)
        if existing is not None:
            return ConfirmationResult(order_id, existing.source.value, existing.minute, True)
        core.repo.confirm(
            DeliveryConfirmation(order_id, now, ConfirmationSource.DRIVER, by=username)
        )
        return ConfirmationResult(order_id, ConfirmationSource.DRIVER.value, now, False)

    # -------------------------------------------------------------- novedades
    def report(
        self,
        vehicle_id: str,
        username: str,
        kind: IncidentKind,
        detail: str,
        order_id: str | None,
    ) -> ReportView:
        core = self._core
        text = " ".join(detail.split())
        if not MIN_DETAIL <= len(text) <= MAX_DETAIL:
            raise InvalidValueError(
                f"Describa la novedad en {MIN_DETAIL} a {MAX_DETAIL} caracteres."
            )
        plan = core.repo.active_plan()
        route = plan.route_of(vehicle_id) if plan else None
        if route is None:
            raise NotFoundError("Su vehículo no tiene ruta en este plan.")
        if order_id is not None:
            view = core.view(route, core.resolver(), core.now_min())
            if order_id not in {t.spec.order_id for t in view.timings}:
                raise NotFoundError("Ese pedido no está en su ruta.")
        report = DriverReport(
            id=core.repo.next_id("NV"),
            vehicle_id=vehicle_id,
            minute=core.now_min(),
            kind=kind,
            detail=text,
            by=username,
            order_id=order_id,
        )
        core.repo.add_report(report)
        return self._view(report)

    # ------------------------------------------------------------------ interno
    def _reports(self) -> list[ReportView]:
        return [self._view(r) for r in reversed(self._core.repo.reports())]

    def _view(self, r: DriverReport) -> ReportView:
        plates = {v.id: v.plate for v in self._core.dataset.vehicles}
        return ReportView(
            id=r.id,
            vehicle_id=r.vehicle_id,
            plate=plates.get(r.vehicle_id, r.vehicle_id),
            minute=r.minute,
            kind=r.kind.value,
            detail=r.detail,
            by=r.by,
            order_id=r.order_id,
        )

    def _address(self, customer_code: str | None, kind: str) -> str:
        if kind == StopKind.RELOAD.value:
            return self._core.dataset.depot.name
        if kind == StopKind.TRANSFER.value:
            return "Punto de avería (transbordo)"
        if customer_code is None:
            return ""
        return self._core.customer(customer_code).address

    @staticmethod
    def _notices(
        version: int,
        reason: str,
        route_status: RouteStatus,
        state: VehicleStatus,
        stops: list,  # type: ignore[type-arg]
        degraded: bool,
    ) -> list[str]:
        notices: list[str] = []
        if route_status is RouteStatus.BROKEN:
            notices.append(
                "Su vehículo figura como averiado. Espere instrucciones del despachador."
            )
        elif route_status is RouteStatus.STANDBY and not stops:
            notices.append("No tiene ruta asignada por ahora. Permanezca en espera.")
        if version > 1:
            notices.append(
                f"La ruta fue actualizada por el despacho (plan versión {version}: {reason})."
            )
        if any(s.kind == "transfer" and s.state != "completed" for s in stops):
            notices.append(
                "Primero vaya al punto de transbordo: allí recibirá la carga de otro vehículo."
            )
        if any(s.kind == "reload" and s.state != "completed" for s in stops):
            notices.append("Debe pasar por el CEDI a recargar antes de continuar.")
        if degraded:
            notices.append(f"{DEGRADED_NOTICE}: los horarios son aproximados.")
        if state is VehicleStatus.NOT_STARTED and stops:
            notices.append("Aún no es la hora de salida.")
        return notices
