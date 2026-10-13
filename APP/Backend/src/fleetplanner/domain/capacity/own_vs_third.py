"""P8. Flota propia vs. terceros, por tipo de vehículo."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacity
from fleetplanner.domain.capacity.models import Corridor, DemandSeries
from fleetplanner.domain.shared.errors import InsufficientDataError, InvalidValueError
from fleetplanner.domain.shared.stats import ceil_fleet, mean


@dataclass(frozen=True)
class OwnFleetCosts:
    """Costos diarios de un tipo de vehículo."""

    fixed_per_day: float
    variable_per_used_vehicle_day: float
    third_party_per_day: float

    def __post_init__(self) -> None:
        if (
            min(self.fixed_per_day, self.variable_per_used_vehicle_day, self.third_party_per_day)
            < 0
        ):
            raise InvalidValueError("Los costos diarios no pueden ser negativos.")


@dataclass(frozen=True)
class CostPoint:
    own_fleet: int
    daily_cost: float


@dataclass(frozen=True)
class OwnVsThirdTypeResult:
    vehicle_type: str
    days_used: int
    optimal_own: int
    optimal_cost_per_day: float
    all_third_party_cost_per_day: float
    all_own_cost_per_day: float
    curve: list[CostPoint]


@dataclass(frozen=True)
class OwnVsThirdResult:
    by_type: Mapping[str, OwnVsThirdTypeResult]

    @property
    def total_own(self) -> int:
        return sum(r.optimal_own for r in self.by_type.values())


def cost_of_own_fleet(requirements: Sequence[int], own: int, costs: OwnFleetCosts) -> float:
    """costo(N) = N·fijo + variable·prom(min(R,N)) + tercero·prom(max(R−N,0))."""
    used = mean([min(r, own) for r in requirements])
    outsourced = mean([max(r - own, 0) for r in requirements])
    return (
        own * costs.fixed_per_day
        + costs.variable_per_used_vehicle_day * used
        + costs.third_party_per_day * outsourced
    )


class OwnVsThirdPartyAnalyzer:
    """Busca la flota propia N de menor costo para cada tipo.

    El espacio de búsqueda se deriva del historial: N va de 0 a max(R). Más allá de max(R) cada
    vehículo propio adicional solo suma costo fijo sin sustituir ningún tercero, por lo que no
    puede ser óptimo; no se usa un tope fijo. En caso de empate se elige el menor N.
    """

    def analyze(
        self,
        daily_requirements: Mapping[str, Sequence[int]],
        costs: Mapping[str, OwnFleetCosts],
    ) -> OwnVsThirdResult:
        results: dict[str, OwnVsThirdTypeResult] = {}
        for vehicle_type, requirements in daily_requirements.items():
            if not requirements:
                raise InsufficientDataError(
                    f"No hay días completos de historial para el tipo {vehicle_type}."
                )
            type_costs = costs[vehicle_type]
            upper = max(requirements)
            curve = [
                CostPoint(n, cost_of_own_fleet(requirements, n, type_costs))
                for n in range(upper + 1)
            ]
            best = min(curve, key=lambda p: (p.daily_cost, p.own_fleet))
            results[vehicle_type] = OwnVsThirdTypeResult(
                vehicle_type=vehicle_type,
                days_used=len(requirements),
                optimal_own=best.own_fleet,
                optimal_cost_per_day=best.daily_cost,
                all_third_party_cost_per_day=curve[0].daily_cost,
                all_own_cost_per_day=curve[-1].daily_cost,
                curve=curve,
            )
        return OwnVsThirdResult(results)


def daily_required_vehicles(
    corridors: list[Corridor],
    capacities: Mapping[str, EffectiveCapacity],
    demand: Mapping[str, DemandSeries],
    window: tuple[date, date],
) -> dict[str, list[int]]:
    """Vehículos requeridos por día y por tipo (R) a partir del historial.

    Regla explícita: solo cuentan los días en que **todos** los corredores tienen observación;
    un día con algún dato ausente se descarta (no se completa con ceros). No se aplica reserva:
    R es la necesidad observada, no la planificada.
    """
    start, end = window
    observations = {code: series.observations for code, series in demand.items()}
    result: dict[str, list[int]] = {}
    day = start
    while day <= end:
        if all(day in observations.get(c.code, {}) for c in corridors):
            fractional: dict[str, float] = {}
            for corridor in corridors:
                needed = (
                    observations[corridor.code][day] / capacities[corridor.code].effective_t_per_day
                )
                key = corridor.assigned_vehicle_type
                fractional[key] = fractional.get(key, 0.0) + needed
            for vehicle_type, value in fractional.items():
                result.setdefault(vehicle_type, []).append(ceil_fleet(value))
        day += timedelta(days=1)
    return result
