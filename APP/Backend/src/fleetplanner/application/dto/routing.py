"""Comandos de entrada y vistas de salida del módulo de ruteo (no son entidades de dominio)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from fleetplanner.domain.routing.events import OperationalEvent, RerouteProposal
from fleetplanner.domain.routing.plan import EngineResult, RoutePlan


# ------------------------------------------------------------------- comandos
@dataclass(frozen=True)
class CloseRoadCommand:
    label: str
    lat: float
    lon: float
    radius_km: float
    factor: float
    duration_min: float


@dataclass(frozen=True)
class UrgentOrderCommand:
    customer_code: str
    kg: float
    m3: float
    window_start_min: float
    window_end_min: float


@dataclass(frozen=True)
class ChangeWindowCommand:
    order_id: str
    window_start_min: float
    window_end_min: float


@dataclass(frozen=True)
class BreakdownCommand:
    vehicle_id: str


EventCommand = CloseRoadCommand | UrgentOrderCommand | ChangeWindowCommand | BreakdownCommand


class SimControlAction(StrEnum):
    GPS_SIGNAL = "gps_signal"  # corta o restablece la señal de un vehículo (DEMO-ONLY)
    PAUSE = "pause"
    RESUME = "resume"
    SPEED = "speed"
    ADVANCE = "advance"
    PROVIDER = "provider"  # simula que el proveedor de tiempos deja (o vuelve) de responder


@dataclass(frozen=True)
class SimControl:
    action: SimControlAction
    value: float | None = None
    target: str | None = None


@dataclass(frozen=True)
class HandleEventResult:
    event: OperationalEvent
    proposal: RerouteProposal


@dataclass(frozen=True)
class DecisionResult:
    proposal: RerouteProposal
    plan: RoutePlan | None  # versión creada al aprobar
    replacement: RerouteProposal | None  # propuesta nueva si la anterior quedó obsoleta
    message: str


# --------------------------------------------------------------------- vistas
INCIDENT_LABELS = {
    "customer_absent": "cliente ausente",
    "access_blocked": "acceso bloqueado",
    "damaged_goods": "mercancía dañada",
    "vehicle_issue": "problema del vehículo",
    "other": "otra novedad",
}


@dataclass(frozen=True)
class ReportView:
    id: str
    vehicle_id: str
    plate: str
    minute: float
    kind: str
    detail: str
    by: str
    order_id: str | None


@dataclass(frozen=True)
class NavLinkView:
    label: str
    url: str
    stops: int


@dataclass(frozen=True)
class DriverStopView:
    stop: StopView
    address: str


@dataclass(frozen=True)
class DriverRouteView:
    vehicle_id: str
    plate: str
    vehicle_status: str
    route_status: str
    plan_version: int
    clock: ClockView
    depot: DepotView
    stops: tuple[DriverStopView, ...]
    next_key: str | None
    nav_links: tuple[NavLinkView, ...]
    load_kg: float
    capacity_kg: float
    return_min: float | None
    delay_min: float
    notices: tuple[str, ...]
    reports: tuple[ReportView, ...]


@dataclass(frozen=True)
class ConfirmationResult:
    order_id: str
    source: str
    minute: float
    already_confirmed: bool


@dataclass(frozen=True)
class ClockView:
    now: datetime
    minute: float
    speed: float
    paused: bool
    simulated: bool


@dataclass(frozen=True)
class StopView:
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
    state: str  # completed | in_service | pending
    at_risk: bool
    confirmed_by: str | None = None  # geofence | driver
    confirmed_min: float | None = None


@dataclass(frozen=True)
class VehicleView:
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
    gps_status: str = "n/a"  # ok | no_signal | n/a
    gps_age_min: float | None = None
    gps_signal_enabled: bool = True


@dataclass(frozen=True)
class PlanSummary:
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
    notes: tuple[str, ...] = ()
    comparison: tuple[EngineResult, ...] = ()


@dataclass(frozen=True)
class Alert:
    level: str  # critical | warning | info
    code: str
    message: str
    vehicle_id: str | None = None


@dataclass(frozen=True)
class DepotView:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class UnassignedView:
    order_id: str
    customer_code: str
    reason: str


@dataclass(frozen=True)
class OperationsSnapshot:
    clock: ClockView
    depot: DepotView
    plan: PlanSummary
    versions: tuple[PlanSummary, ...]
    vehicles: tuple[VehicleView, ...]
    stops: tuple[StopView, ...]
    unassigned: tuple[UnassignedView, ...]
    events: tuple[OperationalEvent, ...]
    proposals: tuple[RerouteProposal, ...]
    alerts: tuple[Alert, ...]
    travel_notice: str | None
    provider_available: bool
    customers: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (código, nombre)
    pending_orders: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (pedido, cliente)
    reports: tuple[ReportView, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlanDetail:
    plan: RoutePlan
    summary: PlanSummary


@dataclass(frozen=True)
class KpiView:
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


@dataclass(frozen=True)
class ScenarioView:
    key: str
    title: str
    description: str
    mode: str  # static | dynamic
    incomplete_rate: float
    kpis: KpiView
    plan_versions: int
    reserve_activations: int
    events: tuple[str, ...]


@dataclass(frozen=True)
class LiveIndicators:
    minute: float
    plan_version: int
    projected: KpiView
    delivered_so_far: int
    on_time_so_far: int


@dataclass(frozen=True)
class IndicatorsView:
    live: LiveIndicators
    scenarios: tuple[ScenarioView, ...]
    definitions: tuple[str, ...]
