"""DEMO-ONLY: tiempos de viaje simulados (Haversine × 1,35 + perfil de velocidades).

En producción un adaptador de `TrafficTimePort` con un proveedor real sustituye a estos dos
sin tocar dominio ni casos de uso (ver `docs/DEUDA_DEMO.md`).
"""

from fleetplanner.adapters.outbound.traffic.simulated import (
    DEFAULT_SPEED_PROFILE,
    SimulatedTrafficProvider,
    SpeedProfileTimeEstimator,
)

__all__ = ["DEFAULT_SPEED_PROFILE", "SimulatedTrafficProvider", "SpeedProfileTimeEstimator"]
