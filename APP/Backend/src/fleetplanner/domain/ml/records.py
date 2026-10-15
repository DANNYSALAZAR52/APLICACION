"""Registros históricos de operación sobre los que se entrenan los modelos."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from fleetplanner.domain.capacity.models import DemandSeries
from fleetplanner.domain.shared.errors import InvalidValueError


@dataclass(frozen=True)
class ServiceVisit:
    """Una visita a un cliente: llegada, espera, servicio y si quedó fuera de la ventana."""

    customer_code: str
    corridor_code: str
    day: date
    hour: int
    wait_min: float
    service_min: float
    order_kg: float
    window_width_min: int
    traffic_factor: float
    stops_remaining: int
    late: bool

    def __post_init__(self) -> None:
        if not 0 <= self.hour <= 23:
            raise InvalidValueError(f"La hora de llegada {self.hour} no es válida (0 a 23).")
        if self.wait_min < 0 or self.service_min < 0 or self.order_kg < 0:
            raise InvalidValueError("Espera, servicio y carga no pueden ser negativos.")
        if self.window_width_min <= 0:
            raise InvalidValueError("La amplitud de la ventana debe ser mayor que cero.")
        if self.traffic_factor <= 0:
            raise InvalidValueError("El factor de tráfico debe ser mayor que cero.")
        if self.stops_remaining < 0:
            raise InvalidValueError("Las paradas restantes no pueden ser negativas.")


@dataclass(frozen=True)
class OperationalHistory:
    """Historia de UNA empresa. Nunca mezcla datos de otras: el lector se crea por tenant."""

    demand: Mapping[str, DemandSeries]
    visits: tuple[ServiceVisit, ...]
    provenance: str
    seed: int | None = None
    corridor_names: Mapping[str, str] = field(default_factory=dict)
    customer_names: Mapping[str, str] = field(default_factory=dict)

    @property
    def last_day(self) -> date | None:
        days = [d for s in self.demand.values() for d in s.observations]
        days.extend(v.day for v in self.visits)
        return max(days) if days else None

    @property
    def first_day(self) -> date | None:
        days = [d for s in self.demand.values() for d in s.observations]
        days.extend(v.day for v in self.visits)
        return min(days) if days else None

    @property
    def span_days(self) -> int:
        first, last = self.first_day, self.last_day
        return 0 if first is None or last is None else (last - first).days + 1

    def corridor_name(self, code: str) -> str:
        return self.corridor_names.get(code, code)

    def customer_name(self, code: str) -> str:
        return self.customer_names.get(code, code)
