"""Composición de dependencias de la demo (DEMO-ONLY: adaptadores en memoria y datos sintéticos)."""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.adapters.outbound.clock import SystemClock
from fleetplanner.adapters.outbound.demo_data import DemoCapacityInputsReader
from fleetplanner.adapters.outbound.persistence_memory import InMemoryCapacityResultRepository
from fleetplanner.adapters.outbound.solver import OrToolsFleetMixSolver
from fleetplanner.application.ports.outbound.capacity import (
    CapacityInputsReader,
    FleetMixSolverPort,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.use_cases.build_capacity_dashboard import BuildCapacityDashboard
from fleetplanner.application.use_cases.optimize_fleet_mix import OptimizeFleetMix
from fleetplanner.application.use_cases.project_five_years import ProjectFiveYears
from fleetplanner.application.use_cases.run_capacity_analysis import RunCapacityAnalysis
from fleetplanner.application.use_cases.simulate_monte_carlo import SimulateMonteCarlo


@dataclass(frozen=True)
class CapacityContainer:
    results: InMemoryCapacityResultRepository
    dashboard: BuildCapacityDashboard


def build_capacity_container(
    reader: CapacityInputsReader | None = None,
    solver: FleetMixSolverPort | None = None,
    clock: ClockPort | None = None,
) -> CapacityContainer:
    """Ensambla los casos de uso de capacidad. Los argumentos permiten sustituir adaptadores."""
    reader = reader or DemoCapacityInputsReader()
    solver = solver or OrToolsFleetMixSolver()
    clock = clock or SystemClock()
    results = InMemoryCapacityResultRepository()
    dashboard = BuildCapacityDashboard(
        reader=reader,
        analysis=RunCapacityAnalysis(reader, results, clock),
        projection=ProjectFiveYears(reader, results, clock),
        monte_carlo=SimulateMonteCarlo(reader, results, clock),
        mix=OptimizeFleetMix(reader, solver, results, clock),
        clock=clock,
    )
    return CapacityContainer(results, dashboard)
