"""Servicio de ML de UNA empresa: entrena (`TrainModels`) y detecta patrones (`DetectPatterns`).

El servicio se crea por tenant con un lector de historia y un registro propios, de modo que no
existe forma de mezclar datos o artefactos de otra empresa.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta

from fleetplanner.application.dto.ml import (
    ANOMALY_MODEL,
    DELAY_MODEL,
    DEMAND_MODEL,
    MODEL_NAMES,
    MODEL_TITLES,
    SEGMENT_MODEL,
    CorridorForecast,
    ForecastComparison,
    LoadedModel,
    MetricLine,
    ModelCard,
    PatternsReport,
    TrainedArtifact,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.ml import (
    AnomalyDetector,
    DelayRiskPredictor,
    DemandForecaster,
    HistoryReaderPort,
    ModelRegistryPort,
    PatternMiner,
)
from fleetplanner.domain.ml.records import OperationalHistory
from fleetplanner.domain.ml.results import ModelMetadata
from fleetplanner.domain.shared.errors import InsufficientDataError
from fleetplanner.domain.shared.stats import percentile_linear

MIN_HISTORY_DAYS = 28
FORECAST_HORIZON_DAYS = 7
RECENT_DAYS = 28
PERCENTILE_WINDOW_DAYS = 60
DESIGN_FRACTION = 0.90
DEFAULT_SEED = 20261014

LIMITS: tuple[str, ...] = (
    "Los modelos se entrenaron con DATOS SINTÉTICOS de demostración: los patrones son los que "
    "se sembraron al generarlos, no hallazgos de una operación real.",
    "Las métricas describen el comportamiento en este conjunto de datos y en una partición "
    "temporal; no permiten afirmar un rendimiento general.",
    "El pronóstico cubre como máximo 7 días y no conoce eventos extraordinarios (cierres, "
    "huelgas, promociones).",
    "La probabilidad de retraso es una estimación, no una certeza; úsela para priorizar la "
    "atención, no para decidir sola.",
    "Una anomalía es una asociación estadística: señala dónde mirar, no la causa.",
    "Los segmentos son una agrupación útil para esta empresa, no categorías objetivas.",
)


def _pct(value: float) -> str:
    return f"{value * 100:.1f} %".replace(".", ",")


def _num(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _int(value: float) -> str:
    return f"{value:.0f}"


# modelo -> [(clave de métrica, etiqueta, formateador, ayuda)]
_METRIC_SPECS: Mapping[str, tuple[tuple[str, str, Callable[[float], str], str], ...]] = {
    DEMAND_MODEL: (
        ("mae", "Error medio absoluto (MAE)", lambda v: f"{_num(v)} t", "Menor es mejor."),
        (
            "mae_baseline",
            "MAE de la línea base ingenua",
            lambda v: f"{_num(v)} t",
            "Repetir el valor de hace 7 días.",
        ),
        ("mape", "Error porcentual (MAPE)", lambda v: f"{_num(v, 1)} %", "Sin días con demanda 0."),
        (
            "mape_baseline",
            "MAPE de la línea base",
            lambda v: f"{_num(v, 1)} %",
            "Misma regla de cálculo.",
        ),
        (
            "p90_coverage",
            "Cobertura del P90",
            _pct,
            "Debería rondar el 90 %: fracción de días reales por debajo del P90.",
        ),
        ("n_test", "Días de prueba", _int, "Partición temporal: los más recientes."),
    ),
    ANOMALY_MODEL: (
        ("n_visits", "Visitas analizadas", _int, ""),
        ("n_flagged", "Visitas marcadas como inusuales", _int, "Aprox. 3 % por diseño."),
    ),
    DELAY_MODEL: (
        ("auc", "AUC", lambda v: _num(v, 3), "0,5 equivale a azar; 1 es perfecto."),
        (
            "brier",
            "Brier",
            lambda v: _num(v, 3),
            "Calibración de la probabilidad; menor es mejor.",
        ),
        ("brier_baseline", "Brier de la predicción ingenua", lambda v: _num(v, 3), "Tasa base."),
        ("precision", "Precisión (umbral 50 %)", _pct, ""),
        ("recall", "Recall (umbral 50 %)", _pct, ""),
        ("base_rate", "Tasa de retrasos en la prueba", _pct, ""),
        ("n_test", "Visitas de prueba", _int, "Partición temporal."),
    ),
    SEGMENT_MODEL: (
        ("k", "Segmentos", _int, "Elegidos por el coeficiente de silueta."),
        ("silhouette", "Silueta", lambda v: _num(v, 2), "Cohesión de los grupos (−1 a 1)."),
        ("n_customers", "Clientes", _int, ""),
    ),
}


class MlService:
    def __init__(
        self,
        reader: HistoryReaderPort,
        forecaster: DemandForecaster,
        detector: AnomalyDetector,
        delay: DelayRiskPredictor,
        miner: PatternMiner,
        registry: ModelRegistryPort,
        clock: ClockPort,
        retrain_every: timedelta = timedelta(hours=24),
    ) -> None:
        self._reader = reader
        self._forecaster = forecaster
        self._detector = detector
        self._delay = delay
        self._miner = miner
        self._registry = registry
        self._clock = clock
        self._retrain_every = retrain_every
        self._lock = threading.RLock()
        self._history: OperationalHistory | None = None
        self._report: PatternsReport | None = None
        self._last_trained: datetime | None = None

    # ------------------------------------------------------------------ entrenamiento
    def train(self) -> list[ModelMetadata]:
        """`TrainModels`: entrena los cuatro modelos con la historia de ESTA empresa."""
        with self._lock:
            history = self._reader.load()
            if history.span_days < MIN_HISTORY_DAYS:
                raise InsufficientDataError(
                    f"Se necesitan al menos {MIN_HISTORY_DAYS} días de historia para entrenar; "
                    f"hay {history.span_days}."
                )
            seed = history.seed if history.seed is not None else DEFAULT_SEED
            now = self._clock.now()
            artifacts: dict[str, TrainedArtifact] = {
                DEMAND_MODEL: self._forecaster.train(history, seed),
                ANOMALY_MODEL: self._detector.train(history, seed),
                DELAY_MODEL: self._delay.train(history, seed),
                SEGMENT_MODEL: self._miner.train(history, seed),
            }
            registered = [
                self._registry.register(name, artifacts[name], now, seed) for name in MODEL_NAMES
            ]
            self._history = history
            self._report = None
            self._last_trained = now
            return registered

    def retrain_if_due(self) -> bool:
        """Reentrenamiento programado: solo si pasó el intervalo desde el último."""
        with self._lock:
            # Nunca entrena en frío: el primer entrenamiento ocurre al primer uso.
            if self._last_trained is None:
                return False
            if self._clock.now() - self._last_trained < self._retrain_every:
                return False
            self.train()
            return True

    def is_trained(self) -> bool:
        return all(self._registry.latest(name) is not None for name in MODEL_NAMES)

    # ------------------------------------------------------------------ patrones
    def report(self) -> PatternsReport:
        """`DetectPatterns`: carga modelos verificados y arma el informe (con caché)."""
        with self._lock:
            if self._report is not None:
                return self._report
            if not self.is_trained():
                self.train()
            history = self._history or self._reader.load()
            self._history = history
            self._report = self._build_report(history)
            return self._report

    def forecast_comparison(self) -> list[ForecastComparison]:
        """Pronóstico del siguiente día frente al percentil histórico, por corredor."""
        report = self.report()
        result: list[ForecastComparison] = []
        for corridor in report.forecasts:
            if not corridor.forecast:
                continue
            first = corridor.forecast[0]
            result.append(
                ForecastComparison(
                    corridor_code=corridor.corridor_code,
                    corridor_name=corridor.corridor_name,
                    day=first.day,
                    p50_t=first.p50_t,
                    p90_t=first.p90_t,
                    baseline_t=first.baseline_t,
                    historical_p90_t=corridor.historical_p90_t,
                )
            )
        return result

    # ------------------------------------------------------------------ interno
    def _build_report(self, history: OperationalHistory) -> PatternsReport:
        loaded = {name: self._registry.load(name) for name in MODEL_NAMES}
        last = history.last_day
        if last is None:
            raise InsufficientDataError("No hay historia para detectar patrones.")
        first_forecast_day = last + timedelta(days=1)

        forecasts = self._forecaster.forecast(
            loaded[DEMAND_MODEL].payload, history, first_forecast_day, FORECAST_HORIZON_DAYS
        )
        by_corridor: dict[str, list[date]] = {}
        for item in forecasts:
            by_corridor.setdefault(item.corridor_code, []).append(item.day)
        corridor_forecasts: list[CorridorForecast] = []
        for code in sorted(history.demand):
            series = history.demand[code]
            recent_from = last - timedelta(days=RECENT_DAYS - 1)
            recent = tuple(
                sorted((d, v) for d, v in series.observations.items() if d >= recent_from)
            )
            window_from = last - timedelta(days=PERCENTILE_WINDOW_DAYS - 1)
            window = [v for d, v in series.observations.items() if d >= window_from]
            historical = percentile_linear(window, DESIGN_FRACTION) if window else None
            corridor_forecasts.append(
                CorridorForecast(
                    corridor_code=code,
                    corridor_name=history.corridor_name(code),
                    recent=recent,
                    forecast=tuple(
                        sorted(
                            (f for f in forecasts if f.corridor_code == code), key=lambda f: f.day
                        )
                    ),
                    historical_p90_t=historical,
                )
            )

        cards = tuple(self._card(name, loaded[name]) for name in MODEL_NAMES)
        return PatternsReport(
            status="ok",
            demo_label="DATOS DE DEMOSTRACIÓN",
            provenance=history.provenance,
            generated_at=self._clock.now(),
            history_from=history.first_day,
            history_to=last,
            models=cards,
            forecasts=tuple(corridor_forecasts),
            anomalies=tuple(self._detector.detect(loaded[ANOMALY_MODEL].payload, history, 10)),
            delay_risks=tuple(self._delay.predict(loaded[DELAY_MODEL].payload, history, 10)),
            segments=tuple(self._miner.segments(loaded[SEGMENT_MODEL].payload, history)),
            limits=LIMITS,
            warnings=(),
        )

    @staticmethod
    def _card(name: str, model: LoadedModel) -> ModelCard:
        lines: list[MetricLine] = []
        for key, label, fmt, hint in _METRIC_SPECS.get(name, ()):
            if key in model.metadata.metrics:
                lines.append(MetricLine(label, fmt(model.metadata.metrics[key]), hint))
        ranked = sorted(model.importances.items(), key=lambda item: item[1], reverse=True)
        return ModelCard(
            metadata=model.metadata,
            title=MODEL_TITLES[name],
            metric_lines=tuple(lines),
            importances=tuple(ranked),
            notes=model.notes,
        )
