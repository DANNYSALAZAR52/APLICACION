"""DEMO-ONLY: estado del día operativo de UN tenant en memoria (planes, eventos, propuestas)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import date

from fleetplanner.domain.routing.delivery import DeliveryConfirmation, DriverReport
from fleetplanner.domain.routing.events import Closure, OperationalEvent, RerouteProposal
from fleetplanner.domain.routing.models import Order
from fleetplanner.domain.routing.plan import RoutePlan
from fleetplanner.domain.shared.errors import ConflictError, NotFoundError


class InMemoryRoutingRepository:
    """Cada tenant recibe su propia instancia: no hay forma de leer el estado de otra empresa.

    Las versiones del plan son append-only: no se borran ni sobrescriben.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._day: date | None = None
        self._clear()

    def _clear(self) -> None:
        self._plans: list[RoutePlan] = []
        self._orders: dict[str, Order] = {}
        self._events: list[OperationalEvent] = []
        self._closures: list[Closure] = []
        self._proposals: dict[str, RerouteProposal] = {}
        self._proposal_order: list[str] = []
        self._counters: dict[str, int] = {}
        self._confirmations: dict[str, DeliveryConfirmation] = {}
        self._reports: list[DriverReport] = []

    @property
    def day(self) -> date | None:
        with self._lock:
            return self._day

    def reset(self, day: date, orders: Sequence[Order]) -> None:
        with self._lock:
            self._clear()
            self._day = day
            self._orders = {o.id: o for o in orders}

    # ------------------------------------------------------------------ planes
    def plans(self) -> list[RoutePlan]:
        with self._lock:
            return list(self._plans)

    def active_plan(self) -> RoutePlan | None:
        with self._lock:
            return self._plans[-1] if self._plans else None

    def add_plan(self, plan: RoutePlan) -> None:
        with self._lock:
            if plan.version != len(self._plans) + 1:
                raise ConflictError(
                    f"La versión {plan.version} no es la siguiente (se esperaba "
                    f"{len(self._plans) + 1}); las versiones no se sobrescriben."
                )
            self._plans.append(plan)

    # ----------------------------------------------------------------- pedidos
    def orders(self) -> dict[str, Order]:
        with self._lock:
            return dict(self._orders)

    def save_order(self, order: Order) -> None:
        with self._lock:
            self._orders[order.id] = order

    # ----------------------------------------------------------------- eventos
    def events(self) -> list[OperationalEvent]:
        with self._lock:
            return list(self._events)

    def add_event(self, event: OperationalEvent) -> None:
        with self._lock:
            self._events.append(event)

    def update_event(self, event: OperationalEvent) -> None:
        with self._lock:
            for i, existing in enumerate(self._events):
                if existing.id == event.id:
                    self._events[i] = event
                    return
        raise NotFoundError("El evento no existe.")

    def closures(self) -> list[Closure]:
        with self._lock:
            return list(self._closures)

    def add_closure(self, closure: Closure) -> None:
        with self._lock:
            self._closures.append(closure)

    # ------------------------------------------------------------- propuestas
    def proposals(self) -> list[RerouteProposal]:
        with self._lock:
            return [self._proposals[i] for i in self._proposal_order]

    def get_proposal(self, proposal_id: str) -> RerouteProposal | None:
        with self._lock:
            return self._proposals.get(proposal_id)

    def save_proposal(self, proposal: RerouteProposal) -> None:
        with self._lock:
            if proposal.id not in self._proposals:
                self._proposal_order.append(proposal.id)
            self._proposals[proposal.id] = proposal

    def next_id(self, prefix: str) -> str:
        with self._lock:
            n = self._counters.get(prefix, 0) + 1
            self._counters[prefix] = n
            return f"{prefix}-{n:03d}"

    # ------------------------------------------------- confirmaciones y novedades
    def confirmations(self) -> dict[str, DeliveryConfirmation]:
        with self._lock:
            return dict(self._confirmations)

    def confirm(self, confirmation: DeliveryConfirmation) -> bool:
        with self._lock:
            if confirmation.order_id in self._confirmations:
                return False  # la primera confirmación gana
            self._confirmations[confirmation.order_id] = confirmation
            return True

    def reports(self) -> list[DriverReport]:
        with self._lock:
            return list(self._reports)

    def add_report(self, report: DriverReport) -> None:
        with self._lock:
            self._reports.append(report)
