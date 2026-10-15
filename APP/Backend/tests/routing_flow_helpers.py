"""Armado de espacios de ruteo para pruebas (reloj acelerado inyectado, solver rápido)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fleetplanner.adapters.outbound.clock import BOGOTA_TZ, SimulatedClock
from fleetplanner.adapters.outbound.demo_data.routing_dataset import (
    DemoRoutingInputsReader,
    RoutingProfile,
)
from fleetplanner.application.ports.outbound.routing import RoutingDataset
from fleetplanner.bootstrap.container import RoutingContainer, build_routing_container
from fleetplanner.domain.routing.evaluation import evaluate_route
from fleetplanner.domain.routing.heuristic import solve_with_heuristic
from fleetplanner.domain.routing.models import (
    Customer,
    Order,
    RoutingParams,
    RoutingVehicle,
    VehicleKind,
)
from fleetplanner.domain.routing.plan import RouteAnchor, RoutePlan, RouteStatus, VehicleRoute
from fleetplanner.domain.routing.problem import RoutingProblem, RoutingSolution
from fleetplanner.domain.routing.time_window import TimeWindow
from routing_builders import DEPOT

DAY = datetime(2026, 10, 14, 5, 0, tzinfo=BOGOTA_TZ)


class HeuristicSolver:
    """Doble de prueba de `RoutingSolverPort`: usa la heurística de dominio (rápida)."""

    def solve(self, problem: RoutingProblem, time_limit_s: float) -> RoutingSolution:
        return solve_with_heuristic(problem)


class StaticReader:
    def __init__(self, dataset: RoutingDataset) -> None:
        self._dataset = dataset

    def read(self) -> RoutingDataset:
        return self._dataset


@dataclass
class Flow:
    container: RoutingContainer

    @property
    def ws(self):  # type: ignore[no-untyped-def]
        return self.container.workspace

    def at(self, hour: int, minute: int = 0) -> None:
        """Lleva el reloj simulado a una hora del día operativo."""
        self.container.clock.reset(DAY.replace(hour=hour, minute=minute))


def seeded(customers: int = 10, vehicles: int = 2, seed: int = 7) -> Flow:
    reader = DemoRoutingInputsReader(RoutingProfile(seed, customers, vehicles))
    clock = SimulatedClock(DAY)
    return Flow(build_routing_container(reader, HeuristicSolver(), clock))


def custom(
    customers: list[Customer],
    kgs: list[float],
    vehicles: int = 1,
    reserve_capacity: float = 4500.0,
    third_capacity: float | None = 8000.0,
) -> Flow:
    orders = [
        Order(f"P-{i + 1:03d}", c.code, kg, 1.0, c.window)
        for i, (c, kg) in enumerate(zip(customers, kgs, strict=True))
    ]
    fleet = [
        RoutingVehicle(f"V-{n:02d}", f"T-{n:02d}", "turbo", 4500.0, VehicleKind.OWN)
        for n in range(1, vehicles + 1)
    ]
    fleet.append(RoutingVehicle("V-RES", "T-RES", "turbo", reserve_capacity, VehicleKind.RESERVE))
    if third_capacity:
        fleet.append(
            RoutingVehicle("V-TER", "TER-1", "sencillo", third_capacity, VehicleKind.THIRD_PARTY)
        )
    dataset = RoutingDataset(DEPOT, tuple(customers), tuple(orders), tuple(fleet), RoutingParams())
    clock = SimulatedClock(DAY)
    return Flow(build_routing_container(StaticReader(dataset), HeuristicSolver(), clock))


def cust(code: str, lat: float, lon: float, start: float, end: float) -> Customer:
    return Customer.create(code, f"Cliente {code}", "x", lat, lon, start, end)


def window(start_hhmm: str, end_hhmm: str) -> TimeWindow:
    from fleetplanner.domain.routing.time_window import parse_clock

    return TimeWindow(parse_clock(start_hhmm), parse_clock(end_hhmm))


def force_plan(flow: Flow, sequences: dict[str, list[str]]) -> RoutePlan:
    """Guarda como versión 1 un plan con el orden exacto indicado (sin pasar por los motores).

    Sirve para probar el re-ruteo desde un punto de partida conocido: los vehículos que no
    aparecen en ``sequences`` quedan en espera (reserva o tercero).
    """
    core = flow.ws.core
    day = flow.container.clock.now().date()
    core.repo.reset(day, core.dataset.orders)
    params, depot = core.params, core.depot_point
    resolver = core.resolver()
    orders = core.repo.orders()
    routes: list[VehicleRoute] = []
    for vehicle in core.dataset.vehicles:
        capacity = params.operational_capacity_kg(vehicle)
        anchor = RouteAnchor(depot, params.departure_min, "CEDI")
        ids = sequences.get(vehicle.id)
        specs = tuple(core.node_for(orders[i]).to_spec() for i in ids or [])
        load = sum(-s.load_delta_kg for s in specs)
        evaluation = evaluate_route(
            depot, params.departure_min, load, specs, depot, capacity, params, resolver
        )
        routes.append(
            VehicleRoute(
                vehicle.id, vehicle.plate, vehicle.vehicle_type, capacity, anchor, load, (),
                specs, evaluation,
                status=RouteStatus.ACTIVE if ids is not None else RouteStatus.STANDBY,
            )
        )  # fmt: skip
    plan = RoutePlan(1, None, core.clock.now(), "prueba", "Plan forzado", tuple(routes))
    core.repo.add_plan(plan)
    return plan
