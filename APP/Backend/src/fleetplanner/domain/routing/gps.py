"""Posiciones GPS, geocerca de llegada y pérdida de señal (DOCS.MD §7.4 y §7.5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fleetplanner.domain.routing.geo import GeoPoint, haversine_km


@dataclass(frozen=True)
class GpsFix:
    """Una lectura del dispositivo. ``at_min`` son minutos desde la medianoche del día operativo."""

    vehicle_id: str
    at_min: float
    point: GeoPoint
    speed_kmh: float
    engine_on: bool


@dataclass(frozen=True)
class GpsSample:
    """Lo que el dispositivo mediría en un instante (la "verdad" que el simulador lee del plan)."""

    point: GeoPoint
    speed_kmh: float
    engine_on: bool


def distance_m(a: GeoPoint, b: GeoPoint) -> float:
    return haversine_km(a, b) * 1000.0


def fix_age_min(fix: GpsFix, now_min: float) -> float:
    """Antigüedad de la última posición (nunca negativa)."""
    return max(now_min - fix.at_min, 0.0)


def has_no_signal(fix: GpsFix | None, now_min: float, limit_min: float) -> bool:
    """Sin señal si nunca reportó o si la última posición tiene más de ``limit_min`` minutos."""
    return fix is None or fix_age_min(fix, now_min) > limit_min


def geofence_arrival(
    fixes: Sequence[GpsFix], target: GeoPoint, radius_m: float, dwell_min: float
) -> float | None:
    """Minuto en que la llegada queda confirmada por geocerca, o None.

    La llegada se confirma cuando el vehículo permanece dentro de ``radius_m`` del destino durante
    MÁS de ``dwell_min`` minutos seguidos (≈100 m y 5 min en la demo). Salir del círculo reinicia
    la cuenta. Devuelve el minuto de la primera lectura que supera la permanencia.
    """
    run_start: float | None = None
    for fix in sorted(fixes, key=lambda f: f.at_min):
        if distance_m(fix.point, target) <= radius_m:
            if run_start is None:
                run_start = fix.at_min
            if fix.at_min - run_start > dwell_min:
                return fix.at_min
        else:
            run_start = None
    return None
