"""Resultado persistible de una corrida de capacidad (tabla `capacity_result`)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from fleetplanner.domain.shared.errors import InvalidValueError

ALGORITHM_VERSION = "capacity-1.0.0"


class CapacityMethod(StrEnum):
    BALANCE = "balance"
    LEAN = "lean"
    MONTE_CARLO = "monte_carlo"
    MIX_OPTIMIZATION = "mix_optimization"
    OWN_VS_THIRD_PARTY = "own_vs_third_party"
    PROJECTION = "projection"


@dataclass(frozen=True)
class CapacityResult:
    """Resultado de un método para un tipo de vehículo (y año/escenario cuando aplica).

    ``parameters`` conserva los parámetros efectivos y la procedencia (método, versión del
    algoritmo, semilla, días válidos...) para poder explicar el resultado.
    """

    run_at: datetime
    method: CapacityMethod
    vehicle_type: str
    year: int | None
    required_fleet: int
    algorithm_version: str
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.run_at.tzinfo is None:
            raise InvalidValueError("La fecha de corrida debe tener zona horaria (no naïve).")
        if self.required_fleet < 0:
            raise InvalidValueError("La flota requerida no puede ser negativa.")
