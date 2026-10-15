"""HandleEvent: registra un evento operativo y genera la propuesta de re-ruteo."""

from __future__ import annotations

from fleetplanner.application.dto.routing import (
    BreakdownCommand,
    ChangeWindowCommand,
    CloseRoadCommand,
    EventCommand,
    HandleEventResult,
    UrgentOrderCommand,
)
from fleetplanner.application.ports.outbound.clock import SimulationClockPort
from fleetplanner.application.use_cases.routing.core import RoutingCore
from fleetplanner.application.use_cases.routing.proposals import store_proposal
from fleetplanner.application.use_cases.routing.rerouting import ReroutePlanner
from fleetplanner.domain.routing.events import (
    BreakdownData,
    Closure,
    ClosureEventData,
    EventPayload,
    EventType,
    OperationalEvent,
    UrgentOrderData,
    WindowChangeData,
)
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.models import Order, VehicleKind
from fleetplanner.domain.routing.plan import RouteStatus
from fleetplanner.domain.routing.time_window import TimeWindow, format_clock
from fleetplanner.domain.shared.errors import ConflictError, InvalidValueError, NotFoundError


class HandleEvent:
    """Valida y registra el evento, y devuelve la propuesta. No cambia el plan vigente."""

    def __init__(
        self,
        core: RoutingCore,
        planner: ReroutePlanner,
        sim_clock: SimulationClockPort | None = None,
    ) -> None:
        self._core = core
        self._planner = planner
        self._sim_clock = sim_clock

    def execute(self, actor: str, command: EventCommand) -> HandleEventResult:
        core = self._core
        if core.repo.active_plan() is None:
            raise ConflictError("Aún no hay plan del día; cree el plan de la mañana primero.")
        event_id = core.repo.next_id("EV")
        minute = core.now_min()
        event_type, payload, summary = self._register(command, event_id, minute)
        event = OperationalEvent(
            id=event_id,
            type=event_type,
            occurred_at=core.clock.now(),
            minute=minute,
            created_by=actor,
            summary=summary,
            payload=payload,
        )
        # Se propone antes de guardar el evento: si el cálculo falla no queda un evento huérfano.
        draft = self._planner.propose(event, actor)
        core.repo.add_event(event)
        stored_event, proposal = store_proposal(core, event, draft, self._sim_clock)
        return HandleEventResult(stored_event, proposal)

    # ------------------------------------------------------------------ registro
    def _register(
        self, command: EventCommand, event_id: str, minute: float
    ) -> tuple[EventType, EventPayload, str]:
        if isinstance(command, CloseRoadCommand):
            return self._closure(command, event_id, minute)
        if isinstance(command, UrgentOrderCommand):
            return self._urgent(command, minute)
        if isinstance(command, ChangeWindowCommand):
            return self._window(command)
        if isinstance(command, BreakdownCommand):
            return self._breakdown(command)
        raise InvalidValueError("Tipo de evento no soportado.")  # pragma: no cover

    def _closure(
        self, cmd: CloseRoadCommand, event_id: str, minute: float
    ) -> tuple[EventType, EventPayload, str]:
        if not cmd.label.strip():
            raise InvalidValueError("Indique el nombre del cierre vial (por ejemplo, la calle).")
        closure = Closure(
            id=event_id,
            label=cmd.label.strip(),
            center=GeoPoint(cmd.lat, cmd.lon),
            radius_km=cmd.radius_km,
            factor=cmd.factor,
            start_min=minute,
            end_min=minute + cmd.duration_min,
        )
        if cmd.duration_min <= 0:
            raise InvalidValueError("La duración del cierre debe ser mayor que cero.")
        self._core.repo.add_closure(closure)
        data = ClosureEventData(
            closure.label, closure.center, cmd.radius_km, cmd.factor, cmd.duration_min
        )
        return (
            EventType.ROAD_CLOSURE,
            data,
            f"Cierre vial «{closure.label}» desde las {format_clock(minute)} "
            f"(×{cmd.factor:g}, radio {cmd.radius_km:g} km, {cmd.duration_min:g} min)",
        )

    def _urgent(
        self, cmd: UrgentOrderCommand, minute: float
    ) -> tuple[EventType, EventPayload, str]:
        core = self._core
        customer = core.customer(cmd.customer_code)  # NotFoundError si no existe
        window = TimeWindow(cmd.window_start_min, cmd.window_end_min)
        if window.end_min <= minute:
            raise InvalidValueError(
                f"La ventana {window.label()} ya terminó (son las {format_clock(minute)}); "
                "indique una ventana que cierre más tarde."
            )
        order_id = core.repo.next_id("URG")
        order = Order(order_id, customer.code, cmd.kg, cmd.m3, window, priority=1, urgent=True)
        core.repo.save_order(order)
        data = UrgentOrderData(order_id, customer.code, cmd.kg, cmd.m3, window)
        return (
            EventType.URGENT_ORDER,
            data,
            f"Pedido urgente {order_id}: {cmd.kg:g} kg para {customer.name}, "
            f"ventana {window.label()}",
        )

    def _window(self, cmd: ChangeWindowCommand) -> tuple[EventType, EventPayload, str]:
        core = self._core
        orders = core.repo.orders()
        order = orders.get(cmd.order_id)
        if order is None:
            raise NotFoundError(f"El pedido '{cmd.order_id}' no existe.")
        window = TimeWindow(cmd.window_start_min, cmd.window_end_min)
        ctx = self._planner.context()
        still_pending = any(
            s.order_id == cmd.order_id for fr in ctx.frozen.values() for s in fr.pending
        )
        if not still_pending and not self._is_unassigned(cmd.order_id):
            raise ConflictError(
                "El pedido ya fue entregado o está en servicio; la ventana ya no se puede cambiar."
            )
        old = order.window.label()
        core.repo.save_order(
            Order(
                order.id,
                order.customer_code,
                order.kg,
                order.m3,
                window,
                order.priority,
                order.urgent,
            )
        )
        data = WindowChangeData(cmd.order_id, window)
        return (
            EventType.WINDOW_CHANGE,
            data,
            f"Cambio de ventana del pedido {cmd.order_id}: {old} → {window.label()}",
        )

    def _is_unassigned(self, order_id: str) -> bool:
        plan = self._core.repo.active_plan()
        return plan is not None and any(u.order_id == order_id for u in plan.unassigned)

    def _breakdown(self, cmd: BreakdownCommand) -> tuple[EventType, EventPayload, str]:
        core = self._core
        vehicle = core.vehicle(cmd.vehicle_id)
        plan = core.repo.active_plan()
        route = plan.route_of(vehicle.id) if plan else None
        if route is None or route.status is not RouteStatus.ACTIVE:
            raise ConflictError(
                f"El vehículo {vehicle.plate} no está en operación; no se puede registrar avería."
            )
        if vehicle.kind is VehicleKind.OWN or route.pending or route.frozen:
            return (
                EventType.BREAKDOWN,
                BreakdownData(vehicle.id),
                f"Avería del vehículo {vehicle.plate}",
            )
        raise ConflictError(f"El vehículo {vehicle.plate} no tiene ruta en curso.")
