"""Riesgo de retraso: clasificador HistGradientBoosting con probabilidad de salir de la ventana.

Variables: hora, día de la semana, carga del pedido, factor de tráfico, paradas restantes,
amplitud de la ventana y cliente (categórica). Partición temporal; se compara con una predicción
ingenua (la tasa base) y se reportan AUC, Brier, precisión y recall.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance

from fleetplanner.adapters.outbound.ml import codec
from fleetplanner.application.dto.ml import TrainedArtifact
from fleetplanner.domain.ml.metrics import auc, brier, precision_recall, temporal_cutoff
from fleetplanner.domain.ml.records import OperationalHistory, ServiceVisit
from fleetplanner.domain.ml.results import DelayRisk
from fleetplanner.domain.shared.errors import InsufficientDataError

FEATURES = (
    "hora",
    "día de la semana",
    "carga del pedido",
    "factor de tráfico",
    "paradas restantes",
    "amplitud de la ventana",
    "cliente",
)
TEST_FRACTION = 0.2
_CUSTOMER_COLUMN = 6


def _row(
    hour: int,
    weekday: int,
    kg: float,
    traffic: float,
    stops: int,
    width: int,
    customer_index: float,
) -> list[float]:
    return [float(hour), float(weekday), kg, traffic, float(stops), float(width), customer_index]


def _classifier(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=120,
        learning_rate=0.06,
        max_depth=4,
        min_samples_leaf=20,
        early_stopping=False,
        categorical_features=[_CUSTOMER_COLUMN],
        random_state=seed,
    )


class SklearnDelayRiskPredictor:
    """Implementa `DelayRiskPredictor` con HistGradientBoostingClassifier."""

    def train(self, history: OperationalHistory, seed: int) -> TrainedArtifact:
        visits = history.visits
        if len(visits) < 200:
            raise InsufficientDataError("Hay muy pocas visitas para entrenar el riesgo de retraso.")
        index = {code: float(i) for i, code in enumerate(sorted({v.customer_code for v in visits}))}
        cutoff = temporal_cutoff([v.day for v in visits], TEST_FRACTION)
        train = [v for v in visits if v.day < cutoff]
        test = [v for v in visits if v.day >= cutoff]
        if not test or len({v.late for v in train}) < 2:
            raise InsufficientDataError("No hay datos suficientes en ambas clases para entrenar.")

        def matrix(items: Sequence[ServiceVisit]) -> np.ndarray:
            return np.array(
                [
                    _row(
                        v.hour,
                        v.day.weekday(),
                        v.order_kg,
                        v.traffic_factor,
                        v.stops_remaining,
                        v.window_width_min,
                        index[v.customer_code],
                    )
                    for v in items
                ]
            )

        y_train = np.array([v.late for v in train])
        y_test = np.array([v.late for v in test])
        model = _classifier(seed).fit(matrix(train), y_train)
        proba = model.predict_proba(matrix(test))[:, 1]

        outcomes = [bool(o) for o in y_test]
        probabilities = [float(p) for p in proba]
        base_rate_train = float(np.mean(y_train))
        precision, recall = precision_recall(outcomes, probabilities, 0.5)
        score = auc(outcomes, probabilities)
        metrics: dict[str, float] = {
            "brier": brier(outcomes, probabilities),
            "brier_baseline": brier(outcomes, [base_rate_train] * len(outcomes)),
            "base_rate": float(np.mean(y_test)),
            "n_test": float(len(test)),
        }
        if score is not None:
            metrics["auc"] = score
        if precision is not None:
            metrics["precision"] = precision
        if recall is not None:
            metrics["recall"] = recall

        importance = permutation_importance(
            model,
            matrix(test),
            y_test,
            n_repeats=5,
            random_state=seed,
            scoring="neg_brier_score",
        )
        raw = np.clip(importance.importances_mean, 0.0, None)
        total = float(raw.sum())
        shares = {
            name: (float(v) / total if total > 0 else 0.0)
            for name, v in zip(FEATURES, raw, strict=True)
        }

        final = _classifier(seed).fit(matrix(visits), np.array([v.late for v in visits]))
        return TrainedArtifact(
            payload=codec.dump({"model": final, "index": index}),
            metrics=metrics,
            importances=shares,
            notes=(
                f"Partición temporal: entrenamiento antes del {cutoff.isoformat()}; "
                "el modelo final se reajusta con toda la historia.",
                "La probabilidad es una estimación calibrada solo en estos datos; no es certeza.",
            ),
            dataset_description=history.provenance,
            library=codec.library_version(),
        )

    def predict(self, payload: bytes, history: OperationalHistory, limit: int) -> list[DelayRisk]:
        """Riesgo por cliente en sus condiciones típicas (hora, carga y tráfico habituales)."""
        bundle: dict[str, Any] = codec.load(payload)
        model: HistGradientBoostingClassifier = bundle["model"]
        index: dict[str, float] = bundle["index"]
        last = history.last_day
        if last is None:
            return []
        next_weekday = (last.weekday() + 1) % 7
        by_customer: dict[str, list[ServiceVisit]] = defaultdict(list)
        for v in history.visits:
            by_customer[v.customer_code].append(v)

        codes: list[str] = []
        rows: list[list[float]] = []
        typical: list[tuple[int, float, float, int]] = []
        for code, items in sorted(by_customer.items()):
            if code not in index:
                continue
            hour = int(statistics.median(v.hour for v in items))
            kg = statistics.median(v.order_kg for v in items)
            traffic = (
                statistics.fmean(v.traffic_factor for v in items if v.hour == hour)
                if any(v.hour == hour for v in items)
                else statistics.fmean(v.traffic_factor for v in items)
            )
            stops = int(statistics.median(v.stops_remaining for v in items))
            width = int(statistics.median(v.window_width_min for v in items))
            codes.append(code)
            rows.append(_row(hour, next_weekday, kg, traffic, stops, width, index[code]))
            typical.append((hour, kg, traffic, stops))
        if not rows:
            return []
        probabilities = model.predict_proba(np.array(rows))[:, 1]
        risks = [
            DelayRisk(
                customer_code=code,
                customer_name=history.customer_name(code),
                hour=hour,
                probability=round(float(p), 3),
                traffic_factor=round(traffic, 2),
                stops_remaining=stops,
                order_kg=round(kg, 0),
            )
            for code, p, (hour, kg, traffic, stops) in zip(
                codes, probabilities, typical, strict=True
            )
        ]
        risks.sort(key=lambda r: r.probability, reverse=True)
        return risks[:limit]
