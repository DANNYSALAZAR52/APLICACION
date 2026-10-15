"""Enlaces de navegación a Google Maps con el formato oficial de URL (``maps/dir/?api=1``).

Es solo un enlace que abre la aplicación de mapas del teléfono: NO es una integración con la API
de Google, no usa claves ni cobra. Google limita los puntos intermedios por enlace; si la ruta
tiene más paradas se generan varios enlaces encadenados (cada tramo arranca donde terminó el
anterior).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from fleetplanner.domain.routing.geo import GeoPoint

MAPS_DIRECTIONS_URL = "https://www.google.com/maps/dir/"
MAX_WAYPOINTS = 9  # puntos intermedios por enlace (límite documentado de las URL de Google Maps)


@dataclass(frozen=True)
class NavLeg:
    """Un enlace de navegación y qué tramo de la lista de paradas cubre (base 0, fin exclusivo)."""

    url: str
    first: int
    last: int


def _coord(point: GeoPoint) -> str:
    return f"{point.lat:.6f},{point.lon:.6f}"


def directions_url(
    destination: GeoPoint,
    waypoints: Sequence[GeoPoint] = (),
    origin: GeoPoint | None = None,
) -> str:
    """URL de indicaciones. Sin ``origin`` Google Maps usa la ubicación actual del teléfono."""
    params: list[tuple[str, str]] = [("api", "1")]
    if origin is not None:
        params.append(("origin", _coord(origin)))
    params.append(("destination", _coord(destination)))
    if waypoints:
        params.append(("waypoints", "|".join(_coord(p) for p in waypoints)))
    params.append(("travelmode", "driving"))
    return f"{MAPS_DIRECTIONS_URL}?{urlencode(params, quote_via=quote, safe=',')}"


def navigation_legs(
    points: Sequence[GeoPoint],
    origin: GeoPoint | None = None,
    max_waypoints: int = MAX_WAYPOINTS,
) -> list[NavLeg]:
    """Divide ``points`` (en el orden de visita) en enlaces de a lo sumo ``max_waypoints`` + 1."""
    if max_waypoints < 0:
        raise ValueError("El máximo de puntos intermedios no puede ser negativo.")
    size = max_waypoints + 1
    legs: list[NavLeg] = []
    start = 0
    previous_end = origin
    while start < len(points):
        chunk = points[start : start + size]
        url = directions_url(chunk[-1], chunk[:-1], previous_end)
        legs.append(NavLeg(url, start, start + len(chunk)))
        previous_end = chunk[-1]
        start += size
    return legs
