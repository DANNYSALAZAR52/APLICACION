"""Puntos geográficos y distancia en línea recta (sin proveedores de mapas)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from fleetplanner.domain.shared.errors import InvalidValueError

# Validación geográfica inicial de Colombia (DOCS.MD §8).
COLOMBIA_LAT = (-4.3, 13.5)
COLOMBIA_LON = (-82.0, -66.0)
# Caja aproximada de Bogotá/Funza: fuera de ella un cliente urbano se marca para revisión.
URBAN_LAT = (4.45, 4.85)
URBAN_LON = (-74.30, -73.95)

_EARTH_RADIUS_KM = 6371.0088


def _es(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def coordinate_issues(lat: float, lon: float) -> list[str]:
    """Problemas de una coordenada, en español y con qué corregir. Lista vacía si es válida."""
    issues: list[str] = []
    if not COLOMBIA_LAT[0] <= lat <= COLOMBIA_LAT[1]:
        issues.append(
            f"La latitud {_es(lat)} está fuera de Colombia (debe estar entre "
            f"{_es(COLOMBIA_LAT[0])} y {_es(COLOMBIA_LAT[1])}); revise que no esté invertida "
            "con la longitud."
        )
    if not COLOMBIA_LON[0] <= lon <= COLOMBIA_LON[1]:
        issues.append(
            f"La longitud {_es(lon)} está fuera de Colombia (debe estar entre "
            f"{_es(COLOMBIA_LON[0])} y {_es(COLOMBIA_LON[1])})."
        )
    return issues


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float

    def __post_init__(self) -> None:
        issues = coordinate_issues(self.lat, self.lon)
        if issues:
            raise InvalidValueError(" ".join(issues))

    def is_in_urban_area(self) -> bool:
        return URBAN_LAT[0] <= self.lat <= URBAN_LAT[1] and URBAN_LON[0] <= self.lon <= URBAN_LON[1]


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Distancia en línea recta entre dos puntos (gran círculo)."""
    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    d_phi = phi2 - phi1
    d_lambda = math.radians(b.lon - a.lon)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def interpolate(a: GeoPoint, b: GeoPoint, fraction: float) -> GeoPoint:
    """Punto a ``fraction`` (0..1) del trayecto recto de ``a`` hacia ``b`` (DEMO-ONLY)."""
    f = min(1.0, max(0.0, fraction))
    return GeoPoint(a.lat + (b.lat - a.lat) * f, a.lon + (b.lon - a.lon) * f)


def midpoint(a: GeoPoint, b: GeoPoint) -> GeoPoint:
    return interpolate(a, b, 0.5)
