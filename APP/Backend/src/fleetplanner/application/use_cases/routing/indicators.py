"""Indicadores diarios y comparación plan estático vs. ruteo dinámico.

Los escenarios se ejecutan en un espacio de trabajo APARTE (reloj, repositorio y proveedor
propios) con los mismos datos de la empresa y el mismo guion de cuatro eventos, de modo que la
comparación usa los mismos pedidos y el mismo denominador. Son simulaciones reproducibles con
datos sintéticos (D-013): nunca se presentan como mediciones reales.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from fleetplanner.application.dto.routing import (
    BreakdownCommand,
    ChangeWindowCommand,
    CloseRoadCommand,
    EventCommand,
    KpiView,
    LiveIndicators,
    ScenarioView,
    UrgentOrderCommand,
)
from fleetplanner.application.use_cases.routing.workspace import RoutingWorkspace
from fleetplanner.domain.routing.evaluation import StopTiming
from fleetplanner.domain.routing.events import Closure, ProposalStatus
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.kpis import DailyKpis, compute_kpis
from fleetplanner.domain.routing.models import Order, VehicleKind
from fleetplanner.domain.routing.plan import RouteStatus
from fleetplanner.domain.routing.time_window import TimeWindow
from fleetplanner.domain.shared.errors import ConflictError, DomainError

SCENARIO_ACTOR = "escenarios (simulación)"
END_OF_DAY_MIN = 19 * 60
INCOMPLETE_RATE_EXAMPLE = 0.10

DEFINITIONS = (
    "Puntualidad = pedidos entregados dentro de su ventana / pedidos comprometidos del día.",
    "OTIF = pedidos entregados completos y a tiempo / pedidos comprometidos del día.",
    "El denominador es el mismo siempre: todos los pedidos del día, incluidos los urgentes y los "
    "que quedaron sin atender (cuentan como no cumplidos).",
    "Un pedido es puntual si la llegada ocurre antes o en el fin de su ventana.",
    "Los escenarios son simulaciones con datos sintéticos y el mismo guion de eventos; las "
    "entregas incompletas son un parámetro de ejemplo, no una medición.",
)


def kpi_view(k: DailyKpis) -> KpiView:
    return KpiView(
        committed_orders=k.committed_orders,
        delivered_orders=k.delivered_orders,
        on_time_orders=k.on_time_orders,
        otif_orders=k.otif_orders,
        late_orders=k.late_orders,
        unattended_orders=k.unattended_orders,
        incomplete_orders=k.incomplete_orders,
        total_delay_min=k.total_delay_min,
        punctuality=k.punctuality,
        otif=k.otif,
    )


def _timings_by_vehicle(ws: RoutingWorkspace, minute: float) -> dict[str, list[StopTiming]]:
    """Paradas del plan vigente por vehículo, con los horarios proyectados a ``minute``."""
    core = ws.core
    plan = core.repo.active_plan()
    if plan is None:
        raise ConflictError("Aún no hay plan del día.")
    resolver = core.resolver()
    return {r.vehicle_id: list(core.view(r, resolver, minute).timings) for r in plan.routes}


def _flat(by_vehicle: dict[str, list[StopTiming]]) -> list[StopTiming]:
    return [t for timings in by_vehicle.values() for t in timings]


def _reserve_activations(ws: RoutingWorkspace) -> int:
    plan = ws.core.repo.active_plan()
    if plan is None:
        return 0
    kinds = {v.id: v.kind for v in ws.core.dataset.vehicles}
    return sum(
        1
        for r in plan.routes
        if kinds[r.vehicle_id] is not VehicleKind.OWN and (r.pending or r.frozen)
    )


@dataclass
class _Targets:
    """Objetivos del guion, escogidos del plan de la mañana con reglas fijas y reproducibles."""

    window_order: str | None = None
    window_end: float = 0.0
    breakdown_vehicle: str | None = None
    urgent_customer: str | None = None
    applied: list[str] = field(default_factory=list)


class ScenarioRunner:
    """Corre el guion de cuatro eventos en un espacio de trabajo aislado."""

    CLOSURE_AT = 8 * 60 + 15
    WINDOW_AT = 9 * 60 + 30
    URGENT_AT = 10 * 60 + 30
    BREAKDOWN_AT = 11 * 60
    CLOSURE = (
        "Calle 80",
        4.7220,
        -74.1000,
        2.5,
        2.5,
        255.0,
    )  # nombre, lat, lon, radio, factor, min

    def __init__(self, factory: Callable[[], RoutingWorkspace]) -> None:
        self._factory = factory

    # ------------------------------------------------------------------ guion
    def _targets(self, ws: RoutingWorkspace) -> _Targets:
        """Reglas fijas sobre el plan de la mañana (versión 1)."""
        core = ws.core
        plan = core.repo.active_plan()
        if plan is None:
            raise ConflictError("Aún no hay plan del día.")
        resolver = core.resolver()
        views = {r.vehicle_id: core.view(r, resolver, 0.0) for r in plan.routes}

        def pending_at(vid: str, minute: float) -> list[StopTiming]:
            return [t for t in views[vid].timings if t.arrival_min > minute and t.spec.order_id]

        own = [r.vehicle_id for r in plan.routes if r.status is RouteStatus.ACTIVE and r.pending]
        targets = _Targets()
        busiest = sorted(own, key=lambda v: (-len(pending_at(v, self.WINDOW_AT)), v))
        if busiest and pending_at(busiest[0], self.WINDOW_AT):
            stops = pending_at(busiest[0], self.WINDOW_AT)
            targets.window_order = stops[-1].spec.order_id
            targets.window_end = stops[0].arrival_min + 25.0
        for vid in sorted(own, key=lambda v: (-len(pending_at(v, self.BREAKDOWN_AT)), v)):
            if pending_at(vid, self.BREAKDOWN_AT):
                targets.breakdown_vehicle = vid
                break
        pending_orders = {t.spec.order_id for vid in own for t in pending_at(vid, self.URGENT_AT)}
        for customer in core.dataset.customers:
            order = next((o for o in core.dataset.orders if o.customer_code == customer.code), None)
            if order and order.id in pending_orders:
                targets.urgent_customer = customer.code
                break
        return targets

    def _commands(self, targets: _Targets) -> list[tuple[float, str, EventCommand]]:
        label, lat, lon, radius, factor, duration = self.CLOSURE
        steps: list[tuple[float, str, EventCommand]] = [
            (
                self.CLOSURE_AT,
                "Cierre vial",
                CloseRoadCommand(label, lat, lon, radius, factor, duration),
            )
        ]
        if targets.window_order:
            steps.append(
                (
                    self.WINDOW_AT,
                    "Cambio de ventana",
                    ChangeWindowCommand(targets.window_order, self.WINDOW_AT, targets.window_end),
                )
            )
        if targets.urgent_customer:
            steps.append(
                (
                    self.URGENT_AT,
                    "Pedido urgente",
                    UrgentOrderCommand(
                        targets.urgent_customer, 400.0, 2.0, self.URGENT_AT, self.URGENT_AT + 300.0
                    ),
                )
            )
        if targets.breakdown_vehicle:
            steps.append((self.BREAKDOWN_AT, "Avería", BreakdownCommand(targets.breakdown_vehicle)))
        return steps

    # --------------------------------------------------------------- escenarios
    def run(self) -> tuple[ScenarioView, ...]:
        dynamic = self._factory()
        dynamic.day.start(SCENARIO_ACTOR)
        targets = self._targets(dynamic)
        applied: list[str] = []
        for minute, name, command in self._commands(targets):
            dynamic.day.seek(minute)
            try:
                result = dynamic.handle_event.execute(SCENARIO_ACTOR, command)
            except DomainError:
                continue  # el objetivo ya no aplica en este plan: se omite en ambos escenarios
            applied.append(name)
            if result.proposal.status is ProposalStatus.PENDING:
                dynamic.approve.execute(SCENARIO_ACTOR, result.proposal.id, True, "escenario")
        dynamic.day.seek(END_OF_DAY_MIN)
        committed = list(dynamic.core.repo.orders())
        dyn_timings = _flat(_timings_by_vehicle(dynamic, END_OF_DAY_MIN))
        dyn_versions = len(dynamic.core.repo.plans())
        dyn_reserves = _reserve_activations(dynamic)

        clean = self._factory()
        clean.day.start(SCENARIO_ACTOR)
        base_ids = list(clean.core.repo.orders())
        clean_timings = _flat(_timings_by_vehicle(clean, END_OF_DAY_MIN))
        static_timings, static_committed = self._static_with_events(clean, applied, targets)

        def view(
            key: str,
            title: str,
            description: str,
            mode: str,
            timings: list[StopTiming],
            ids: list[str],
            versions: int,
            reserves: int,
            events: tuple[str, ...],
            rate: float = 0.0,
        ) -> ScenarioView:
            return ScenarioView(
                key=key,
                title=title,
                description=description,
                mode=mode,
                incomplete_rate=rate,
                kpis=kpi_view(compute_kpis(timings, ids, rate)),
                plan_versions=versions,
                reserve_activations=reserves,
                events=events,
            )

        events = tuple(applied)
        return (
            view(
                "clean",
                "Sin eventos · plan de la mañana",
                "El plan inicial se cumple tal como se planificó.",
                "static",
                clean_timings,
                base_ids,
                1,
                0,
                (),
            ),
            view(
                "static_events",
                "Con eventos · plan estático",
                "Mismos eventos, pero el plan de la mañana no se modifica: los cierres atrasan "
                "las rutas, el pedido urgente no se atiende y la carga del vehículo averiado "
                "queda sin entregar.",
                "static",
                static_timings,
                static_committed,
                1,
                0,
                events,
            ),
            view(
                "dynamic_events",
                "Con eventos · ruteo dinámico",
                "Mismos eventos; cada propuesta de re-ruteo se aprueba y crea una versión nueva.",
                "dynamic",
                dyn_timings,
                committed,
                dyn_versions,
                dyn_reserves,
                events,
            ),
            view(
                "dynamic_incomplete",
                "Con eventos · ruteo dinámico · 10 % de entregas incompletas (ejemplo)",
                "Igual al escenario dinámico, pero se supone que una de cada diez entregas llegó "
                "incompleta. Ilustra cómo baja el OTIF sin cambiar la puntualidad.",
                "dynamic",
                dyn_timings,
                committed,
                dyn_versions,
                dyn_reserves,
                events,
                INCOMPLETE_RATE_EXAMPLE,
            ),
        )

    def _static_with_events(
        self, ws: RoutingWorkspace, applied: list[str], targets: _Targets
    ) -> tuple[list[StopTiming], list[str]]:
        """El plan de la mañana, sin tocarlo, sufriendo los mismos eventos (sin re-ruteo)."""
        core = ws.core
        label, lat, lon, radius, factor, duration = self.CLOSURE
        committed = list(core.repo.orders())
        if "Cierre vial" in applied:
            core.repo.add_closure(
                Closure(
                    "ESC-1",
                    label,
                    GeoPoint(lat, lon),
                    radius,
                    factor,
                    self.CLOSURE_AT,
                    self.CLOSURE_AT + duration,
                )
            )
        if "Cambio de ventana" in applied and targets.window_order:
            order = core.repo.orders()[targets.window_order]
            core.repo.save_order(
                Order(
                    order.id,
                    order.customer_code,
                    order.kg,
                    order.m3,
                    TimeWindow(self.WINDOW_AT, targets.window_end),
                    order.priority,
                    order.urgent,
                )
            )
        if "Pedido urgente" in applied:
            committed.append("URG-ESTATICO")  # cuenta como comprometido y nunca se atiende
        by_vehicle = _timings_by_vehicle(ws, END_OF_DAY_MIN)
        if "Avería" in applied and targets.breakdown_vehicle in by_vehicle:
            broken = targets.breakdown_vehicle
            # lo que el vehículo averiado no alcanzó a entregar queda sin atender
            by_vehicle[broken] = [
                t for t in by_vehicle[broken] if t.arrival_min <= self.BREAKDOWN_AT
            ]
        return _flat(by_vehicle), committed


class IndicatorsService:
    """Indicadores en vivo (proyección al cierre) y escenarios, con caché por empresa."""

    def __init__(self, runner: ScenarioRunner) -> None:
        self._runner = runner
        self._cache: tuple[ScenarioView, ...] | None = None
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        """Los escenarios dependen de los maestros: al cambiarlos hay que volver a calcularlos."""
        with self._lock:
            self._cache = None

    def scenarios(self) -> tuple[ScenarioView, ...]:
        """Se calculan una vez por empresa (son deterministas) y no bloquean el día en curso."""
        with self._lock:
            if self._cache is None:
                self._cache = self._runner.run()
            return self._cache

    @staticmethod
    def live(ws: RoutingWorkspace) -> LiveIndicators:
        core = ws.core
        now = core.now_min()
        plan = core.repo.active_plan()
        if plan is None:
            raise ConflictError("Aún no hay plan del día.")
        timings = _flat(_timings_by_vehicle(ws, now))
        committed = list(core.repo.orders())
        done = [t for t in timings if t.departure_min <= now and t.spec.order_id]
        return LiveIndicators(
            minute=now,
            plan_version=plan.version,
            projected=kpi_view(compute_kpis(timings, committed)),
            delivered_so_far=len(done),
            on_time_so_far=sum(1 for t in done if t.delay_min <= 1e-6),
        )

    def definitions(self) -> tuple[str, ...]:
        return DEFINITIONS
