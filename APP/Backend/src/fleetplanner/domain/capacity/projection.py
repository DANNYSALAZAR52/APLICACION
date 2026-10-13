"""P4. Proyección de flota a cinco años por escenario."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacity
from fleetplanner.domain.capacity.fleet_requirement import (
    FleetRequirement,
    FleetRequirementCalculator,
)
from fleetplanner.domain.capacity.models import Corridor
from fleetplanner.domain.shared.errors import InvalidValueError


@dataclass(frozen=True)
class GrowthScenario:
    """Escenario de crecimiento (maestro `growth_scenario`).

    ``cagr`` y ``route_adjustments`` son tasas anuales como fracción (0.06 = 6 %); pueden ser
    negativas (escenario pesimista) pero la tasa efectiva debe ser mayor que −100 %.

    Interpretación de ``new_volume_t`` (SUPUESTO DE DEMO, pendiente de validar con negocio, ver
    ``docs/DECISIONES.md``): toneladas/día adicionales por corredor que se **suman en cada año
    desde ``entry_year``** (inclusive) sin crecer con el CAGR.
    """

    name: str
    cagr: float
    route_adjustments: Mapping[str, float] = field(default_factory=dict)
    new_volume_t: Mapping[str, float] = field(default_factory=dict)
    entry_year: int = 0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidValueError("El escenario de crecimiento debe tener nombre.")
        for code, tons in self.new_volume_t.items():
            if tons < 0:
                raise InvalidValueError(
                    f"El volumen nuevo del corredor {code} no puede ser negativo."
                )

    def rate_for(self, corridor_code: str) -> float:
        rate = self.cagr + self.route_adjustments.get(corridor_code, 0.0)
        if rate <= -1.0:
            raise InvalidValueError(
                f"La tasa de crecimiento del corredor {corridor_code} en el escenario "
                f"'{self.name}' debe ser mayor que −100 %."
            )
        return rate


def project_demand(
    design_t: float, corridor_code: str, scenario: GrowthScenario, base_year: int, year: int
) -> float:
    """demanda_n = demanda_diseno·(1+tasa)^n + volumen_nuevo (si year ≥ entry_year)."""
    n = year - base_year
    if n < 0:
        raise InvalidValueError("El año proyectado no puede ser anterior al año base.")
    demand = design_t * (1.0 + scenario.rate_for(corridor_code)) ** n
    if year >= scenario.entry_year:
        demand += scenario.new_volume_t.get(corridor_code, 0.0)
    return demand


@dataclass(frozen=True)
class YearProjection:
    year: int
    demand_t_by_corridor: Mapping[str, float]
    requirement: FleetRequirement


@dataclass(frozen=True)
class ScenarioProjection:
    scenario: str
    years: list[YearProjection]
    first_deficit_year: int | None
    first_deficit_year_by_type: Mapping[str, int | None]


class FiveYearProjector:
    """Repite P3 para cada año (base+1 … base+horizonte) y escenario."""

    def __init__(self, requirement_calculator: FleetRequirementCalculator, horizon_years: int = 5):
        if horizon_years < 1:
            raise InvalidValueError("El horizonte de proyección debe ser de al menos un año.")
        self._calculator = requirement_calculator
        self._horizon = horizon_years

    def project(
        self,
        scenario: GrowthScenario,
        base_year: int,
        corridors: list[Corridor],
        design_demand_t: Mapping[str, float],
        capacities: Mapping[str, EffectiveCapacity],
        current_fleet: Mapping[str, int],
    ) -> ScenarioProjection:
        years: list[YearProjection] = []
        for year in range(base_year + 1, base_year + self._horizon + 1):
            demand = {
                c.code: project_demand(design_demand_t[c.code], c.code, scenario, base_year, year)
                for c in corridors
            }
            requirement = self._calculator.calculate(corridors, demand, capacities, current_fleet)
            years.append(YearProjection(year, demand, requirement))

        first_total = next(
            (y.year for y in years if y.requirement.total_required > y.requirement.total_current),
            None,
        )
        types = {t for y in years for t in y.requirement.required_by_type}
        first_by_type: dict[str, int | None] = {}
        for vehicle_type in sorted(types):
            first_by_type[vehicle_type] = next(
                (
                    y.year
                    for y in years
                    if y.requirement.required_by_type.get(vehicle_type, 0)
                    > y.requirement.current_by_type.get(vehicle_type, 0)
                ),
                None,
            )
        return ScenarioProjection(scenario.name, years, first_total, first_by_type)
