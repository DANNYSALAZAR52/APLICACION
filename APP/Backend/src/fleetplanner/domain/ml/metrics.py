"""Métricas de evaluación puras (solo librería estándar) y partición temporal sin fuga."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

from fleetplanner.domain.shared.errors import InsufficientDataError, InvalidValueError


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    _same_length(actual, predicted)
    if not actual:
        raise InsufficientDataError("No hay datos para calcular el MAE.")
    return math.fsum(abs(a - p) for a, p in zip(actual, predicted, strict=True)) / len(actual)


def mape(actual: Sequence[float], predicted: Sequence[float]) -> tuple[float | None, int]:
    """MAPE en %, omitiendo los valores reales iguales a cero (denominador cero).

    Devuelve (valor o None si no quedó ningún dato, cantidad de pares omitidos).
    """
    _same_length(actual, predicted)
    pairs = [(a, p) for a, p in zip(actual, predicted, strict=True) if a != 0]
    skipped = len(actual) - len(pairs)
    if not pairs:
        return None, skipped
    return 100.0 * math.fsum(abs(a - p) / abs(a) for a, p in pairs) / len(pairs), skipped


def brier(outcomes: Sequence[bool], probabilities: Sequence[float]) -> float:
    _same_length(outcomes, probabilities)
    if not outcomes:
        raise InsufficientDataError("No hay datos para calcular el Brier.")
    return math.fsum(
        (float(o) - p) ** 2 for o, p in zip(outcomes, probabilities, strict=True)
    ) / len(outcomes)


def auc(outcomes: Sequence[bool], scores: Sequence[float]) -> float | None:
    """Área bajo la curva ROC por rangos (Mann-Whitney). None si falta una de las dos clases."""
    _same_length(outcomes, scores)
    positives = [s for o, s in zip(outcomes, scores, strict=True) if o]
    negatives = [s for o, s in zip(outcomes, scores, strict=True) if not o]
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for n in negatives:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(positives) * len(negatives))


def precision_recall(
    outcomes: Sequence[bool], probabilities: Sequence[float], threshold: float = 0.5
) -> tuple[float | None, float | None]:
    """Precisión y recall con un umbral; None cuando el denominador es cero."""
    _same_length(outcomes, probabilities)
    true_pos = sum(1 for o, p in zip(outcomes, probabilities, strict=True) if o and p >= threshold)
    predicted_pos = sum(1 for p in probabilities if p >= threshold)
    actual_pos = sum(1 for o in outcomes if o)
    precision = true_pos / predicted_pos if predicted_pos else None
    recall = true_pos / actual_pos if actual_pos else None
    return precision, recall


def temporal_cutoff(days: Sequence[date], test_fraction: float) -> date:
    """Primer día del conjunto de prueba: todo lo anterior entrena, lo posterior prueba.

    La partición es por fecha (nunca aleatoria) para que ningún dato futuro llegue al
    entrenamiento.
    """
    if not 0.0 < test_fraction < 1.0:
        raise InvalidValueError("La fracción de prueba debe estar entre 0 y 1.")
    unique = sorted(set(days))
    if len(unique) < 2:
        raise InsufficientDataError("Se necesitan al menos 2 días distintos para particionar.")
    first_test_index = max(1, min(len(unique) - 1, round(len(unique) * (1.0 - test_fraction))))
    return unique[first_test_index]


def _same_length(a: Sequence[object], b: Sequence[object]) -> None:
    if len(a) != len(b):
        raise InvalidValueError("Las secuencias comparadas deben tener la misma longitud.")
