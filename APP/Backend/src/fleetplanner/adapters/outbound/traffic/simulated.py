"""DEMO-ONLY: proveedor de tiempos simulado y respaldo por perfil de velocidades.

* Distancia vial = Haversine × 1,35 (aproximación del prototipo; no sigue calles).
* Tiempo = km / velocidad de la hora de salida × 60, según el `speed_profile` (DOCS.MD §7.1).
* Un cierre activo cuyo radio toca origen, destino o punto medio multiplica el tiempo por su factor.
* `SimulatedTrafficProvider` añade una congestión "en vivo" inventada por hora y puede dejar de
  responder (para demostrar el respaldo). `SpeedProfileTimeEstimator` es ese respaldo: no afirma
  tráfico en vivo.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from functools import lru_cache

from fleetplanner.application.ports.outbound.routing import TrafficProviderUnavailable
from fleetplanner.domain.routing.evaluation import TravelLeg
from fleetplanner.domain.routing.events import Closure
from fleetplanner.domain.routing.geo import GeoPoint, haversine_km
from fleetplanner.domain.shared.errors import InvalidValueError

ROAD_FACTOR = 1.35  # DEMO-ONLY: distancia vial ≈ línea recta × 1,35

# km/h por hora del día (0–23); mínimo 5 y máximo 90 según DOCS.MD §8.
DEFAULT_SPEED_PROFILE: Mapping[int, float] = {
    **dict.fromkeys(range(0, 5), 35.0),
    5: 30.0, 6: 24.0, 7: 18.0, 8: 16.0, 9: 20.0, 10: 22.0, 11: 22.0, 12: 20.0, 13: 20.0,
    14: 22.0, 15: 21.0, 16: 18.0, 17: 15.0, 18: 14.0, 19: 18.0, 20: 24.0, 21: 28.0,
    22: 32.0, 23: 35.0,
}  # fmt: skip

# Congestión adicional "en vivo" que solo agrega el proveedor simulado (DEMO-ONLY).
_LIVE_CONGESTION: Mapping[int, float] = {7: 1.10, 8: 1.15, 12: 1.05, 17: 1.12, 18: 1.15}


def _validate(profile: Mapping[int, float]) -> Mapping[int, float]:
    if set(profile) != set(range(24)):
        raise InvalidValueError("El perfil de velocidades debe tener las 24 horas (0 a 23).")
    for hour, speed in profile.items():
        if not 5 <= speed <= 90:
            raise InvalidValueError(
                f"La velocidad de la hora {hour} ({speed:g} km/h) debe estar entre 5 y 90 km/h."
            )
    return profile


@lru_cache(maxsize=500_000)
def _road_km(a: GeoPoint, b: GeoPoint) -> float:
    return haversine_km(a, b) * ROAD_FACTOR


@lru_cache(maxsize=500_000)
def _touches(closure: Closure, a: GeoPoint, b: GeoPoint) -> bool:
    return closure.touches(a, b)


def _factor(closures: Sequence[Closure], a: GeoPoint, b: GeoPoint, depart_min: float) -> float:
    best = 1.0
    for c in closures:
        if c.factor > best and c.is_active_at(depart_min) and _touches(c, a, b):
            best = c.factor
    return best


class SpeedProfileTimeEstimator:
    """Respaldo: velocidad por hora y cierres conocidos; sin congestión en vivo."""

    def __init__(self, profile: Mapping[int, float] = DEFAULT_SPEED_PROFILE) -> None:
        self._profile = _validate(profile)

    def _live_factor(self, hour: int) -> float:
        return 1.0

    def estimate(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_min: float,
        closures: Sequence[Closure],
    ) -> TravelLeg:
        km = _road_km(origin, destination)
        hour = int(depart_min // 60) % 24
        minutes = km / self._profile[hour] * 60.0 * self._live_factor(hour)
        return TravelLeg(minutes * _factor(closures, origin, destination, depart_min), km)


class SimulatedTrafficProvider(SpeedProfileTimeEstimator):
    """Proveedor con congestión inventada por hora que puede "caerse" a pedido de la demo."""

    def __init__(self, profile: Mapping[int, float] = DEFAULT_SPEED_PROFILE) -> None:
        super().__init__(profile)
        self._available = True
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        with self._lock:
            return self._available

    def set_available(self, available: bool) -> None:
        with self._lock:
            self._available = available

    def _live_factor(self, hour: int) -> float:
        return _LIVE_CONGESTION.get(hour, 1.0)

    def estimate(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_min: float,
        closures: Sequence[Closure],
    ) -> TravelLeg:
        if not self.is_available():
            raise TrafficProviderUnavailable("El proveedor de tiempos simulado no responde.")
        return super().estimate(origin, destination, depart_min, closures)
