"""P2. Ciclo de viaje y capacidad efectiva por vehículo."""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.domain.capacity.models import Corridor, OeeFactors, VehicleType


@dataclass(frozen=True)
class EffectiveCapacity:
    """Capacidad efectiva de un tipo de vehículo operando un corredor."""

    corridor_code: str
    vehicle_type: str
    cycle_h: float
    trips_per_day: float
    oee: float
    effective_t_per_day: float


def trip_cycle_hours(corridor: Corridor) -> float:
    """Ciclo de viaje en horas.

    cargue + espera muelle + 2·(km/velocidad) + paradas·min/60 + espera en cliente.
    """
    transit_round_trip_h = 2.0 * corridor.one_way_km / corridor.average_speed_kmh
    stops_h = corridor.stops * corridor.minutes_per_stop / 60.0
    return (
        corridor.loading_h
        + corridor.dock_wait_h
        + transit_round_trip_h
        + stops_h
        + corridor.customer_wait_h
    )


def vehicle_daily_km(corridor: Corridor, capacity: EffectiveCapacity) -> float:
    """Km recorridos por un vehículo en un día de operación del corredor.

    Viajes efectivos (viajes/día × OEE) × recorrido ida y vuelta. Es la base del costo variable
    modelado (decisión documentada en ``docs/DECISIONES.md``).
    """
    return capacity.trips_per_day * capacity.oee * 2.0 * corridor.one_way_km


class EffectiveCapacityCalculator:
    """capacidad_efectiva_t_dia = capacidad_t · %llenado · viajes_dia · OEE."""

    def __init__(self, oee: OeeFactors) -> None:
        self._oee = oee

    def calculate(self, corridor: Corridor, vehicle_type: VehicleType) -> EffectiveCapacity:
        cycle_h = trip_cycle_hours(corridor)
        # Ciclo > 0 está garantizado: km y velocidad son positivos (invariantes de Corridor).
        trips_per_day = corridor.operating_hours / cycle_h
        effective = vehicle_type.capacity_t * corridor.fill.fraction * trips_per_day * self._oee.oee
        return EffectiveCapacity(
            corridor_code=corridor.code,
            vehicle_type=vehicle_type.name,
            cycle_h=cycle_h,
            trips_per_day=trips_per_day,
            oee=self._oee.oee,
            effective_t_per_day=effective,
        )
