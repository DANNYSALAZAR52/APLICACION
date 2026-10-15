"""Resultados de ML con tipos propios del dominio (nada de objetos de scikit-learn)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from fleetplanner.domain.ml.calendar_co import WEEKDAYS_ES
from fleetplanner.domain.shared.errors import InvalidValueError


@dataclass(frozen=True)
class Forecast:
    """Pronóstico de demanda diaria (t) de un corredor, con intervalo y línea base."""

    corridor_code: str
    day: date
    p50_t: float
    p90_t: float
    baseline_t: float | None

    def __post_init__(self) -> None:
        if self.p90_t < self.p50_t:
            raise InvalidValueError("El P90 del pronóstico no puede ser menor que el P50.")


@dataclass(frozen=True)
class Anomaly:
    """Comportamiento inusual de un cliente en una franja, con evidencia estadística."""

    customer_code: str
    customer_name: str
    kind: str  # "espera" | "servicio"
    weekday: int
    hour_from: int
    hour_to: int
    events: int
    observed_min: float
    usual_min: float
    severity: float

    @property
    def ratio(self) -> float:
        return self.observed_min / self.usual_min if self.usual_min > 0 else float("inf")

    @property
    def message(self) -> str:
        concept = "esperas" if self.kind == "espera" else "tiempos de servicio"
        weekday = WEEKDAYS_ES[self.weekday]
        if self.weekday >= 5:  # sábado y domingo forman el plural con "s"
            weekday += "s"
        ratio = f"{self.ratio:.1f}".replace(".", ",")
        return (
            f"{self.customer_name} tuvo {concept} de {self.observed_min:.0f} min en promedio "
            f"los {weekday} entre las {self.hour_from:02d}:00 y las {self.hour_to:02d}:00, "
            f"{ratio} veces su patrón habitual ({self.usual_min:.0f} min), en {self.events} "
            "visitas. Es una asociación estadística: no demuestra la causa."
        )


@dataclass(frozen=True)
class DelayRisk:
    """Probabilidad estimada de quedar fuera de ventana en condiciones típicas del cliente."""

    customer_code: str
    customer_name: str
    hour: int
    probability: float
    traffic_factor: float
    stops_remaining: int
    order_kg: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise InvalidValueError("La probabilidad de retraso debe estar entre 0 y 1.")


@dataclass(frozen=True)
class Segment:
    """Grupo de clientes con comportamiento parecido (no es una categoría objetiva)."""

    segment_id: int
    name: str
    description: str
    customers: tuple[str, ...]
    mean_service_min: float
    mean_order_kg: float
    mean_window_min: float
    weekly_variation: float


@dataclass(frozen=True)
class ModelMetadata:
    """Registro versionado de un modelo entrenado para una empresa."""

    name: str
    version: int
    trained_at: datetime
    seed: int
    metrics: Mapping[str, float]
    artifact_sha256: str
    dataset_description: str
    library: str
