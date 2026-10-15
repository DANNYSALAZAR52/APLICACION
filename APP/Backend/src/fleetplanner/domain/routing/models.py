"""Entidades de ruteo: CEDI, clientes, pedidos, vehículos y parámetros del plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from fleetplanner.domain.routing.geo import GeoPoint, coordinate_issues
from fleetplanner.domain.routing.time_window import TimeWindow, window_issues
from fleetplanner.domain.shared.errors import InvalidValueError


@dataclass(frozen=True)
class Depot:
    """CEDI: origen y destino de todas las rutas."""

    code: str
    name: str
    point: GeoPoint


def customer_issues(
    code: str,
    name: str,
    lat: float,
    lon: float,
    window_start_min: float,
    window_end_min: float,
    service_minutes: float,
) -> list[str]:
    """Todos los problemas de un cliente a la vez, para corregirlos en una sola pasada."""
    issues: list[str] = []
    if not code.strip():
        issues.append("El código del cliente es obligatorio.")
    if not name.strip():
        issues.append("El nombre del cliente es obligatorio.")
    issues.extend(coordinate_issues(lat, lon))
    issues.extend(window_issues(window_start_min, window_end_min))
    if service_minutes <= 0:
        issues.append("Los minutos de servicio deben ser mayores que cero.")
    return issues


@dataclass(frozen=True)
class Customer:
    code: str
    name: str
    address: str
    point: GeoPoint
    window: TimeWindow
    service_minutes: float = 15.0
    restrictions: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        address: str,
        lat: float,
        lon: float,
        window_start_min: float,
        window_end_min: float,
        service_minutes: float = 15.0,
        restrictions: tuple[str, ...] = (),
    ) -> Customer:
        """Valida y construye; ante datos inválidos informa TODOS los problemas (criterio 11)."""
        issues = customer_issues(
            code, name, lat, lon, window_start_min, window_end_min, service_minutes
        )
        if issues:
            raise InvalidValueError(f"El cliente '{code}' no es válido: " + " ".join(issues))
        return cls(
            code=code.strip(),
            name=name.strip(),
            address=address.strip(),
            point=GeoPoint(lat, lon),
            window=TimeWindow(window_start_min, window_end_min),
            service_minutes=service_minutes,
            restrictions=restrictions,
        )

    @property
    def needs_location_review(self) -> bool:
        """Cliente fuera del área urbana: se marca para revisión, no se descarta en silencio."""
        return not self.point.is_in_urban_area()


class OrderStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    DELIVERED = "delivered"
    LATE = "late"
    NOT_DELIVERED = "not_delivered"


@dataclass(frozen=True)
class Order:
    id: str
    customer_code: str
    kg: float
    m3: float
    window: TimeWindow
    priority: int = 2
    urgent: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidValueError("El pedido debe tener identificador.")
        if self.kg <= 0:
            raise InvalidValueError(f"Los kg del pedido {self.id} deben ser mayores que cero.")
        if self.m3 < 0:
            raise InvalidValueError(f"Los m³ del pedido {self.id} no pueden ser negativos.")
        if self.priority not in (1, 2, 3):
            raise InvalidValueError(f"La prioridad del pedido {self.id} debe ser 1, 2 o 3.")


class VehicleKind(StrEnum):
    OWN = "own"
    RESERVE = "reserve"
    THIRD_PARTY = "third_party"


@dataclass(frozen=True)
class RoutingVehicle:
    id: str
    plate: str
    vehicle_type: str
    capacity_kg: float
    kind: VehicleKind = VehicleKind.OWN
    gps_id: str = ""

    def __post_init__(self) -> None:
        if self.capacity_kg <= 0:
            raise InvalidValueError(f"La capacidad del vehículo {self.plate} debe ser positiva.")

    @property
    def is_active_fleet(self) -> bool:
        return self.kind is VehicleKind.OWN


@dataclass(frozen=True)
class RoutingParams:
    """Parámetros editables del plan (DOCS.MD §7.2). Los pesos del puntaje son configurables."""

    departure_min: float = 360.0  # salida de referencia 06:00
    shift_end_min: float = 1020.0  # fin de turno 17:00
    max_fill: float = 0.90  # llenado máximo (capacidad operativa = capacidad × llenado)
    service_kg_per_min: float = 50.0  # servicio = minutos del cliente + kg/50
    weight_travel: float = 1.0
    weight_wait: float = 0.2
    weight_delay: float = 20.0
    weight_overtime: float = 2.0
    transshipment_min: float = 25.0  # transbordo ante avería
    reload_min: float = 20.0  # recarga en el CEDI
    reserve_activation_cost: float = 60.0  # puntos de puntaje por activar reserva/tercero
    risk_margin_min: float = 10.0  # holgura bajo la cual una entrega se considera en riesgo
    geofence_m: float = 100.0
    geofence_dwell_min: float = 5.0
    no_signal_min: float = 15.0
    extra: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 < self.max_fill <= 1:
            raise InvalidValueError("El llenado máximo debe estar entre 0 y 100 %.")
        if self.service_kg_per_min <= 0:
            raise InvalidValueError("Los kg por minuto de servicio deben ser positivos.")
        if self.shift_end_min <= self.departure_min:
            raise InvalidValueError("El fin de turno debe ser posterior a la salida.")
        for label, weight in (
            ("viaje", self.weight_travel),
            ("espera", self.weight_wait),
            ("retraso", self.weight_delay),
            ("horas extra", self.weight_overtime),
        ):
            if weight < 0:
                raise InvalidValueError(f"El peso de {label} no puede ser negativo.")

    def operational_capacity_kg(self, vehicle: RoutingVehicle) -> float:
        return vehicle.capacity_kg * self.max_fill

    def service_minutes_for(self, customer: Customer, kg: float) -> float:
        return customer.service_minutes + kg / self.service_kg_per_min
