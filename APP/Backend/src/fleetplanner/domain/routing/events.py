"""Eventos operativos y propuestas de re-ruteo (DOCS.MD §7.5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from fleetplanner.domain.routing.geo import GeoPoint, haversine_km, midpoint
from fleetplanner.domain.routing.plan import RoutePlan
from fleetplanner.domain.routing.time_window import TimeWindow
from fleetplanner.domain.shared.errors import InvalidValueError


class EventType(StrEnum):
    ROAD_CLOSURE = "road_closure"
    URGENT_ORDER = "urgent_order"
    WINDOW_CHANGE = "window_change"
    BREAKDOWN = "breakdown"
    DELAY_RISK = "delay_risk"  # lo genera el seguimiento (7.4), no el despachador


@dataclass(frozen=True)
class Closure:
    """Cierre vial o congestión: multiplica el tiempo de los tramos que toca (DOCS.MD §7.1)."""

    id: str
    label: str
    center: GeoPoint
    radius_km: float
    factor: float
    start_min: float
    end_min: float

    def __post_init__(self) -> None:
        if self.radius_km <= 0:
            raise InvalidValueError("El radio del cierre debe ser mayor que cero.")
        if self.factor < 1:
            raise InvalidValueError("El factor del cierre debe ser 1 o mayor (1 = sin efecto).")
        if self.end_min <= self.start_min:
            raise InvalidValueError("El cierre debe terminar después de empezar.")

    def is_active_at(self, minute: float) -> bool:
        return self.start_min <= minute < self.end_min

    def touches(self, origin: GeoPoint, destination: GeoPoint) -> bool:
        """El radio afecta el origen, el destino o el punto medio del tramo."""
        return any(
            haversine_km(self.center, p) <= self.radius_km
            for p in (origin, destination, midpoint(origin, destination))
        )


def closure_factor(
    closures: Sequence[Closure], origin: GeoPoint, destination: GeoPoint, depart_min: float
) -> float:
    """Factor de tiempo del tramo; con varios cierres aplica el mayor (no se multiplican)."""
    factors = [
        c.factor for c in closures if c.is_active_at(depart_min) and c.touches(origin, destination)
    ]
    return max(factors, default=1.0)


@dataclass(frozen=True)
class ClosureEventData:
    label: str
    center: GeoPoint
    radius_km: float
    factor: float
    duration_min: float


@dataclass(frozen=True)
class UrgentOrderData:
    order_id: str
    customer_code: str
    kg: float
    m3: float
    window: TimeWindow


@dataclass(frozen=True)
class WindowChangeData:
    order_id: str
    window: TimeWindow


@dataclass(frozen=True)
class BreakdownData:
    vehicle_id: str


@dataclass(frozen=True)
class DelayRiskData:
    vehicle_id: str


EventPayload = ClosureEventData | UrgentOrderData | WindowChangeData | BreakdownData | DelayRiskData


@dataclass(frozen=True)
class OperationalEvent:
    id: str
    type: EventType
    occurred_at: datetime
    minute: float
    created_by: str
    summary: str
    payload: EventPayload
    proposal_ids: tuple[str, ...] = ()
    outcome: str = ""


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"  # el plan cambió antes de decidir
    NONE_NEEDED = "none_needed"  # el evento no requiere cambios


@dataclass(frozen=True)
class ProposalImpact:
    """Antes/después del cambio propuesto, para que el despachador decida con cifras."""

    late_stops_before: int
    delay_min_before: float
    late_stops_after: int
    delay_min_after: float
    score_before: float
    score_after: float
    affected_vehicles: tuple[str, ...]
    activates_reserve: bool
    reserve_vehicle: str | None = None
    unattended_before: int = 0  # entregas que quedarían sin vehículo si no se actúa
    unattended_orders: tuple[str, ...] = ()  # pedidos que quedan sin atender hoy tras el cambio
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RerouteProposal:
    id: str
    event_id: str
    event_type: EventType
    base_version: int
    created_at: datetime
    reason: str
    summary: str
    impact: ProposalImpact
    proposed_plan: RoutePlan | None
    status: ProposalStatus = ProposalStatus.PENDING
    requires_confirmation: bool = True
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_comment: str = ""
    applied_version: int | None = None
    created_minute: float = 0.0
