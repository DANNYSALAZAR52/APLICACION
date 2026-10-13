"""DTO del módulo de capacidad."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from fleetplanner.domain.capacity.design_demand import DesignDemand
from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacity
from fleetplanner.domain.capacity.fleet_mix import FleetMixSolution
from fleetplanner.domain.capacity.fleet_requirement import FleetRequirement
from fleetplanner.domain.capacity.kpis import CapacityKpis
from fleetplanner.domain.capacity.lean import LeanResult, LeanTargets
from fleetplanner.domain.capacity.models import (
    CompatibilityMatrix,
    Corridor,
    DemandSeries,
    OeeFactors,
    VehicleType,
)
from fleetplanner.domain.capacity.monte_carlo import MonteCarloConfig, MonteCarloResult
from fleetplanner.domain.capacity.own_vs_third import OwnVsThirdResult
from fleetplanner.domain.capacity.projection import GrowthScenario, ScenarioProjection
from fleetplanner.domain.shared.percentage import Percentage


@dataclass(frozen=True)
class CapacityParameters:
    """Parámetros vigentes de la corrida (en producción provienen de la tabla `parameter`)."""

    design_percentile: Percentage
    reserve: Percentage
    days_per_month: int
    window_days: int
    oee: OeeFactors
    lean_targets: LeanTargets
    monte_carlo: MonteCarloConfig
    solver_time_limit_s: float = 30.0
    base_year: int | None = None


@dataclass(frozen=True)
class CapacityInputs:
    """Todo lo que necesita una corrida de capacidad, leído por un único puerto."""

    vehicle_types: Mapping[str, VehicleType]
    corridors: list[Corridor]
    compatibility: CompatibilityMatrix
    demand: Mapping[str, DemandSeries]
    current_fleet: Mapping[str, int]
    parameters: CapacityParameters
    scenarios: list[GrowthScenario]


@dataclass(frozen=True)
class PreparedCapacity:
    """Corredores con datos suficientes y sus cálculos base (P1 y P2)."""

    corridors: list[Corridor]
    design: Mapping[str, DesignDemand]
    capacities: Mapping[str, EffectiveCapacity]
    excluded: Mapping[str, str]
    warnings: list[str]

    @property
    def design_t(self) -> dict[str, float]:
        return {code: d.design_t for code, d in self.design.items()}

    @property
    def mean_t(self) -> dict[str, float]:
        return {code: d.mean_t for code, d in self.design.items()}


@dataclass(frozen=True)
class BalanceReport:
    requirement: FleetRequirement
    design: Mapping[str, DesignDemand]
    capacities: Mapping[str, EffectiveCapacity]
    kpis: CapacityKpis


@dataclass(frozen=True)
class CapacityDashboard:
    """Vista consolidada (P9): métodos lado a lado, KPI, hallazgos y advertencias."""

    run_at: datetime
    algorithm_version: str
    base_year: int
    balance: BalanceReport
    lean: LeanResult
    monte_carlo: MonteCarloResult
    mix: FleetMixSolution
    own_vs_third: OwnVsThirdResult
    projections: list[ScenarioProjection]
    findings: list[str]
    parameters: CapacityParameters
    corridor_names: Mapping[str, str]
    warnings: list[str] = field(default_factory=list)
    ml_forecast_available: bool = False
