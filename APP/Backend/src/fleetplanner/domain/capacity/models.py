"""Entidades y value objects del subdominio de capacidad.

Unidades: toneladas (t), kilómetros (km), horas (h), minutos (min). Los nombres de campo llevan
el sufijo de unidad cuando no es evidente.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from fleetplanner.domain.shared.errors import InvalidValueError
from fleetplanner.domain.shared.percentage import Percentage


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise InvalidValueError(f"{name} debe ser mayor que cero (se recibió {value:g}).")


def _require_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise InvalidValueError(f"{name} no puede ser negativo (se recibió {value:g}).")


@dataclass(frozen=True)
class VehicleType:
    """Tipo de vehículo (turbo, sencillo, doble troque, tractomula...)."""

    name: str
    capacity_t: float
    capacity_m3: float
    pallets: int
    fixed_cost_month: float
    variable_cost_per_km: float
    third_party_daily_rate: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidValueError("El tipo de vehículo debe tener nombre.")
        _require_positive("La capacidad en toneladas", self.capacity_t)
        _require_positive("La capacidad en m³", self.capacity_m3)
        _require_non_negative("Los pallets", self.pallets)
        _require_non_negative("El costo fijo mensual", self.fixed_cost_month)
        _require_non_negative("El costo variable por km", self.variable_cost_per_km)
        _require_non_negative("La tarifa diaria de tercero", self.third_party_daily_rate)

    def fixed_cost_per_day(self, days_per_month: int) -> float:
        """Convierte el costo fijo mensual a diario con los días operativos configurados."""
        if days_per_month <= 0:
            raise InvalidValueError("Los días operativos por mes deben ser mayores que cero.")
        return self.fixed_cost_month / days_per_month


@dataclass(frozen=True)
class OeeFactors:
    """OEE de flota = disponibilidad × utilización × rendimiento."""

    availability: Percentage
    utilization: Percentage
    performance: Percentage

    def __post_init__(self) -> None:
        for label, factor in (
            ("La disponibilidad", self.availability),
            ("La utilización", self.utilization),
            ("El rendimiento", self.performance),
        ):
            if factor.fraction <= 0:
                raise InvalidValueError(f"{label} debe ser mayor que 0 % para calcular el OEE.")

    @property
    def oee(self) -> float:
        return self.availability.fraction * self.utilization.fraction * self.performance.fraction


@dataclass(frozen=True)
class Corridor:
    """Ruta o corredor con sus tiempos de ciclo (maestro `corridor_route`)."""

    code: str
    name: str
    assigned_vehicle_type: str
    one_way_km: float
    average_speed_kmh: float
    operating_hours: float
    loading_h: float
    dock_wait_h: float
    stops: int
    minutes_per_stop: float
    customer_wait_h: float
    fill: Percentage
    backhaul: Percentage

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise InvalidValueError("El corredor debe tener código.")
        _require_positive(f"Los km de ida del corredor {self.code}", self.one_way_km)
        _require_positive(f"La velocidad del corredor {self.code}", self.average_speed_kmh)
        _require_positive(f"Las horas operativas del corredor {self.code}", self.operating_hours)
        _require_non_negative(f"El cargue del corredor {self.code}", self.loading_h)
        _require_non_negative(f"La espera en muelle del corredor {self.code}", self.dock_wait_h)
        _require_non_negative(f"Las paradas del corredor {self.code}", self.stops)
        _require_non_negative(
            f"Los minutos por parada del corredor {self.code}", self.minutes_per_stop
        )
        _require_non_negative(
            f"La espera en cliente del corredor {self.code}", self.customer_wait_h
        )
        if self.fill.fraction <= 0:
            raise InvalidValueError(
                f"El porcentaje de llenado del corredor {self.code} debe ser mayor que 0 %."
            )


@dataclass(frozen=True)
class CompatibilityMatrix:
    """Combinaciones (corredor, tipo de vehículo) permitidas."""

    allowed: frozenset[tuple[str, str]]

    @classmethod
    def of(cls, pairs: Iterable[tuple[str, str]]) -> CompatibilityMatrix:
        return cls(frozenset(pairs))

    def is_allowed(self, corridor_code: str, vehicle_type: str) -> bool:
        return (corridor_code, vehicle_type) in self.allowed

    def types_for(self, corridor_code: str) -> list[str]:
        return sorted(t for c, t in self.allowed if c == corridor_code)


@dataclass(frozen=True)
class DemandSeries:
    """Demanda diaria (t/día) de un corredor.

    Un día sin observación **no existe** en la serie: es dato ausente, nunca cero.
    """

    corridor_code: str
    observations: Mapping[date, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for day, tons in self.observations.items():
            if tons < 0:
                raise InvalidValueError(
                    f"La demanda del {day.isoformat()} en {self.corridor_code} "
                    "no puede ser negativa."
                )

    def last_date(self) -> date | None:
        return max(self.observations) if self.observations else None
