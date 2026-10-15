"""DTO del módulo de ML: lo que consumen los adaptadores de entrada."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

from fleetplanner.domain.ml.results import (
    Anomaly,
    DelayRisk,
    Forecast,
    ModelMetadata,
    Segment,
)

DEMAND_MODEL = "pronostico_demanda"
ANOMALY_MODEL = "deteccion_anomalias"
DELAY_MODEL = "riesgo_retraso"
SEGMENT_MODEL = "segmentacion_clientes"
MODEL_NAMES = (DEMAND_MODEL, ANOMALY_MODEL, DELAY_MODEL, SEGMENT_MODEL)

MODEL_TITLES: Mapping[str, str] = {
    DEMAND_MODEL: "Pronóstico de demanda por corredor",
    ANOMALY_MODEL: "Detección de anomalías por cliente",
    DELAY_MODEL: "Riesgo de retraso",
    SEGMENT_MODEL: "Segmentación de clientes",
}


@dataclass(frozen=True)
class TrainedArtifact:
    """Resultado de entrenar: el artefacto serializado y su evaluación (sin tipos de sklearn)."""

    payload: bytes
    metrics: Mapping[str, float]
    importances: Mapping[str, float] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    dataset_description: str = ""
    library: str = ""


@dataclass(frozen=True)
class LoadedModel:
    """Artefacto cuyo hash ya fue verificado contra el registro, con su procedencia."""

    metadata: ModelMetadata
    payload: bytes
    importances: Mapping[str, float]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class MetricLine:
    label: str
    value: str
    hint: str = ""


@dataclass(frozen=True)
class ModelCard:
    """Procedencia visible de un modelo: versión, fecha, métricas e importancias."""

    metadata: ModelMetadata
    title: str
    metric_lines: tuple[MetricLine, ...]
    importances: tuple[tuple[str, float], ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class CorridorForecast:
    corridor_code: str
    corridor_name: str
    recent: tuple[tuple[date, float], ...]
    forecast: tuple[Forecast, ...]
    historical_p90_t: float | None


@dataclass(frozen=True)
class ForecastComparison:
    """Pronóstico del siguiente día frente al percentil histórico (tablero de capacidad)."""

    corridor_code: str
    corridor_name: str
    day: date
    p50_t: float
    p90_t: float
    baseline_t: float | None
    historical_p90_t: float | None


@dataclass(frozen=True)
class PatternsReport:
    status: str  # "ok" | "sin_datos"
    demo_label: str
    provenance: str
    generated_at: datetime
    history_from: date | None
    history_to: date | None
    models: tuple[ModelCard, ...] = ()
    forecasts: tuple[CorridorForecast, ...] = ()
    anomalies: tuple[Anomaly, ...] = ()
    delay_risks: tuple[DelayRisk, ...] = ()
    segments: tuple[Segment, ...] = ()
    limits: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
