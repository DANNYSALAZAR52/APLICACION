"""P7. Modelo de optimización del mix de flota (el solver vive detrás de un puerto)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from fleetplanner.domain.capacity.effective_capacity import (
    EffectiveCapacityCalculator,
    vehicle_daily_km,
)
from fleetplanner.domain.capacity.models import CompatibilityMatrix, Corridor, VehicleType
from fleetplanner.domain.shared.errors import InvalidValueError
from fleetplanner.domain.shared.percentage import Percentage


class SolverStatus(StrEnum):
    """Estado verificable del solver. Solo ``OPTIMAL`` autoriza llamar óptima a una solución."""

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    TIME_LIMIT = "time_limit"
    ERROR = "error"


@dataclass(frozen=True)
class FleetMixProblem:
    """Datos del MIP: minimizar costo fijo·y + costo variable·x.

    s.a. Σ_t cap[r,t]·x[r,t] ≥ required_t[r];  Σ_r x[r,t] ≤ y[t];  x,y enteras ≥ 0;
    x[r,t] solo existe si la combinación es compatible.
    """

    corridors: tuple[str, ...]
    vehicle_types: tuple[str, ...]
    required_t: Mapping[str, float]
    capacity_t: Mapping[tuple[str, str], float]
    fixed_cost_per_day: Mapping[str, float]
    variable_cost_per_day: Mapping[tuple[str, str], float]

    def unservable_corridors(self) -> list[str]:
        """Corredores con demanda positiva y ninguna combinación compatible."""
        covered = {r for r, _ in self.capacity_t}
        return [r for r in self.corridors if self.required_t[r] > 0 and r not in covered]


@dataclass(frozen=True)
class FleetMixSolution:
    status: SolverStatus
    assignments: Mapping[tuple[str, str], int] = field(default_factory=dict)
    fleet_by_type: Mapping[str, int] = field(default_factory=dict)
    total_cost_per_day: float | None = None
    message: str = ""

    @property
    def total_vehicles(self) -> int:
        return sum(self.fleet_by_type.values())

    @property
    def has_solution(self) -> bool:
        return self.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE) or (
            self.status is SolverStatus.TIME_LIMIT and bool(self.fleet_by_type)
        )


class FleetMixProblemBuilder:
    """Arma el problema del mix a partir de maestros y demanda de diseño."""

    def __init__(
        self,
        capacity_calculator: EffectiveCapacityCalculator,
        reserve: Percentage,
        days_per_month: int,
    ) -> None:
        self._capacity = capacity_calculator
        self._reserve = reserve
        self._days_per_month = days_per_month

    def build(
        self,
        corridors: list[Corridor],
        vehicle_types: Mapping[str, VehicleType],
        compatibility: CompatibilityMatrix,
        design_demand_t: Mapping[str, float],
    ) -> FleetMixProblem:
        capacity: dict[tuple[str, str], float] = {}
        variable: dict[tuple[str, str], float] = {}
        required: dict[str, float] = {}
        for corridor in corridors:
            if corridor.code not in design_demand_t:
                raise InvalidValueError(
                    f"Falta la demanda del corredor {corridor.code}; no se asume cero."
                )
            required[corridor.code] = design_demand_t[corridor.code] * (
                1.0 + self._reserve.fraction
            )
            for type_name in compatibility.types_for(corridor.code):
                vehicle = vehicle_types[type_name]
                effective = self._capacity.calculate(corridor, vehicle)
                capacity[(corridor.code, type_name)] = effective.effective_t_per_day
                variable[(corridor.code, type_name)] = vehicle.variable_cost_per_km * (
                    vehicle_daily_km(corridor, effective)
                )
        return FleetMixProblem(
            corridors=tuple(c.code for c in corridors),
            vehicle_types=tuple(sorted(vehicle_types)),
            required_t=required,
            capacity_t=capacity,
            fixed_cost_per_day={
                name: vt.fixed_cost_per_day(self._days_per_month)
                for name, vt in vehicle_types.items()
            },
            variable_cost_per_day=variable,
        )
