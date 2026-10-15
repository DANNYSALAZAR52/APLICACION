"""GPS en el ruteo: lo que "mediría" el dispositivo, geocerca de llegada y estado de la señal."""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.application.use_cases.routing.core import RoutingCore
from fleetplanner.domain.routing.delivery import ConfirmationSource, DeliveryConfirmation
from fleetplanner.domain.routing.evaluation import StopKind
from fleetplanner.domain.routing.gps import (
    GpsFix,
    GpsSample,
    distance_m,
    fix_age_min,
    geofence_arrival,
    has_no_signal,
)
from fleetplanner.domain.routing.plan import RouteStatus, RouteView
from fleetplanner.domain.routing.tracking import VehicleStatus


@dataclass(frozen=True)
class GpsStatus:
    """Estado de la señal de un vehículo. ``applicable`` es falso si no debería estar reportando."""

    applicable: bool
    fix: GpsFix | None
    age_min: float | None
    no_signal: bool
    signal_enabled: bool

    @property
    def label(self) -> str:
        if not self.applicable:
            return "n/a"
        return "no_signal" if self.no_signal else "ok"


class FleetTruth:
    """Posición real del vehículo según el plan vigente (la lee el simulador de GPS)."""

    def __init__(self, core: RoutingCore) -> None:
        self._core = core

    def sample(self, vehicle_id: str, minute: float) -> GpsSample | None:
        core = self._core
        plan = core.repo.active_plan()
        route = plan.route_of(vehicle_id) if plan else None
        if route is None or route.status is RouteStatus.STANDBY:
            return None
        resolver = core.resolver()
        state = core.view(route, resolver, minute).state
        moving = state.status in (VehicleStatus.TRAVELING, VehicleStatus.RETURNING)
        speed = 0.0
        if moving:
            after = core.view(route, resolver, minute + 1.0).state
            speed = distance_m(state.point, after.point) / 1000.0 * 60.0
        return GpsSample(state.point, speed, moving)


class GpsMonitor:
    """Evalúa la señal ("sin señal" a los 15 min) y confirma entregas por geocerca."""

    _REPORTING = (
        VehicleStatus.TRAVELING,
        VehicleStatus.WAITING,
        VehicleStatus.SERVING,
        VehicleStatus.RETURNING,
    )

    def __init__(self, core: RoutingCore) -> None:
        self._core = core

    def status(self, view: RouteView, now_min: float) -> GpsStatus:
        gps, control = self._core.gps, self._core.gps_control
        enabled = control.signal_enabled(view.route.vehicle_id) if control else True
        if gps is None or view.route.status is not RouteStatus.ACTIVE:
            return GpsStatus(False, None, None, False, enabled)
        fix = gps.latest_fix(view.route.vehicle_id)
        applicable = view.state.status in self._REPORTING
        age = fix_age_min(fix, now_min) if fix else None
        no_signal = applicable and has_no_signal(fix, now_min, self._core.params.no_signal_min)
        return GpsStatus(applicable, fix, age, no_signal, enabled)

    def evaluate_geofence(self, views: dict[str, RouteView], now_min: float) -> int:
        """Confirma por geocerca (≈100 m, >5 min) las entregas que lleguen a ese umbral."""
        core, gps = self._core, self._core.gps
        if gps is None:
            return 0
        params = core.params
        confirmed = core.repo.confirmations()
        recorded = 0
        for vid, view in views.items():
            if view.route.status is not RouteStatus.ACTIVE:
                continue
            for t in view.timings:
                order_id = t.spec.order_id
                if (
                    t.spec.kind is not StopKind.DELIVERY
                    or order_id is None
                    or order_id in confirmed
                    or t.arrival_min > now_min
                ):
                    continue
                fixes = gps.fixes_since(vid, t.arrival_min - 4.0)
                minute = geofence_arrival(
                    fixes, t.spec.point, params.geofence_m, params.geofence_dwell_min
                )
                if minute is not None and core.repo.confirm(
                    DeliveryConfirmation(order_id, minute, ConfirmationSource.GEOFENCE)
                ):
                    recorded += 1
        return recorded
