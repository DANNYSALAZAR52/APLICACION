"""Núcleo compartido por los casos de uso de ruteo de UN tenant.

Agrupa lo que todos necesitan: los datos de la empresa, el estado del día, el reloj y el
resolutor de tiempos de viaje (proveedor con respaldo por perfil de velocidades).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.routing import (
    FallbackTravelTimePort,
    GpsPort,
    GpsSimulationControl,
    RoutingDataset,
    RoutingInputsReader,
    RoutingRepositoryPort,
    RoutingSolverPort,
    TrafficProviderUnavailable,
    TrafficTimePort,
)
from fleetplanner.domain.routing.evaluation import StopKind, StopSpec, TravelLeg
from fleetplanner.domain.routing.events import Closure
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.models import Customer, Order, RoutingParams, RoutingVehicle
from fleetplanner.domain.routing.plan import RouteView, VehicleRoute, view_route
from fleetplanner.domain.routing.problem import OrderNode, make_node
from fleetplanner.domain.shared.errors import NotFoundError

DEGRADED_NOTICE = "Tiempos estimados sin tráfico"


class TravelResolver:
    """Callable de tiempos de viaje. Si el proveedor falla usa el perfil de velocidades.

    Al primer fallo pasa al respaldo para el resto del cálculo y ``degraded`` queda en verdadero:
    la interfaz debe avisar "Tiempos estimados sin tráfico" y nunca afirmar tráfico en vivo.
    """

    def __init__(
        self,
        primary: TrafficTimePort,
        fallback: FallbackTravelTimePort,
        closures: Sequence[Closure],
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._closures = tuple(closures)
        self.degraded = False

    def __call__(self, origin: GeoPoint, destination: GeoPoint, depart_min: float) -> TravelLeg:
        if origin == destination:
            return TravelLeg(0.0, 0.0)
        if not self.degraded:
            try:
                return self._primary.estimate(origin, destination, depart_min, self._closures)
            except TrafficProviderUnavailable:
                self.degraded = True
        return self._fallback.estimate(origin, destination, depart_min, self._closures)


class RoutingCore:
    def __init__(
        self,
        reader: RoutingInputsReader,
        repo: RoutingRepositoryPort,
        traffic: TrafficTimePort,
        fallback: FallbackTravelTimePort,
        solver: RoutingSolverPort,
        clock: ClockPort,
    ) -> None:
        self._reader = reader
        self.dataset: RoutingDataset = reader.read()
        self.repo = repo
        self.traffic = traffic
        self.fallback = fallback
        self.solver = solver
        self.clock = clock
        self._index()
        self.gps: GpsPort | None = None
        self.gps_control: GpsSimulationControl | None = None

    def _index(self) -> None:
        self._vehicles = {v.id: v for v in self.dataset.vehicles}
        self._customers = {c.code: c for c in self.dataset.customers}

    def reload(self) -> None:
        """Relee los maestros: los cambios del administrador aplican al iniciar un día nuevo."""
        self.dataset = self._reader.read()
        self._index()

    def attach_gps(self, gps: GpsPort, control: GpsSimulationControl | None = None) -> None:
        """Conecta el GPS (se crea después del núcleo porque lee posiciones del plan)."""
        self.gps = gps
        self.gps_control = control

    # ------------------------------------------------------------------ datos
    @property
    def params(self) -> RoutingParams:
        return self.dataset.params

    @property
    def depot_point(self) -> GeoPoint:
        return self.dataset.depot.point

    def vehicle(self, vehicle_id: str) -> RoutingVehicle:
        found = self._vehicles.get(vehicle_id)
        if found is None:
            raise NotFoundError("El vehículo no existe.")
        return found

    def customer(self, code: str) -> Customer:
        found = self._customers.get(code)
        if found is None:
            raise NotFoundError(f"El cliente '{code}' no existe.")
        return found

    def node_for(self, order: Order) -> OrderNode:
        return make_node(order, self.customer(order.customer_code), self.params)

    # ------------------------------------------------------------------ tiempo
    def now_min(self) -> float:
        now = self.clock.now()
        return now.hour * 60 + now.minute + now.second / 60 + now.microsecond / 6e7

    def resolver(
        self, extra_closures: Sequence[Closure] = (), exclude_ids: Sequence[str] = ()
    ) -> TravelResolver:
        """Resolutor con los cierres conocidos (menos ``exclude_ids``, para medir su impacto)."""
        known = [c for c in self.repo.closures() if c.id not in exclude_ids]
        return TravelResolver(self.traffic, self.fallback, [*known, *extra_closures])

    # ------------------------------------------------------------------ vistas
    def refresh_route(self, route: VehicleRoute) -> VehicleRoute:
        """Aplica a las paradas pendientes las ventanas vigentes (cambios de ventana)."""
        orders = self.repo.orders()
        pending = tuple(self._with_current_window(s, orders) for s in route.pending)
        return replace(route, pending=pending) if pending != route.pending else route

    @staticmethod
    def _with_current_window(spec: StopSpec, orders: dict[str, Order]) -> StopSpec:
        if spec.kind is not StopKind.DELIVERY or spec.order_id is None:
            return spec
        order = orders.get(spec.order_id)
        if order is None or order.window == spec.window:
            return spec
        return replace(spec, window=order.window)

    def view(self, route: VehicleRoute, resolver: TravelResolver, now_min: float) -> RouteView:
        return view_route(
            self.refresh_route(route), now_min, self.depot_point, self.params, resolver
        )
