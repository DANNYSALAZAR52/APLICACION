"""Estadísticos puros y deterministas (solo librería estándar)."""

from __future__ import annotations

import math
from collections.abc import Sequence

from fleetplanner.domain.shared.errors import InsufficientDataError, InvalidValueError

# Tolerancia para no inflar un entero por ruido de punto flotante (p. ej. 3.0000000000000004).
_CEIL_TOLERANCE = 1e-9


def mean(values: Sequence[float]) -> float:
    if not values:
        raise InsufficientDataError("No hay datos para calcular el promedio.")
    return math.fsum(values) / len(values)


def sample_std(values: Sequence[float]) -> float:
    """Desviación estándar muestral (n - 1). Requiere al menos dos datos."""
    if len(values) < 2:
        raise InsufficientDataError(
            "Se necesitan al menos 2 datos para calcular la desviación estándar."
        )
    mu = mean(values)
    return math.sqrt(math.fsum((v - mu) ** 2 for v in values) / (len(values) - 1))


def percentile_linear(values: Sequence[float], fraction: float) -> float:
    """Percentil con interpolación lineal (equivale a PERCENTIL.INC de una planilla)."""
    if not values:
        raise InsufficientDataError("No hay datos para calcular el percentil.")
    if not 0.0 <= fraction <= 1.0:
        raise InvalidValueError("El percentil debe estar entre 0 y 1.")
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def percentile_nearest_rank(values: Sequence[int], fraction: float) -> int:
    """Percentil por rango más cercano: devuelve siempre un valor observado (útil para flotas)."""
    if not values:
        raise InsufficientDataError("No hay datos para calcular el percentil.")
    if not 0.0 < fraction <= 1.0:
        raise InvalidValueError("El percentil debe estar en el rango (0, 1].")
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered) - _CEIL_TOLERANCE))
    return ordered[rank - 1]


def ceil_fleet(value: float) -> int:
    """Redondea hacia arriba un número de vehículos sin inflar por ruido de punto flotante."""
    if value < 0:
        raise InvalidValueError("La cantidad de vehículos no puede ser negativa.")
    return math.ceil(value - _CEIL_TOLERANCE)
