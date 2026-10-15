"""Heurística de ruteo: inserción por arrepentimiento, 2-opt y reubicación.

Sirve como comparación del solver y como motor del re-ruteo de un solo vehículo. No se promete
que supere al solver: el plan guarda el puntaje de ambos y elige el mejor con criterio explícito.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from fleetplanner.domain.routing.evaluation import RouteEvaluation, StopSpec
from fleetplanner.domain.routing.problem import (
    RoutingProblem,
    RoutingSolution,
    VehicleSlot,
    explain_unassigned,
)

_IMPROVEMENT = 1e-6
_MAX_PASSES = 25
_NO_ALTERNATIVE = 1e9  # arrepentimiento de un pedido con una sola opción: se inserta primero

ENGINE_NAME = "Heurística (arrepentimiento + 2-opt + reubicación)"


# ------------------------------------------------------- secuenciar un vehículo
SequenceEvaluator = Callable[[Sequence[StopSpec]], RouteEvaluation]


def optimize_sequence(
    prefix: Sequence[StopSpec], free: Sequence[StopSpec], evaluate: SequenceEvaluator
) -> list[StopSpec]:
    """Mejor orden de ``free`` detrás de ``prefix`` (que no se mueve). Determinista.

    Parte de una inserción más barata, sembrada por fin de ventana, y la mejora con 2-opt y
    reubicación hasta que no haya mejora.
    """
    pre = list(prefix)
    if len(free) <= 1:
        return list(free)

    def cost(seq: Sequence[StopSpec]) -> float:
        ev = evaluate([*pre, *seq])
        return ev.score if ev.capacity_ok else float("inf")

    ordered = sorted(
        free,
        key=lambda s: (
            s.window.end_min if s.window else 0.0,
            s.window.start_min if s.window else 0.0,
            s.key,
        ),
    )
    seq: list[StopSpec] = []
    for spec in ordered:  # inserción más barata
        best_pos, best_cost = 0, float("inf")
        for pos in range(len(seq) + 1):
            c = cost([*seq[:pos], spec, *seq[pos:]])
            if c < best_cost - _IMPROVEMENT:
                best_pos, best_cost = pos, c
        seq.insert(best_pos, spec)

    current = cost(seq)
    for _ in range(_MAX_PASSES):
        improved = False
        for i in range(len(seq) - 1):  # 2-opt
            for j in range(i + 1, len(seq)):
                cand = [*seq[:i], *reversed(seq[i : j + 1]), *seq[j + 1 :]]
                c = cost(cand)
                if c < current - _IMPROVEMENT:
                    seq, current, improved = cand, c, True
        for i in range(len(seq)):  # reubicación
            spec = seq[i]
            rest = [*seq[:i], *seq[i + 1 :]]
            for pos in range(len(rest) + 1):
                if pos == i:
                    continue
                cand = [*rest[:pos], spec, *rest[pos:]]
                c = cost(cand)
                if c < current - _IMPROVEMENT:
                    seq, current, improved = cand, c, True
                    break
        if not improved:
            break
    return seq


# ------------------------------------------------------------- varios vehículos
def solve_with_heuristic(problem: RoutingProblem) -> RoutingSolution:
    started = time.perf_counter()
    routes: dict[str, list[str]] = {s.vehicle.id: [] for s in problem.slots}
    slots = {s.vehicle.id: s for s in problem.slots}
    scores = {v: problem.evaluate(slots[v], []).score for v in routes}
    pending = sorted(n.id for n in problem.nodes)
    unassigned: dict[str, str] = {}

    # cache de mejores inserciones por (pedido, vehículo); se invalida al cambiar la ruta
    cache: dict[tuple[str, str], tuple[float, int] | None] = {}

    def best_insertion(order_id: str, vehicle_id: str) -> tuple[float, int] | None:
        key = (order_id, vehicle_id)
        if key in cache:
            return cache[key]
        base = scores[vehicle_id]
        best: tuple[float, int] | None = None
        ids = routes[vehicle_id]
        for pos in range(len(ids) + 1):
            ev = problem.evaluate(slots[vehicle_id], [*ids[:pos], order_id, *ids[pos:]])
            if not ev.capacity_ok:
                continue
            delta = ev.score - base
            if best is None or delta < best[0] - _IMPROVEMENT:
                best = (delta, pos)
        cache[key] = best
        return best

    while pending:
        choice: tuple[float, str, str, int] | None = (
            None  # (arrepentimiento, pedido, vehículo, pos)
        )
        for order_id in pending:
            options = sorted(
                (opt[0], v, opt[1])
                for v in routes
                if (opt := best_insertion(order_id, v)) is not None
            )
            if not options:
                continue
            regret = options[1][0] - options[0][0] if len(options) > 1 else _NO_ALTERNATIVE
            cand = (regret, order_id, options[0][1], options[0][2])
            if (
                choice is None
                or cand[0] > choice[0] + _IMPROVEMENT
                or (
                    abs(cand[0] - choice[0]) <= _IMPROVEMENT
                    and problem.node(cand[1]).kg > problem.node(choice[1]).kg
                )
            ):
                choice = cand
        if choice is None:
            for order_id in pending:
                unassigned[order_id] = explain_unassigned(problem, order_id)
            break
        _, order_id, vehicle_id, pos = choice
        routes[vehicle_id].insert(pos, order_id)
        pending.remove(order_id)
        scores[vehicle_id] = problem.evaluate(slots[vehicle_id], routes[vehicle_id]).score
        for k in [k for k in cache if k[1] == vehicle_id]:
            del cache[k]

    _improve(problem, slots, routes, scores)
    return RoutingSolution(
        routes={v: tuple(ids) for v, ids in routes.items()},
        unassigned=unassigned,
        engine=ENGINE_NAME,
        elapsed_s=time.perf_counter() - started,
    )


def _improve(
    problem: RoutingProblem,
    slots: dict[str, VehicleSlot],
    routes: dict[str, list[str]],
    scores: dict[str, float],
) -> None:
    nodes = {n.id: n for n in problem.nodes}

    def best_order(vehicle_id: str, ids: list[str]) -> list[str]:
        slot = slots[vehicle_id]
        specs = [nodes[i].to_spec() for i in ids]
        by_key = {s.key: s for s in specs}

        def evaluate(seq: Sequence[StopSpec]) -> RouteEvaluation:
            return problem.evaluate(slot, [s.key for s in seq])

        return [s.key for s in optimize_sequence([], [by_key[i] for i in ids], evaluate)]

    for v in routes:  # 2-opt y reubicación dentro de cada ruta
        if len(routes[v]) > 1:
            candidate = best_order(v, routes[v])
            score = problem.evaluate(slots[v], candidate).score
            if score < scores[v] - _IMPROVEMENT:
                routes[v], scores[v] = candidate, score

    for _ in range(_MAX_PASSES):  # reubicación entre rutas
        improved = False
        for src in routes:
            for order_id in list(routes[src]):
                for dst in routes:
                    if dst == src:
                        continue
                    base_src = [i for i in routes[src] if i != order_id]
                    new_src = problem.evaluate(slots[src], base_src).score
                    for pos in range(len(routes[dst]) + 1):
                        cand = [*routes[dst][:pos], order_id, *routes[dst][pos:]]
                        ev = problem.evaluate(slots[dst], cand)
                        if not ev.capacity_ok:
                            continue
                        gain = scores[src] + scores[dst] - (new_src + ev.score)
                        if gain > _IMPROVEMENT:
                            routes[src], routes[dst] = base_src, cand
                            scores[src], scores[dst] = new_src, ev.score
                            improved = True
                            break
                    if order_id not in routes[src]:
                        break
        if not improved:
            break
