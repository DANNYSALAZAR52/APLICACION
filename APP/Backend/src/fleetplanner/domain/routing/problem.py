"""Definición de un problema de ruteo (varios vehículos, entregas con ventana y capacidad)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from fleetplanner.domain.routing.evaluation import (
    RouteEvaluation,
    StopKind,
    StopSpec,
    TravelFn,
    evaluate_route,
)
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.models import Customer, Order, RoutingParams, RoutingVehicle


@dataclass(frozen=True)
class OrderNode:
    """Pedido ya unido a su cliente y con el servicio calculado."""

    order: Order
    customer: Customer
    service_min: float

    @property
    def id(self) -> str:
        return self.order.id

    @property
    def kg(self) -> float:
        return self.order.kg

    def to_spec(self) -> StopSpec:
        return StopSpec(
            key=self.order.id,
            kind=StopKind.DELIVERY,
            point=self.customer.point,
            label=self.customer.name,
            service_min=self.service_min,
            load_delta_kg=-self.order.kg,
            window=self.order.window,
            order_id=self.order.id,
            customer_code=self.customer.code,
            priority=self.order.priority,
        )


def make_node(order: Order, customer: Customer, params: RoutingParams) -> OrderNode:
    return OrderNode(order, customer, params.service_minutes_for(customer, order.kg))


@dataclass(frozen=True)
class VehicleSlot:
    """Vehículo disponible para el problema, con su punto y hora de arranque."""

    vehicle: RoutingVehicle
    capacity_kg: float
    anchor_point: GeoPoint
    anchor_time_min: float


@dataclass(frozen=True)
class RoutingProblem:
    depot_point: GeoPoint
    slots: tuple[VehicleSlot, ...]
    nodes: tuple[OrderNode, ...]
    params: RoutingParams
    travel: TravelFn

    def node(self, order_id: str) -> OrderNode:
        return self._index()[order_id]

    def _index(self) -> dict[str, OrderNode]:
        return {n.id: n for n in self.nodes}

    def evaluate(self, slot: VehicleSlot, order_ids: Sequence[str]) -> RouteEvaluation:
        index = self._index()
        specs = [index[i].to_spec() for i in order_ids]
        load = sum(index[i].kg for i in order_ids)
        return evaluate_route(
            slot.anchor_point,
            slot.anchor_time_min,
            load,
            specs,
            self.depot_point,
            slot.capacity_kg,
            self.params,
            self.travel,
        )


@dataclass(frozen=True)
class RoutingSolution:
    routes: dict[str, tuple[str, ...]]  # vehicle_id -> order_ids en secuencia
    unassigned: dict[str, str] = field(default_factory=dict)  # order_id -> motivo legible
    engine: str = ""
    elapsed_s: float = 0.0
    note: str = ""

    @property
    def assigned_count(self) -> int:
        return sum(len(ids) for ids in self.routes.values())


def evaluate_solution(
    problem: RoutingProblem, solution: RoutingSolution
) -> dict[str, RouteEvaluation]:
    """Evalúa con el evaluador de dominio, sin importar qué motor generó la solución."""
    by_id = {s.vehicle.id: s for s in problem.slots}
    return {v: problem.evaluate(by_id[v], ids) for v, ids in solution.routes.items()}


def solution_score(problem: RoutingProblem, solution: RoutingSolution) -> float:
    return sum(e.score for e in evaluate_solution(problem, solution).values())


def explain_unassigned(problem: RoutingProblem, order_id: str) -> str:
    """Motivo legible de por qué un pedido no se pudo asignar."""
    node = problem.node(order_id)
    if not problem.slots:
        return "No hay vehículos disponibles."
    biggest = max(s.capacity_kg for s in problem.slots)
    if node.kg > biggest:
        return (
            f"El pedido pesa {node.kg:g} kg y supera la capacidad operativa del mayor vehículo "
            f"disponible ({biggest:g} kg)."
        )
    earliest = min(
        s.anchor_time_min
        + problem.travel(s.anchor_point, node.customer.point, s.anchor_time_min).minutes
        for s in problem.slots
    )
    if earliest > node.order.window.end_min:
        return (
            f"Ningún vehículo llega antes del fin de la ventana ({node.order.window.label()}); "
            "amplíe la ventana o use un vehículo de reserva."
        )
    return "La flota disponible no tiene capacidad restante para este pedido en el día."
