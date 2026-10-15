"""Pronóstico diario por corredor: gradient boosting con regresión por cuantiles (P50 y P90).

Variables (DOCS.MD §13.1): día de la semana, mes, día del mes, festivo de Colombia, quincena,
valor de hace 7 y 14 días y promedio de la semana previa. Todas se conocen al momento de
pronosticar hasta 7 días hacia adelante. Evaluación con partición TEMPORAL (los días más
recientes) frente a una línea base ingenua estacional (el valor de hace 7 días).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from fleetplanner.adapters.outbound.ml import codec
from fleetplanner.application.dto.ml import TrainedArtifact
from fleetplanner.domain.ml.calendar_co import is_holiday, is_quincena
from fleetplanner.domain.ml.metrics import mae, mape, temporal_cutoff
from fleetplanner.domain.ml.records import OperationalHistory
from fleetplanner.domain.ml.results import Forecast
from fleetplanner.domain.shared.errors import InsufficientDataError

FEATURES = (
    "día de la semana",
    "mes",
    "día del mes",
    "festivo",
    "quincena",
    "valor de hace 7 días",
    "valor de hace 14 días",
    "promedio de la semana previa",
)
TEST_FRACTION = 0.2
MAX_HORIZON_DAYS = 7
_MIN_TRAIN_ROWS = 30


def _features(day: date, obs: Mapping[date, float], level: float) -> list[float]:
    lag7 = obs.get(day - timedelta(days=7))
    lag14 = obs.get(day - timedelta(days=14))
    week = [obs[d] for k in range(7, 14) if (d := day - timedelta(days=k)) in obs]
    nan = float("nan")
    return [
        float(day.weekday()),
        float(day.month),
        float(day.day),
        1.0 if is_holiday(day) else 0.0,
        1.0 if is_quincena(day) else 0.0,
        lag7 / level if lag7 is not None else nan,
        lag14 / level if lag14 is not None else nan,
        (math.fsum(week) / len(week)) / level if week else nan,
    ]


def _naive(day: date, obs: Mapping[date, float], fallback: float) -> float:
    """Línea base ingenua estacional: el valor de hace 7 días (o el nivel si falta)."""
    return obs.get(day - timedelta(days=7), fallback)


def _regressor(quantile: float, seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="quantile",
        quantile=quantile,
        max_iter=120,
        learning_rate=0.08,
        max_depth=4,
        min_samples_leaf=10,
        early_stopping=False,
        random_state=seed,
    )


class SklearnDemandForecaster:
    """Implementa `DemandForecaster` con HistGradientBoosting (cuantiles 0,5 y 0,9)."""

    def train(self, history: OperationalHistory, seed: int) -> TrainedArtifact:
        all_days = sorted({d for s in history.demand.values() for d in s.observations})
        if len(all_days) < 20:
            raise InsufficientDataError("Hay muy pocos días con demanda para entrenar.")
        cutoff = temporal_cutoff(all_days, TEST_FRACTION)

        train_x: list[list[float]] = []
        train_y: list[float] = []
        test_x: list[list[float]] = []
        test_y: list[float] = []
        test_actual: list[float] = []
        test_level: list[float] = []
        test_baseline: list[float] = []
        for series in history.demand.values():
            obs = series.observations
            train_values = [v for d, v in obs.items() if d < cutoff]
            if len(train_values) < 5:
                continue
            level = max(math.fsum(train_values) / len(train_values), 1e-6)
            for day, value in obs.items():
                row = _features(day, obs, level)
                if day < cutoff:
                    train_x.append(row)
                    train_y.append(value / level)
                else:
                    test_x.append(row)
                    test_y.append(value / level)
                    test_actual.append(value)
                    test_level.append(level)
                    test_baseline.append(_naive(day, obs, level))
        if len(train_x) < _MIN_TRAIN_ROWS or not test_x:
            raise InsufficientDataError("No hay datos suficientes para entrenar y evaluar.")

        x_train, y_train = np.array(train_x), np.array(train_y)
        x_test, y_test = np.array(test_x), np.array(test_y)
        median = _regressor(0.5, seed).fit(x_train, y_train)
        upper = _regressor(0.9, seed).fit(x_train, y_train)

        levels_arr = np.array(test_level)
        pred50 = median.predict(x_test) * levels_arr
        pred90 = np.maximum(upper.predict(x_test) * levels_arr, pred50)
        metrics: dict[str, float] = {
            "mae": mae(test_actual, pred50.tolist()),
            "mae_baseline": mae(test_actual, test_baseline),
            "p90_coverage": float(np.mean(np.array(test_actual) <= pred90)),
            "n_test": float(len(test_actual)),
        }
        model_mape, _ = mape(test_actual, pred50.tolist())
        baseline_mape, _ = mape(test_actual, test_baseline)
        if model_mape is not None:
            metrics["mape"] = model_mape
        if baseline_mape is not None:
            metrics["mape_baseline"] = baseline_mape

        importance = permutation_importance(
            median,
            x_test,
            y_test,
            n_repeats=5,
            random_state=seed,
            scoring="neg_mean_absolute_error",
        )
        raw = np.clip(importance.importances_mean, 0.0, None)
        total = float(raw.sum())
        shares = {
            name: (float(v) / total if total > 0 else 0.0)
            for name, v in zip(FEATURES, raw, strict=True)
        }

        # Modelo final: mismos hiperparámetros, reajustado con TODA la historia disponible.
        final_x: list[list[float]] = []
        final_y: list[float] = []
        levels: dict[str, float] = {}
        for code, series in history.demand.items():
            values = list(series.observations.values())
            if not values:
                continue
            level = max(math.fsum(values) / len(values), 1e-6)
            levels[code] = level
            for day, value in series.observations.items():
                final_x.append(_features(day, series.observations, level))
                final_y.append(value / level)
        final50 = _regressor(0.5, seed).fit(np.array(final_x), np.array(final_y))
        final90 = _regressor(0.9, seed).fit(np.array(final_x), np.array(final_y))

        cutoff_text = cutoff.isoformat()
        return TrainedArtifact(
            payload=codec.dump({"q50": final50, "q90": final90, "levels": levels}),
            metrics=metrics,
            importances=shares,
            notes=(
                f"Partición temporal: entrenamiento antes del {cutoff_text}, prueba desde esa "
                "fecha. El modelo final se reajusta con toda la historia.",
                "Horizonte máximo de 7 días.",
            ),
            dataset_description=history.provenance,
            library=codec.library_version(),
        )

    def forecast(
        self, payload: bytes, history: OperationalHistory, first_day: date, horizon_days: int
    ) -> list[Forecast]:
        if not 1 <= horizon_days <= MAX_HORIZON_DAYS:
            raise InsufficientDataError(
                f"El horizonte debe estar entre 1 y {MAX_HORIZON_DAYS} días."
            )
        bundle: dict[str, Any] = codec.load(payload)
        levels: Mapping[str, float] = bundle["levels"]
        result: list[Forecast] = []
        for code in sorted(history.demand):
            level = levels.get(code)
            if level is None:
                continue
            obs = history.demand[code].observations
            days = [first_day + timedelta(days=k) for k in range(horizon_days)]
            matrix = np.array([_features(d, obs, level) for d in days])
            p50 = np.clip(bundle["q50"].predict(matrix) * level, 0.0, None)
            p90 = np.maximum(bundle["q90"].predict(matrix) * level, p50)
            for day, low, high in zip(days, p50, p90, strict=True):
                result.append(
                    Forecast(
                        corridor_code=code,
                        day=day,
                        p50_t=round(float(low), 2),
                        p90_t=round(float(high), 2),
                        baseline_t=round(_naive(day, obs, level), 2),
                    )
                )
        return result
