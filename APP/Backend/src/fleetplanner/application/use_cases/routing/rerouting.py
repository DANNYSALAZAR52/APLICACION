"""Generación de propuestas de re-ruteo (DOCS.MD §7.5).

El sistema **propone**: nada de lo que se calcula aquí cambia el plan vigente. Una propuesta
trae el plan nuevo completo (versión siguiente) y el antes/después para que el despachador
decida; solo `ApproveReroute` lo guarda.

Reglas que se respetan:
* Lo ya entregado o en servicio queda congelado (``freeze_route``).
* Una carga no cambia de vehículo salvo transbordo (avería) o recarga en el CEDI (urgente).
* Cada re-ruteo es una versión nueva; las anteriores no se tocan.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from fleetplanner.application.use_cases.routing.core import RoutingCore, TravelResolver
from fleetplanner.domain.routing.evaluation import (
    RouteEvaluation,
    StopKind,
    StopSpec,
    evaluate_route,
)
from fleetplanner.domain.routing.events import (
    BreakdownData,
    ClosureEventData,
    DelayRiskData,
    OperationalEvent,
    ProposalImpact,
    UrgentOrderData,
    WindowChangeData,
)
from fleetplanner.domain.routing.heuristic import optimize_sequence
from fleetplanner.domain.routing.models import VehicleKind
from fleetplanner.domain.routing.plan import (
    FrozenRoute,
    RouteAnchor,
    RoutePlan,
    RouteStatus,
    RouteView,
    UnassignedOrder,
    VehicleRoute,
    freeze_route,
    make_route,
)
from fleetplanner.domain.shared.errors import ConflictError

_EPS = 1e-6
ENGINE = "Re-ruteo: heurística de secuenciación"


@dataclass(frozen=True)
class ProposalDraft:
    plan: RoutePlan | None  # None = no hay cambios que proponer
    reason: str
    summary: str
    impact: ProposalImpact
    requires_confirmation: bool


@dataclass(frozen=True)
class Context:
    now: float
    plan: RoutePlan
    resolver: TravelResolver
    views: dict[str, RouteView]
    frozen: dict[str, FrozenRoute]


class ReroutePlanner:
    def __init__(self, core: RoutingCore) -> None:
        self._core = core

    # ----------------------------------------------------------------- contexto
    def context(self, exclude_closures: Sequence[str] = ()) -> Context:
        core = self._core
        plan = core.repo.active_plan()
        if plan is None:
            raise ConflictError("Aún no hay plan del día; cree el plan de la mañana primero.")
        now = core.now_min()
        resolver = core.resolver(exclude_ids=exclude_closures)
        views = {r.vehicle_id: core.view(r, resolver, now) for r in plan.routes}
        frozen = {
            vid: freeze_route(v, now)
            for vid, v in views.items()
            if v.route.status is RouteStatus.ACTIVE
        }
        return Context(now, plan, resolver, views, frozen)

    # ------------------------------------------------------------------ entrada
    def propose(self, event: OperationalEvent, actor: str) -> ProposalDraft:
        payload = event.payload
        if isinstance(payload, ClosureEventData):
            return self._closure(event, payload, actor)
        if isinstance(payload, WindowChangeData):
            return self._window_change(event, payload, actor)
        if isinstance(payload, UrgentOrderData):
            return self._urgent(event, payload, actor)
        if isinstance(payload, BreakdownData):
            return self._breakdown(event, payload, actor)
        if isinstance(payload, DelayRiskData):
            return self._delay_risk(event, payload, actor)
        raise ConflictError("Tipo de evento no soportado.")  # pragma: no cover

    # ----------------------------------------------------------------- utilidades
    @staticmethod
    def _split(pending: Sequence[StopSpec]) -> tuple[list[StopSpec], list[StopSpec]]:
        """Prefijo fijo (hasta la última recarga/transbordo) y entregas reordenables."""
        last = max(
            (i for i, s in enumerate(pending) if s.kind is not StopKind.DELIVERY), default=-1
        )
        return list(pending[: last + 1]), list(pending[last + 1 :])

    def _evaluator(
        self, ctx: Context, route: VehicleRoute, fr: FrozenRoute
    ) -> Callable[[Sequence[StopSpec]], RouteEvaluation]:
        core = self._core

        def evaluate(seq: Sequence[StopSpec]) -> RouteEvaluation:
            return evaluate_route(
                fr.anchor.point,
                fr.anchor.time_min,
                fr.load_kg,
                seq,
                core.depot_point,
                route.capacity_kg,
                core.params,
                ctx.resolver,
            )

        return evaluate

    def _rebuild(
        self,
        ctx: Context,
        route: VehicleRoute,
        fr: FrozenRoute,
        specs: Sequence[StopSpec],
        note: str = "",
    ) -> VehicleRoute:
        core = self._core
        return make_route(
            route, fr.frozen, fr.anchor, fr.load_kg, specs, core.depot_point, core.params,
            ctx.resolver, status=RouteStatus.ACTIVE, note=note,
        )  # fmt: skip

    def _resequence(self, ctx: Context, vehicle_id: str) -> VehicleRoute | None:
        """Mejor orden de las entregas pendientes del vehículo, o None si no mejora."""
        view, fr = ctx.views.get(vehicle_id), ctx.frozen.get(vehicle_id)
        if view is None or fr is None:
            return None
        prefix, free = self._split(fr.pending)
        if len(free) < 2:
            return None
        evaluate = self._evaluator(ctx, view.route, fr)
        current = evaluate(fr.pending)
        best = optimize_sequence(prefix, free, evaluate)
        candidate = evaluate([*prefix, *best])
        if not candidate.capacity_ok or candidate.score >= current.score - _EPS:
            return None
        return self._rebuild(ctx, view.route, fr, [*prefix, *best])

    def _restate(self, ctx: Context, route: VehicleRoute) -> VehicleRoute:
        """Copia una ruta sin cambios a la versión nueva, con horarios al día de hoy."""
        core = self._core
        refreshed = core.refresh_route(route)
        return make_route(
            refreshed, refreshed.frozen, refreshed.anchor, refreshed.initial_load_kg,
            refreshed.pending, core.depot_point, core.params, ctx.resolver,
            status=refreshed.status, note=refreshed.note,
        )  # fmt: skip

    def _assemble(
        self,
        ctx: Context,
        replaced: dict[str, VehicleRoute],
        extra_unassigned: Sequence[UnassignedOrder],
        reason: str,
        actor: str,
        notes: Sequence[str] = (),
    ) -> RoutePlan:
        routes = tuple(
            replaced[r.vehicle_id] if r.vehicle_id in replaced else self._restate(ctx, r)
            for r in ctx.plan.routes
        )
        return RoutePlan(
            version=ctx.plan.version + 1,
            base_version=ctx.plan.version,
            created_at=self._core.clock.now(),
            created_by=actor,
            reason=reason,
            routes=routes,
            unassigned=(*ctx.plan.unassigned, *extra_unassigned),
            engine=ENGINE,
            notes=tuple(notes),
        )

    @staticmethod
    def _totals(evals: Sequence[RouteEvaluation]) -> tuple[int, float, float]:
        return (
            sum(e.late_stops for e in evals),
            sum(e.delay_min for e in evals),
            sum(e.score for e in evals),
        )

    def _impact(
        self,
        ctx: Context,
        replaced: dict[str, VehicleRoute],
        *,
        activates_reserve: bool = False,
        reserve_vehicle: str | None = None,
        unattended_before: int = 0,
        unattended_orders: Sequence[str] = (),
        notes: Sequence[str] = (),
        skip_before: Sequence[str] = (),
    ) -> ProposalImpact:
        """Antes = el plan vigente con lo que se sabe hoy; después = con el cambio propuesto."""
        before = [
            v.evaluation
            for vid, v in ctx.views.items()
            if v.route.status is RouteStatus.ACTIVE and vid not in skip_before
        ]
        after = [
            replaced[vid].evaluation if vid in replaced else v.evaluation
            for vid, v in ctx.views.items()
            if (replaced[vid].status if vid in replaced else v.route.status) is RouteStatus.ACTIVE
        ]
        late_b, delay_b, score_b = self._totals(before)
        late_a, delay_a, score_a = self._totals(after)
        return ProposalImpact(
            late_stops_before=late_b,
            delay_min_before=delay_b,
            late_stops_after=late_a,
            delay_min_after=delay_a,
            score_before=score_b,
            score_after=score_a,
            affected_vehicles=tuple(sorted(replaced)),
            activates_reserve=activates_reserve,
            reserve_vehicle=reserve_vehicle,
            unattended_before=unattended_before,
            unattended_orders=tuple(unattended_orders),
            notes=tuple(notes),
        )

    def _plate(self, vehicle_id: str) -> str:
        return self._core.vehicle(vehicle_id).plate

    # ------------------------------------------------------------------- cierre
    def _closure(
        self, event: OperationalEvent, data: ClosureEventData, actor: str
    ) -> ProposalDraft:
        ctx = self.context()
        without = self.context(exclude_closures=[event.id])
        affected = [
            vid
            for vid, v in ctx.views.items()
            if v.route.status is RouteStatus.ACTIVE
            and abs(v.evaluation.score - without.views[vid].evaluation.score) > _EPS
        ]
        replaced: dict[str, VehicleRoute] = {}
        for vid in affected:
            better = self._resequence(ctx, vid)
            if better is not None:
                replaced[vid] = better
        reason = f"Cierre vial: {data.label}"
        impacted = ", ".join(self._plate(v) for v in affected) or "ninguno"
        notes = [
            f"Vehículos con tramos afectados por el cierre: {impacted}.",
            f"Factor ×{data.factor:g} en un radio de {data.radius_km:g} km durante "
            f"{data.duration_min:g} min.",
        ]
        if ctx.resolver.degraded:
            notes.append("Tiempos estimados sin tráfico: el proveedor no respondió.")
        if not replaced:
            summary = (
                "El cierre no obliga a re-secuenciar: ninguna ruta mejora cambiando el orden."
                if affected
                else "El cierre no toca ningún tramo pendiente de las rutas vigentes."
            )
            return ProposalDraft(
                None,
                reason,
                summary,
                self._impact(ctx, {}, notes=notes),
                requires_confirmation=False,
            )
        plan = self._assemble(ctx, replaced, (), reason, actor, notes)
        plates = ", ".join(self._plate(v) for v in sorted(replaced))
        return ProposalDraft(
            plan,
            reason,
            f"Se re-secuencian las entregas pendientes de: {plates}.",
            self._impact(ctx, replaced, notes=notes),
            requires_confirmation=len(replaced) > 1,
        )

    # ------------------------------------------------------------------ ventana
    def _window_change(
        self, event: OperationalEvent, data: WindowChangeData, actor: str
    ) -> ProposalDraft:
        ctx = self.context()
        reason = f"Cambio de ventana del pedido {data.order_id} a {data.window.label()}"
        carrier = next(
            (
                vid
                for vid, fr in ctx.frozen.items()
                if any(s.order_id == data.order_id for s in fr.pending)
            ),
            None,
        )
        if carrier is None:
            return ProposalDraft(
                None, reason,
                "El pedido no está pendiente en ninguna ruta; la nueva ventana quedó registrada.",
                self._impact(ctx, {}), requires_confirmation=False,
            )  # fmt: skip
        better = self._resequence(ctx, carrier)
        replaced = {carrier: better} if better is not None else {}
        notes = [f"Vehículo que lleva el pedido: {self._plate(carrier)}."]
        if not replaced:
            return ProposalDraft(
                None, reason,
                "Con la nueva ventana no conviene cambiar el orden de la ruta.",
                self._impact(ctx, {}, notes=notes), requires_confirmation=False,
            )  # fmt: skip
        plan = self._assemble(ctx, replaced, (), reason, actor, notes)
        return ProposalDraft(
            plan, reason,
            f"Se re-secuencia la ruta de {self._plate(carrier)} para respetar la nueva ventana.",
            self._impact(ctx, replaced, notes=notes), requires_confirmation=False,
        )  # fmt: skip

    # ------------------------------------------------------------------- riesgo
    def _delay_risk(
        self, event: OperationalEvent, data: DelayRiskData, actor: str
    ) -> ProposalDraft:
        ctx = self.context()
        better = self._resequence(ctx, data.vehicle_id)
        reason = f"Riesgo de retraso en {self._plate(data.vehicle_id)}"
        if better is None:
            return ProposalDraft(
                None, reason, "Re-secuenciar no mejora los horarios pendientes.",
                self._impact(ctx, {}), requires_confirmation=False,
            )  # fmt: skip
        replaced = {data.vehicle_id: better}
        plan = self._assemble(ctx, replaced, (), reason, actor)
        return ProposalDraft(
            plan, reason, "Se propone re-secuenciar las entregas pendientes del vehículo.",
            self._impact(ctx, replaced), requires_confirmation=False,
        )  # fmt: skip

    # ------------------------------------------------------------------ urgente
    def _urgent(self, event: OperationalEvent, data: UrgentOrderData, actor: str) -> ProposalDraft:
        core = self._core
        ctx = self.context()
        params = core.params
        order = core.repo.orders()[data.order_id]
        urgent = core.node_for(order).to_spec()
        reason = f"Pedido urgente {data.order_id}"

        best: tuple[float, str, VehicleRoute, bool, str | None] | None = None
        # (delta de puntaje, desempate, ruta nueva, activa reserva, vehículo de reserva)

        def consider(delta: float, vid: str, route: VehicleRoute, reserve: bool) -> None:
            nonlocal best
            candidate = (delta, vid, route, reserve, vid if reserve else None)
            if best is None or (candidate[0], candidate[1]) < (best[0], best[1]):
                best = candidate

        for vid, fr in ctx.frozen.items():  # opción A: un vehículo en ruta vuelve a recargar
            view = ctx.views[vid]
            route = view.route
            evaluate = self._evaluator(ctx, route, fr)
            current = evaluate(fr.pending).score
            found = self._best_reload_insertion(fr, evaluate, urgent, data.kg)
            if found is not None:
                specs, _ = found
                rebuilt = self._rebuild(ctx, route, fr, specs, note=f"Recarga para {data.order_id}")
                consider(rebuilt.evaluation.score - current, vid, rebuilt, False)

        for vid, view in ctx.views.items():  # opción B: activar reserva o tercero
            if view.route.status is not RouteStatus.STANDBY:
                continue
            vehicle = core.vehicle(vid)
            start = max(ctx.now, view.route.anchor.time_min) + params.reload_min
            anchor = RouteAnchor(core.depot_point, start, "Carga en CEDI")
            route = make_route(
                view.route, (), anchor, data.kg, [urgent], core.depot_point, params,
                ctx.resolver, status=RouteStatus.ACTIVE, note=f"Reserva para {data.order_id}",
            )  # fmt: skip
            timing = route.evaluation.timings[0]
            if not route.evaluation.capacity_ok or timing.delay_min > _EPS:
                continue
            cost = params.reserve_activation_cost * (
                2.0 if vehicle.kind is VehicleKind.THIRD_PARTY else 1.0
            )
            consider(route.evaluation.score + cost, vid, route, True)

        if best is None:
            return self._postpone(ctx, data, reason, actor)
        delta, vid, route, reserve, reserve_id = best
        replaced = {vid: route}
        mode = (
            f"activar la reserva {self._plate(vid)}"
            if reserve
            else f"que {self._plate(vid)} regrese al CEDI a recargar"
        )
        notes = [
            f"Opción elegida: {mode} (costo adicional estimado {delta:.1f} puntos).",
            "Se compararon los vehículos en ruta (con retorno al CEDI) y la reserva disponible.",
        ]
        plan = self._assemble(ctx, replaced, (), reason, actor, notes)
        return ProposalDraft(
            plan, reason, f"Para atender {data.order_id} se propone {mode}.",
            self._impact(
                ctx, replaced, activates_reserve=reserve, reserve_vehicle=reserve_id, notes=notes
            ),
            requires_confirmation=reserve,
        )  # fmt: skip

    def _best_reload_insertion(
        self,
        fr: FrozenRoute,
        evaluate: Callable[[Sequence[StopSpec]], RouteEvaluation],
        urgent: StopSpec,
        kg: float,
    ) -> tuple[list[StopSpec], RouteEvaluation] | None:
        """Mejor secuencia con recarga en el CEDI y el urgente después, o None si no es viable."""
        core = self._core
        reload_spec = StopSpec(
            key=f"RELOAD-{urgent.key}",
            kind=StopKind.RELOAD,
            point=core.depot_point,
            label="Recarga en CEDI",
            service_min=core.params.reload_min,
            load_delta_kg=kg,
        )
        pending = list(fr.pending)
        first = max(
            (i + 1 for i, s in enumerate(pending) if s.kind is not StopKind.DELIVERY), default=0
        )

        def viable(ev: RouteEvaluation) -> bool:
            if not ev.capacity_ok:
                return False
            hit = next((t for t in ev.timings if t.spec.key == urgent.key), None)
            return hit is not None and hit.delay_min <= _EPS

        best: tuple[list[StopSpec], RouteEvaluation] | None = None
        for r in range(first, len(pending) + 1):
            head, tail = pending[:r], pending[r:]
            base = [*head, reload_spec]
            for pos in range(len(tail) + 1):
                seq = [*base, *tail[:pos], urgent, *tail[pos:]]
                ev = evaluate(seq)
                if viable(ev) and (best is None or ev.score < best[1].score - _EPS):
                    best = (seq, ev)
            free = [*tail, urgent]
            if len(free) > 1:
                tuned = [*base, *optimize_sequence(base, free, evaluate)]
                ev = evaluate(tuned)
                if viable(ev) and (best is None or ev.score < best[1].score - _EPS):
                    best = (tuned, ev)
        return best

    def _postpone(
        self, ctx: Context, data: UrgentOrderData, reason: str, actor: str
    ) -> ProposalDraft:
        note = (
            "Ninguna alternativa cumple capacidad y ventana: el pedido se atenderá el día "
            "siguiente. Aprobar confirma el aplazamiento; se alerta al despachador."
        )
        order = self._core.repo.orders()[data.order_id]
        unassigned = UnassignedOrder(order.id, order.customer_code, note)
        plan = self._assemble(ctx, {}, [unassigned], reason, actor, [note])
        return ProposalDraft(
            plan, reason, note,
            self._impact(ctx, {}, unattended_orders=[data.order_id], notes=[note]),
            requires_confirmation=True,
        )  # fmt: skip

    # ------------------------------------------------------------------- avería
    def _breakdown(self, event: OperationalEvent, data: BreakdownData, actor: str) -> ProposalDraft:
        core = self._core
        ctx = self.context()
        params = core.params
        broken_id = data.vehicle_id
        view, fr = ctx.views.get(broken_id), ctx.frozen.get(broken_id)
        reason = f"Avería del vehículo {self._plate(broken_id)}"
        if view is None or fr is None:
            raise ConflictError(
                "El vehículo no tiene una ruta activa; no se puede registrar avería."
            )
        if any(s.kind is not StopKind.DELIVERY for s in fr.pending):
            raise ConflictError(
                "El vehículo aún tiene un transbordo o recarga pendiente; "
                "resuélvalo antes de registrar otra avería."
            )
        deliveries = [s for s in fr.pending if s.kind is StopKind.DELIVERY]
        remaining_kg = sum(-s.load_delta_kg for s in deliveries)
        spot = fr.anchor.point
        broken_route = make_route(
            view.route, fr.frozen, RouteAnchor(spot, ctx.now, "Punto de avería"), 0.0, (),
            core.depot_point, params, ctx.resolver, status=RouteStatus.BROKEN,
            note="Averiado; carga transbordada" if deliveries else "Averiado",
        )  # fmt: skip
        replaced: dict[str, VehicleRoute] = {broken_id: broken_route}
        notes = [
            f"El vehículo quedó detenido en el punto de avería ({spot.lat:.4f}, {spot.lon:.4f})."
        ]
        if not deliveries:
            plan = self._assemble(ctx, replaced, (), reason, actor, notes)
            return ProposalDraft(
                plan, reason, "Sin entregas pendientes: solo se marca el vehículo como averiado.",
                self._impact(ctx, replaced, notes=notes, skip_before=[broken_id]),
                requires_confirmation=False,
            )  # fmt: skip

        choice: tuple[float, str, VehicleRoute] | None = None
        for vid, rview in sorted(ctx.views.items()):
            if rview.route.status is not RouteStatus.STANDBY:
                continue
            vehicle = core.vehicle(vid)
            if params.operational_capacity_kg(vehicle) < remaining_kg:
                continue
            transfer = StopSpec(
                key=f"TRANSFER-{vid}",
                kind=StopKind.TRANSFER,
                point=spot,
                label="Transbordo en punto de avería",
                service_min=params.transshipment_min,
                load_delta_kg=remaining_kg,
            )
            anchor = RouteAnchor(
                core.depot_point, max(ctx.now, rview.route.anchor.time_min), "CEDI"
            )
            base = make_route(
                rview.route, (), anchor, 0.0, [transfer], core.depot_point, params,
                ctx.resolver, status=RouteStatus.ACTIVE,
            )  # fmt: skip

            def evaluate(
                seq: Sequence[StopSpec], _a: RouteAnchor = anchor, _r: VehicleRoute = base
            ) -> RouteEvaluation:
                return evaluate_route(
                    _a.point,
                    _a.time_min,
                    0.0,
                    seq,
                    core.depot_point,
                    _r.capacity_kg,
                    params,
                    ctx.resolver,
                )

            tuned = [transfer, *optimize_sequence([transfer], deliveries, evaluate)]
            route = make_route(
                rview.route, (), anchor, 0.0, tuned, core.depot_point, params, ctx.resolver,
                status=RouteStatus.ACTIVE, note=f"Reemplaza a {self._plate(broken_id)}",
            )  # fmt: skip
            if not route.evaluation.capacity_ok:
                continue
            cost = params.reserve_activation_cost * (
                2.0 if vehicle.kind is VehicleKind.THIRD_PARTY else 1.0
            )
            candidate = (route.evaluation.score + cost, vid, route)
            if choice is None or (candidate[0], candidate[1]) < (choice[0], choice[1]):
                choice = candidate

        if choice is None:
            note = (
                "No hay vehículo de reserva ni tercero con capacidad para la carga "
                f"({remaining_kg:g} kg): las entregas quedan sin atender y se alerta."
            )
            stranded = [
                UnassignedOrder(s.order_id or s.key, s.customer_code or "", note)
                for s in deliveries
            ]
            plan = self._assemble(ctx, replaced, stranded, reason, actor, [*notes, note])
            return ProposalDraft(
                plan, reason, note,
                self._impact(
                    ctx, replaced, unattended_before=len(deliveries),
                    unattended_orders=[u.order_id for u in stranded], notes=[*notes, note],
                    skip_before=[broken_id],
                ),
                requires_confirmation=True,
            )  # fmt: skip

        _, rid, route = choice
        replaced[rid] = route
        notes.append(
            f"Se envía {self._plate(rid)} desde el CEDI; transbordo de "
            f"{params.transshipment_min:g} min y luego entregas desde el punto de avería."
        )
        plan = self._assemble(ctx, replaced, (), reason, actor, notes)
        return ProposalDraft(
            plan, reason,
            f"{self._plate(rid)} recoge la carga de {self._plate(broken_id)} y atiende "
            f"{len(deliveries)} entregas pendientes.",
            self._impact(
                ctx, replaced, activates_reserve=True, reserve_vehicle=rid,
                unattended_before=len(deliveries), notes=notes, skip_before=[broken_id],
            ),
            requires_confirmation=True,
        )  # fmt: skip
