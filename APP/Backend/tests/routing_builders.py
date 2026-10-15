"""Constructores de datos de prueba para ruteo (sin adaptadores ni solver)."""

from __future__ import annotations

from fleetplanner.domain.routing.evaluation import (
    StopKind,
    StopSpec,
    TravelFn,
    TravelLeg,
)
from fleetplanner.domain.routing.geo import GeoPoint, haversine_km
from fleetplanner.domain.routing.models import (
    Customer,
    Depot,
    Order,
    RoutingParams,
    RoutingVehicle,
)
from fleetplanner.domain.routing.problem import (
    OrderNode,
    RoutingProblem,
    VehicleSlot,
    make_node,
)
from fleetplanner.domain.routing.time_window import TimeWindow

DEPOT_POINT = GeoPoint(4.7165, -74.2125)  # Funza
PARAMS = RoutingParams()


def constant_travel(minutes: float = 10.0, km: float = 5.0) -> TravelFn:
    """Todo tramo cuesta lo mismo, salvo que origen y destino coincidan (0)."""

    def travel(a: GeoPoint, b: GeoPoint, depart_min: float) -> TravelLeg:
        if a == b:
            return TravelLeg(0.0, 0.0)
        return TravelLeg(minutes, km)

    return travel


def haversine_travel(speed_kmh: float = 30.0, road_factor: float = 1.35) -> TravelFn:
    """Tiempo proporcional a la distancia (para probar geometría real)."""

    def travel(a: GeoPoint, b: GeoPoint, depart_min: float) -> TravelLeg:
        km = haversine_km(a, b) * road_factor
        return TravelLeg(km / speed_kmh * 60.0, km)

    return travel


def point(i: int) -> GeoPoint:
    """Puntos distintos y dentro de Bogotá, separados ~1,1 km."""
    return GeoPoint(4.60 + 0.01 * (i % 10), -74.10 - 0.01 * (i // 10))


def spec(
    key: str,
    start: float,
    end: float,
    kg: float = 100.0,
    service: float = 5.0,
    where: GeoPoint | None = None,
) -> StopSpec:
    return StopSpec(
        key=key,
        kind=StopKind.DELIVERY,
        point=where or point(sum(map(ord, key)) % 90),  # determinista (hash() varía por proceso)
        label=f"Cliente {key}",
        service_min=service,
        load_delta_kg=-kg,
        window=TimeWindow(start, end),
        order_id=key,
        customer_code=f"C-{key}",
    )


def customer(code: str, i: int, start: float = 420.0, end: float = 840.0) -> Customer:
    return Customer.create(
        code=code,
        name=f"Cliente {code}",
        address=f"Calle {i}",
        lat=point(i).lat,
        lon=point(i).lon,
        window_start_min=start,
        window_end_min=end,
    )


def node(
    order_id: str, i: int, kg: float = 200.0, start: float = 420.0, end: float = 840.0
) -> OrderNode:
    cust = customer(f"C{order_id}", i, start, end)
    order = Order(order_id, cust.code, kg, 1.0, TimeWindow(start, end))
    return make_node(order, cust, PARAMS)


def vehicle(vid: str, capacity_kg: float = 4500.0) -> RoutingVehicle:
    return RoutingVehicle(vid, f"PL-{vid}", "turbo", capacity_kg)


def slot(vid: str, capacity_kg: float = 4500.0, start_min: float = 360.0) -> VehicleSlot:
    v = vehicle(vid, capacity_kg)
    return VehicleSlot(v, PARAMS.operational_capacity_kg(v), DEPOT_POINT, start_min)


def problem(
    nodes: list[OrderNode], slots: list[VehicleSlot], travel: TravelFn | None = None
) -> RoutingProblem:
    return RoutingProblem(
        DEPOT_POINT, tuple(slots), tuple(nodes), PARAMS, travel or haversine_travel()
    )


DEPOT = Depot("CEDI", "CEDI Funza", DEPOT_POINT)
