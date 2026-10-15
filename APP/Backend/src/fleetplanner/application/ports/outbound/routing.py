"""Puertos de salida del ruteo: datos, tiempos de viaje, solver, persistencia y control de demo."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from fleetplanner.domain.routing.delivery import DeliveryConfirmation, DriverReport
from fleetplanner.domain.routing.evaluation import TravelLeg
from fleetplanner.domain.routing.events import Closure, OperationalEvent, RerouteProposal
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.gps import GpsFix
from fleetplanner.domain.routing.models import Customer, Depot, Order, RoutingParams, RoutingVehicle
from fleetplanner.domain.routing.plan import RoutePlan
from fleetplanner.domain.routing.problem import RoutingProblem, RoutingSolution


class TrafficProviderUnavailable(Exception):  # noqa: N818 - es una condición, no un error de uso
    """El proveedor de tiempos no respondió. El resolutor cae al perfil de velocidades."""


@dataclass(frozen=True)
class RoutingDataset:
    """Datos de ruteo de UNA empresa (los entrega un lector ya ligado a ese tenant)."""

    depot: Depot
    customers: tuple[Customer, ...]
    orders: tuple[Order, ...]
    vehicles: tuple[RoutingVehicle, ...]
    params: RoutingParams


class RoutingInputsReader(Protocol):
    def read(self) -> RoutingDataset: ...


class TrafficTimePort(Protocol):
    """Tiempos de viaje de un proveedor (con tráfico). Puede lanzar `TrafficProviderUnavailable`."""

    def estimate(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_min: float,
        closures: Sequence[Closure],
    ) -> TravelLeg: ...


class FallbackTravelTimePort(Protocol):
    """Respaldo basado en el perfil de velocidades: nunca falla y no afirma tráfico en vivo."""

    def estimate(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_min: float,
        closures: Sequence[Closure],
    ) -> TravelLeg: ...


class TrafficProviderControl(Protocol):
    """Solo demo: permite simular que el proveedor de tiempos deja de responder."""

    def is_available(self) -> bool: ...

    def set_available(self, available: bool) -> None: ...


class RoutingSolverPort(Protocol):
    def solve(self, problem: RoutingProblem, time_limit_s: float) -> RoutingSolution:
        """Resuelve el VRP con ventanas y capacidad. Puede dejar pedidos sin asignar."""
        ...


class RoutingRepositoryPort(Protocol):
    """Estado del día operativo de UN tenant. Las versiones del plan nunca se sobrescriben."""

    @property
    def day(self) -> date | None: ...

    def reset(self, day: date, orders: Sequence[Order]) -> None: ...

    def plans(self) -> list[RoutePlan]: ...

    def active_plan(self) -> RoutePlan | None: ...

    def add_plan(self, plan: RoutePlan) -> None:
        """Agrega una versión nueva; lanza `ConflictError` si el número no es el siguiente."""
        ...

    def orders(self) -> dict[str, Order]: ...

    def save_order(self, order: Order) -> None: ...

    def events(self) -> list[OperationalEvent]: ...

    def add_event(self, event: OperationalEvent) -> None: ...

    def update_event(self, event: OperationalEvent) -> None: ...

    def closures(self) -> list[Closure]: ...

    def add_closure(self, closure: Closure) -> None: ...

    def proposals(self) -> list[RerouteProposal]: ...

    def get_proposal(self, proposal_id: str) -> RerouteProposal | None: ...

    def save_proposal(self, proposal: RerouteProposal) -> None: ...

    def next_id(self, prefix: str) -> str: ...

    def confirmations(self) -> dict[str, DeliveryConfirmation]: ...

    def confirm(self, confirmation: DeliveryConfirmation) -> bool:
        """Registra la confirmación de un pedido; la primera gana. Devuelve si quedó registrada."""
        ...

    def reports(self) -> list[DriverReport]: ...

    def add_report(self, report: DriverReport) -> None: ...


class GpsPort(Protocol):
    """Posiciones de los dispositivos GPS. La demo usa un simulador (DEMO-ONLY)."""

    def latest_fix(self, vehicle_id: str) -> GpsFix | None: ...

    def fixes_since(self, vehicle_id: str, since_min: float) -> list[GpsFix]: ...


class GpsSimulationControl(Protocol):
    """Solo demo: pérdida de señal a pedido y reinicio del día."""

    def set_signal(self, vehicle_id: str, enabled: bool) -> None: ...

    def signal_enabled(self, vehicle_id: str) -> bool: ...

    def reset(self) -> None: ...
