"""P5. Flota Lean."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from fleetplanner.domain.capacity.effective_capacity import trip_cycle_hours
from fleetplanner.domain.capacity.models import Corridor, VehicleType
from fleetplanner.domain.shared.errors import InvalidValueError
from fleetplanner.domain.shared.percentage import Percentage
from fleetplanner.domain.shared.stats import ceil_fleet


@dataclass(frozen=True)
class LeanTargets:
    """Metas Lean editables (reducciones sobre cada tiempo) y colchón Heijunka."""

    dock_wait_reduction: Percentage
    loading_reduction: Percentage
    stop_time_reduction: Percentage
    customer_wait_reduction: Percentage
    heijunka_buffer: Percentage
    target_oee: Percentage

    def __post_init__(self) -> None:
        if self.target_oee.fraction <= 0:
            raise InvalidValueError("El OEE objetivo debe ser mayor que 0 %.")


@dataclass(frozen=True)
class LeanCorridorResult:
    corridor_code: str
    standard_cycle_h: float
    trips_required: float
    fleet_fractional: float
    value_added_pct: float
    waste_pct: float
    takt_min: float


@dataclass(frozen=True)
class LeanResult:
    by_corridor: list[LeanCorridorResult]
    fractional_by_type: Mapping[str, float]
    required_by_type: Mapping[str, int]

    @property
    def total_required(self) -> int:
        return sum(self.required_by_type.values())


def standard_corridor(corridor: Corridor, targets: LeanTargets) -> Corridor:
    """Corredor con los tiempos reducidos según las metas Lean."""
    return replace(
        corridor,
        dock_wait_h=corridor.dock_wait_h * (1.0 - targets.dock_wait_reduction.fraction),
        loading_h=corridor.loading_h * (1.0 - targets.loading_reduction.fraction),
        minutes_per_stop=corridor.minutes_per_stop * (1.0 - targets.stop_time_reduction.fraction),
        customer_wait_h=corridor.customer_wait_h * (1.0 - targets.customer_wait_reduction.fraction),
    )


class LeanFleetCalculator:
    """flota_lean = (viajes_requeridos · ciclo_estándar) / (horas_operativas · OEE_objetivo).

    Definiciones (decisión documentada, ver ``docs/DECISIONES.md``):

    * ``viajes_requeridos = demanda_promedio · (1 + colchón) / (capacidad_t · %llenado)``.
    * % valor agregado = tránsito cargado / ciclo, con tránsito cargado = ida + la fracción de
      retorno con backhaul.
    * % muda = (espera en muelle + espera en cliente + retorno vacío) / ciclo.
    * takt de despacho = minutos operativos / viajes requeridos.
    """

    def __init__(self, targets: LeanTargets) -> None:
        self._targets = targets

    def calculate(
        self,
        corridors: list[Corridor],
        vehicle_types: Mapping[str, VehicleType],
        mean_demand_t: Mapping[str, float],
    ) -> LeanResult:
        results: list[LeanCorridorResult] = []
        fractional_by_type: dict[str, float] = {}
        for corridor in corridors:
            if corridor.code not in mean_demand_t:
                raise InvalidValueError(
                    f"Falta la demanda promedio del corredor {corridor.code}; no se asume cero."
                )
            vehicle = vehicle_types[corridor.assigned_vehicle_type]
            std = standard_corridor(corridor, self._targets)
            cycle_h = trip_cycle_hours(std)
            demand = mean_demand_t[corridor.code] * (1.0 + self._targets.heijunka_buffer.fraction)
            trips = demand / (vehicle.capacity_t * corridor.fill.fraction)
            fleet = (trips * cycle_h) / (
                corridor.operating_hours * self._targets.target_oee.fraction
            )

            one_way_h = corridor.one_way_km / corridor.average_speed_kmh
            empty_return_h = one_way_h * (1.0 - corridor.backhaul.fraction)
            loaded_transit_h = one_way_h * (1.0 + corridor.backhaul.fraction)
            waste_h = std.dock_wait_h + std.customer_wait_h + empty_return_h
            takt = (corridor.operating_hours * 60.0 / trips) if trips > 0 else float("inf")
            results.append(
                LeanCorridorResult(
                    corridor_code=corridor.code,
                    standard_cycle_h=cycle_h,
                    trips_required=trips,
                    fleet_fractional=fleet,
                    value_added_pct=loaded_transit_h / cycle_h,
                    waste_pct=waste_h / cycle_h,
                    takt_min=takt,
                )
            )
            fractional_by_type[corridor.assigned_vehicle_type] = (
                fractional_by_type.get(corridor.assigned_vehicle_type, 0.0) + fleet
            )
        required = {t: ceil_fleet(f) for t, f in fractional_by_type.items()}
        return LeanResult(results, fractional_by_type, required)
