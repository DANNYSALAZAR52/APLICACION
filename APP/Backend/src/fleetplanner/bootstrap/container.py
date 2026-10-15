"""Composición de dependencias de la demo (DEMO-ONLY: adaptadores en memoria y datos sintéticos)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fleetplanner.adapters.outbound.clock import BOGOTA_TZ, SimulatedClock, SystemClock
from fleetplanner.adapters.outbound.demo_data import (
    DemoCapacityInputsReader,
    DemoRoutingInputsReader,
)
from fleetplanner.adapters.outbound.gps import SimulatedGps
from fleetplanner.adapters.outbound.persistence_memory import (
    InMemoryCapacityResultRepository,
    InMemoryRoutingRepository,
)
from fleetplanner.adapters.outbound.solver import OrToolsFleetMixSolver, OrToolsRoutingSolver
from fleetplanner.adapters.outbound.traffic import (
    SimulatedTrafficProvider,
    SpeedProfileTimeEstimator,
)
from fleetplanner.application.ports.outbound.capacity import (
    CapacityInputsReader,
    FleetMixSolverPort,
    MlForecastSource,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.routing import RoutingInputsReader, RoutingSolverPort
from fleetplanner.application.use_cases.build_capacity_dashboard import BuildCapacityDashboard
from fleetplanner.application.use_cases.optimize_fleet_mix import OptimizeFleetMix
from fleetplanner.application.use_cases.project_five_years import ProjectFiveYears
from fleetplanner.application.use_cases.routing.approve_reroute import ApproveReroute
from fleetplanner.application.use_cases.routing.build_morning_plan import BuildMorningPlan
from fleetplanner.application.use_cases.routing.core import RoutingCore
from fleetplanner.application.use_cases.routing.driver import DriverService
from fleetplanner.application.use_cases.routing.gps_support import FleetTruth, GpsMonitor
from fleetplanner.application.use_cases.routing.handle_event import HandleEvent
from fleetplanner.application.use_cases.routing.indicators import (
    IndicatorsService,
    ScenarioRunner,
)
from fleetplanner.application.use_cases.routing.rerouting import ReroutePlanner
from fleetplanner.application.use_cases.routing.snapshot import GetOperationsSnapshot
from fleetplanner.application.use_cases.routing.track_fleet import TrackFleet
from fleetplanner.application.use_cases.routing.workspace import (
    DAY_START,
    OperatingDay,
    RoutingWorkspace,
)
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
    ml: MlForecastSource | None = None,
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
        ml=ml,
    )
    return CapacityContainer(results, dashboard)


@dataclass(frozen=True)
class RoutingContainer:
    workspace: RoutingWorkspace
    repo: InMemoryRoutingRepository
    clock: SimulatedClock
    provider: SimulatedTrafficProvider


def default_sim_start() -> datetime:
    """Hoy a las 05:00 en Bogotá: cuando se arma el plan de la mañana."""
    today = SystemClock().now().date()
    return datetime.combine(today, DAY_START, tzinfo=BOGOTA_TZ)


def build_routing_container(
    reader: RoutingInputsReader | None = None,
    solver: RoutingSolverPort | None = None,
    clock: SimulatedClock | None = None,
    provider: SimulatedTrafficProvider | None = None,
) -> RoutingContainer:
    """Ensambla el ruteo de UNA empresa con su propio reloj, proveedor y estado del día."""
    reader = reader or DemoRoutingInputsReader()
    solver = solver or OrToolsRoutingSolver()
    clock = clock or SimulatedClock(default_sim_start())
    provider = provider or SimulatedTrafficProvider()
    repo = InMemoryRoutingRepository()
    # Los escenarios del tablero corren en un espacio de trabajo aparte con los mismos datos.
    scenarios = ScenarioRunner(lambda: build_routing_container(reader, solver).workspace)
    core = RoutingCore(reader, repo, provider, SpeedProfileTimeEstimator(), solver, clock)
    gps = SimulatedGps(FleetTruth(core).sample, clock, [v.id for v in core.dataset.vehicles])
    core.attach_gps(gps, gps)
    monitor = GpsMonitor(core)
    planner = ReroutePlanner(core)
    build = BuildMorningPlan(core)
    workspace = RoutingWorkspace(
        core=core,
        build_plan=build,
        handle_event=HandleEvent(core, planner, clock),
        approve=ApproveReroute(core, planner, clock),
        track=TrackFleet(core, planner, clock, monitor),
        snapshot=GetOperationsSnapshot(core, clock, provider, monitor),
        day=OperatingDay(core, build, clock, provider),
        planner=planner,
        driver=DriverService(core, clock),
        indicators=IndicatorsService(scenarios),
    )
    return RoutingContainer(workspace, repo, clock, provider)
