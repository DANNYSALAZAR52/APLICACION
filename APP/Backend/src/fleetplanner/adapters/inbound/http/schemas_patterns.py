"""Esquemas HTTP de patrones de ML. Solo salida; ninguna entrada acepta un `tenant_id`."""

from __future__ import annotations

import math
from datetime import date, datetime

from pydantic import BaseModel

from fleetplanner.application.dto.ml import (
    CorridorForecast,
    ForecastComparison,
    MetricLine,
    ModelCard,
    PatternsReport,
)
from fleetplanner.domain.ml.results import Anomaly, DelayRisk, Forecast, Segment


def _finite(value: float | None) -> float | None:
    if value is None or math.isinf(value) or math.isnan(value):
        return None
    return value


class MetricOut(BaseModel):
    label: str
    value: str
    hint: str


class ModelOut(BaseModel):
    name: str
    title: str
    version: int
    trained_at: datetime
    seed: int
    library: str
    artifact_sha256: str
    dataset_description: str
    metrics: list[MetricOut]
    importances: list[tuple[str, float]]
    notes: list[str]


class ForecastOut(BaseModel):
    day: date
    p50_t: float
    p90_t: float
    baseline_t: float | None


class RecentOut(BaseModel):
    day: date
    tons: float


class CorridorForecastOut(BaseModel):
    corridor_code: str
    corridor_name: str
    recent: list[RecentOut]
    forecast: list[ForecastOut]
    historical_p90_t: float | None


class AnomalyOut(BaseModel):
    customer_code: str
    customer_name: str
    kind: str
    weekday: int
    hour_from: int
    hour_to: int
    events: int
    observed_min: float
    usual_min: float
    ratio: float | None
    severity: float
    message: str


class DelayRiskOut(BaseModel):
    customer_code: str
    customer_name: str
    hour: int
    probability: float
    traffic_factor: float
    stops_remaining: int
    order_kg: float


class SegmentOut(BaseModel):
    segment_id: int
    name: str
    description: str
    customers: list[str]
    mean_service_min: float
    mean_order_kg: float
    mean_window_min: float
    weekly_variation: float


class PatternsOut(BaseModel):
    status: str
    demo_label: str
    provenance: str
    generated_at: datetime
    history_from: date | None
    history_to: date | None
    models: list[ModelOut]
    forecasts: list[CorridorForecastOut]
    anomalies: list[AnomalyOut]
    delay_risks: list[DelayRiskOut]
    segments: list[SegmentOut]
    limits: list[str]
    warnings: list[str]


class MlForecastOut(BaseModel):
    """Pronóstico del siguiente día frente al percentil histórico, para el tablero."""

    corridor_code: str
    corridor_name: str
    day: date
    p50_t: float
    p90_t: float
    baseline_t: float | None
    historical_p90_t: float | None


def _metric(line: MetricLine) -> MetricOut:
    return MetricOut(label=line.label, value=line.value, hint=line.hint)


def _model(card: ModelCard) -> ModelOut:
    meta = card.metadata
    return ModelOut(
        name=meta.name,
        title=card.title,
        version=meta.version,
        trained_at=meta.trained_at,
        seed=meta.seed,
        library=meta.library,
        artifact_sha256=meta.artifact_sha256,
        dataset_description=meta.dataset_description,
        metrics=[_metric(m) for m in card.metric_lines],
        importances=[(name, round(share, 4)) for name, share in card.importances],
        notes=list(card.notes),
    )


def _forecast(item: Forecast) -> ForecastOut:
    return ForecastOut(day=item.day, p50_t=item.p50_t, p90_t=item.p90_t, baseline_t=item.baseline_t)


def _corridor(item: CorridorForecast) -> CorridorForecastOut:
    return CorridorForecastOut(
        corridor_code=item.corridor_code,
        corridor_name=item.corridor_name,
        recent=[RecentOut(day=d, tons=t) for d, t in item.recent],
        forecast=[_forecast(f) for f in item.forecast],
        historical_p90_t=item.historical_p90_t,
    )


def _anomaly(item: Anomaly) -> AnomalyOut:
    return AnomalyOut(
        customer_code=item.customer_code,
        customer_name=item.customer_name,
        kind=item.kind,
        weekday=item.weekday,
        hour_from=item.hour_from,
        hour_to=item.hour_to,
        events=item.events,
        observed_min=item.observed_min,
        usual_min=item.usual_min,
        ratio=_finite(item.ratio),
        severity=item.severity,
        message=item.message,
    )


def _delay(item: DelayRisk) -> DelayRiskOut:
    return DelayRiskOut(
        customer_code=item.customer_code,
        customer_name=item.customer_name,
        hour=item.hour,
        probability=item.probability,
        traffic_factor=item.traffic_factor,
        stops_remaining=item.stops_remaining,
        order_kg=item.order_kg,
    )


def _segment(item: Segment) -> SegmentOut:
    return SegmentOut(
        segment_id=item.segment_id,
        name=item.name,
        description=item.description,
        customers=list(item.customers),
        mean_service_min=item.mean_service_min,
        mean_order_kg=item.mean_order_kg,
        mean_window_min=item.mean_window_min,
        weekly_variation=item.weekly_variation,
    )


def patterns_out(report: PatternsReport) -> PatternsOut:
    return PatternsOut(
        status=report.status,
        demo_label=report.demo_label,
        provenance=report.provenance,
        generated_at=report.generated_at,
        history_from=report.history_from,
        history_to=report.history_to,
        models=[_model(m) for m in report.models],
        forecasts=[_corridor(c) for c in report.forecasts],
        anomalies=[_anomaly(a) for a in report.anomalies],
        delay_risks=[_delay(d) for d in report.delay_risks],
        segments=[_segment(s) for s in report.segments],
        limits=list(report.limits),
        warnings=list(report.warnings),
    )


def ml_forecast_out(item: ForecastComparison) -> MlForecastOut:
    return MlForecastOut(
        corridor_code=item.corridor_code,
        corridor_name=item.corridor_name,
        day=item.day,
        p50_t=item.p50_t,
        p90_t=item.p90_t,
        baseline_t=item.baseline_t,
        historical_p90_t=item.historical_p90_t,
    )
