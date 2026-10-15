"""Plan de rutas versionado e inmutable, proyección en vivo y congelamiento para re-ruteo.

Un `RoutePlan` guarda las **decisiones** (secuencias por vehículo) y los horarios calculados al
crearlo. Los horarios "reales" se obtienen reevaluando las secuencias con lo que se sabe ahora
(`project_route`), sin tocar la versión guardada.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from fleetplanner.domain.routing.evaluation import (
    RouteEvaluation,
    StopSpec,
    StopTiming,
    TravelFn,
    evaluate_route,
)
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.models import RoutingParams
from fleetplanner.domain.routing.tracking import (
    VehicleState,
    VehicleStatus,
    build_segments,
    locate,
)


class RouteStatus(StrEnum):
    ACTIVE = "active"
    BROKEN = "broken"  # averiado: conserva lo entregado y deja de operar
    STANDBY = "standby"  # reserva o tercero sin ruta asignada


@dataclass(frozen=True)
class RouteAnchor:
    """Punto y hora desde los que se evalúa la parte pendiente de una ruta."""

    point: GeoPoint
    time_min: float
    label: str


@dataclass(frozen=True)
class VehicleRoute:
    vehicle_id: str
    plate: str
    vehicle_type: str
    capacity_kg: float  # capacidad operativa (capacidad × llenado máximo)
    anchor: RouteAnchor
    initial_load_kg: float
    frozen: tuple[StopTiming, ...]
    pending: tuple[StopSpec, ...]
    evaluation: RouteEvaluation
    status: RouteStatus = RouteStatus.ACTIVE
    note: str = ""

    @property
    def is_reserve_in_use(self) -> bool:
        return self.status is RouteStatus.ACTIVE and bool(self.pending)

    def pending_order_ids(self) -> list[str]:
        return [s.order_id for s in self.pending if s.order_id]


@dataclass(frozen=True)
class UnassignedOrder:
    order_id: str
    customer_code: str
    reason: str


@dataclass(frozen=True)
class EngineResult:
    """Resultado de un motor al construir el plan (para compararlos sin prometer ganadores)."""

    engine: str
    score: float
    assigned_orders: int
    unassigned_orders: int
    elapsed_s: float
    chosen: bool


@dataclass(frozen=True)
class RoutePlan:
    version: int
    base_version: int | None
    created_at: datetime
    created_by: str
    reason: str
    routes: tuple[VehicleRoute, ...]
    unassigned: tuple[UnassignedOrder, ...] = ()
    engine: str = ""
    comparison: tuple[EngineResult, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def route_of(self, vehicle_id: str) -> VehicleRoute | None:
        return next((r for r in self.routes if r.vehicle_id == vehicle_id), None)

    def route_carrying(self, order_id: str) -> VehicleRoute | None:
        return next((r for r in self.routes if order_id in r.pending_order_ids()), None)

    @property
    def score(self) -> float:
        return sum(r.evaluation.score for r in self.routes)


# ---------------------------------------------------------------- proyección
def project_route(
    route: VehicleRoute, depot_point: GeoPoint, params: RoutingParams, travel: TravelFn
) -> RouteEvaluation:
    """Reevalúa la parte pendiente de la ruta con las condiciones conocidas hoy."""
    return evaluate_route(
        route.anchor.point,
        route.anchor.time_min,
        route.initial_load_kg,
        route.pending,
        depot_point,
        route.capacity_kg,
        params,
        travel,
        return_to_depot=route.status is not RouteStatus.BROKEN,
    )


@dataclass(frozen=True)
class RouteView:
    """Ruta + horarios vigentes + estado del vehículo en un instante."""

    route: VehicleRoute
    evaluation: RouteEvaluation
    state: VehicleState

    @property
    def timings(self) -> tuple[StopTiming, ...]:
        return (*self.route.frozen, *self.evaluation.timings)


def view_route(
    route: VehicleRoute,
    now_min: float,
    depot_point: GeoPoint,
    params: RoutingParams,
    travel: TravelFn,
) -> RouteView:
    evaluation = project_route(route, depot_point, params, travel)
    timings = (*route.frozen, *evaluation.timings)
    if route.status is RouteStatus.BROKEN:
        state = VehicleState(
            VehicleStatus.BROKEN,
            route.anchor.point,
            now_min,
            None,
            None,
            sum(1 for t in timings if t.departure_min <= now_min),
            0,
        )
    elif not route.pending and not route.frozen and route.status is RouteStatus.STANDBY:
        state = VehicleState(VehicleStatus.STANDBY, depot_point, now_min, None, None, 0, 0)
    else:
        segments = build_segments(
            route.frozen,
            route.anchor.point,
            route.anchor.time_min,
            evaluation.timings,
            depot_point,
            evaluation.return_arrival_min,
        )
        state = locate(segments, now_min, route.anchor.point, depot_point, timings)
    return RouteView(route, evaluation, state)


# ------------------------------------------------------------- congelamiento
@dataclass(frozen=True)
class FrozenRoute:
    """Lo que no se puede cambiar de una ruta en un instante y desde dónde se replanifica."""

    vehicle_id: str
    frozen: tuple[StopTiming, ...]
    anchor: RouteAnchor
    load_kg: float
    pending: tuple[StopSpec, ...]
    state: VehicleState


def freeze_route(view: RouteView, now_min: float) -> FrozenRoute:
    """Congela lo entregado o en servicio en ``now_min`` y fija el ancla de re-ruteo.

    Una parada ya cargada no cambia de vehículo (DOCS.MD §7.5): lo congelado se queda y solo la
    secuencia pendiente puede reordenarse.
    """
    route = view.route
    timings = view.timings
    arrived = [t for t in timings if t.arrival_min <= now_min]
    pending = tuple(t.spec for t in timings if t.arrival_min > now_min)
    load = arrived[-1].load_after_kg if arrived else route.initial_load_kg

    in_service = arrived[-1] if arrived and arrived[-1].departure_min > now_min else None
    if in_service is not None:
        anchor = RouteAnchor(in_service.spec.point, in_service.departure_min, in_service.spec.label)
    elif view.state.status is VehicleStatus.NOT_STARTED:
        anchor = route.anchor
    else:
        anchor = RouteAnchor(view.state.point, now_min, "Posición actual")
    return FrozenRoute(
        vehicle_id=route.vehicle_id,
        frozen=tuple(arrived),
        anchor=anchor,
        load_kg=load,
        pending=pending,
        state=view.state,
    )


def make_route(
    base: VehicleRoute,
    frozen: Sequence[StopTiming],
    anchor: RouteAnchor,
    load_kg: float,
    pending: Sequence[StopSpec],
    depot_point: GeoPoint,
    params: RoutingParams,
    travel: TravelFn,
    status: RouteStatus = RouteStatus.ACTIVE,
    note: str = "",
) -> VehicleRoute:
    """Nueva ruta del mismo vehículo con otra secuencia pendiente, evaluada desde el ancla."""
    draft = replace(
        base,
        anchor=anchor,
        initial_load_kg=load_kg,
        frozen=tuple(frozen),
        pending=tuple(pending),
        status=status,
        note=note,
    )
    return replace(draft, evaluation=project_route(draft, depot_point, params, travel))
