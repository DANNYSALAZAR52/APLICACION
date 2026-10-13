"""P9. KPI del tablero de capacidad."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacity
from fleetplanner.domain.capacity.fleet_requirement import FleetRequirement
from fleetplanner.domain.capacity.models import Corridor, VehicleType


@dataclass(frozen=True)
class CapacityKpis:
    """KPI calculables con los datos del módulo de capacidad.

    ``otif`` no se calcula aquí: depende de entregas reales/simuladas del módulo de ruteo y se
    declara no disponible (``None``) en vez de inventarlo.
    """

    fleet_utilization: float | None
    oee: float
    fill_pct: float
    empty_km_pct: float
    daily_cost: float
    cost_per_ton_km: float | None
    cost_per_ton: float | None
    otif: float | None = None


class CapacityKpiCalculator:
    """Calcula los KPI sobre la flota requerida por balance.

    Definiciones (ver ``docs/DECISIONES.md``):

    * utilización de flota = vehículos fraccionales requeridos (sin reserva) / flota actual;
      un valor > 1 indica déficit.
    * llenado = promedio del % de llenado ponderado por demanda.
    * km en vacío = km sin carga / km totales, con viajes = demanda / (capacidad · llenado).
    * costo diario = flota requerida · costo fijo diario + Σ costo/km · km recorridos.
    * costo por t-km = costo diario / Σ (t · km de ida); costo por tonelada = costo / Σ t.
    """

    def __init__(self, days_per_month: int) -> None:
        self._days_per_month = days_per_month

    def calculate(
        self,
        corridors: list[Corridor],
        vehicle_types: Mapping[str, VehicleType],
        design_demand_t: Mapping[str, float],
        capacities: Mapping[str, EffectiveCapacity],
        requirement: FleetRequirement,
    ) -> CapacityKpis:
        total_t = 0.0
        total_t_km = 0.0
        weighted_fill = 0.0
        total_km = 0.0
        empty_km = 0.0
        variable_cost = 0.0
        for corridor in corridors:
            demand = design_demand_t[corridor.code]
            vehicle = vehicle_types[corridor.assigned_vehicle_type]
            trips = demand / (vehicle.capacity_t * corridor.fill.fraction)
            round_trip_km = 2.0 * corridor.one_way_km
            total_t += demand
            total_t_km += demand * corridor.one_way_km
            weighted_fill += demand * corridor.fill.fraction
            total_km += trips * round_trip_km
            empty_km += trips * corridor.one_way_km * (1.0 - corridor.backhaul.fraction)
            variable_cost += vehicle.variable_cost_per_km * trips * round_trip_km

        fixed_cost = sum(
            n * vehicle_types[t].fixed_cost_per_day(self._days_per_month)
            for t, n in requirement.required_by_type.items()
        )
        daily_cost = fixed_cost + variable_cost
        current = requirement.total_current
        fractional = sum(requirement.fractional_by_type.values())
        any_capacity = next(iter(capacities.values()), None)
        return CapacityKpis(
            fleet_utilization=fractional / current if current > 0 else None,
            oee=any_capacity.oee if any_capacity else 0.0,
            fill_pct=weighted_fill / total_t if total_t > 0 else 0.0,
            empty_km_pct=empty_km / total_km if total_km > 0 else 0.0,
            daily_cost=daily_cost,
            cost_per_ton_km=daily_cost / total_t_km if total_t_km > 0 else None,
            cost_per_ton=daily_cost / total_t if total_t > 0 else None,
        )
