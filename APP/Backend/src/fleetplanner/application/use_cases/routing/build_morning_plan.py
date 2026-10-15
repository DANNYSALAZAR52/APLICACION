"""BuildMorningPlan: plan inicial de la mañana (versión 1) con solver y heurística comparados."""

from __future__ import annotations

from fleetplanner.application.use_cases.routing.core import DEGRADED_NOTICE, RoutingCore
from fleetplanner.domain.routing.heuristic import solve_with_heuristic
from fleetplanner.domain.routing.models import VehicleKind
from fleetplanner.domain.routing.plan import (
    EngineResult,
    RouteAnchor,
    RoutePlan,
    RouteStatus,
    UnassignedOrder,
    VehicleRoute,
)
from fleetplanner.domain.routing.problem import (
    RoutingProblem,
    RoutingSolution,
    VehicleSlot,
    evaluate_solution,
    solution_score,
)
from fleetplanner.domain.shared.errors import ConflictError

SOLVER_TIME_LIMIT_S = 2.5


class BuildMorningPlan:
    """Lee pedidos pendientes y vehículos y guarda el plan como versión 1.

    Corre el solver (OR-Tools) y la heurística sobre el mismo problema, descarta cualquier plan
    que viole capacidad y elige el de menos pedidos sin asignar y, a igualdad, menor puntaje.
    No se asume que uno gane siempre: el plan conserva el puntaje de ambos.
    """

    def __init__(self, core: RoutingCore) -> None:
        self._core = core

    def execute(self, actor: str) -> RoutePlan:
        core = self._core
        if core.repo.active_plan() is not None:
            raise ConflictError("Ya existe un plan para este día; reinicie el día para crear otro.")
        params = core.params
        resolver = core.resolver()
        nodes = tuple(core.node_for(o) for _, o in sorted(core.repo.orders().items()))
        own = [v for v in core.dataset.vehicles if v.kind is VehicleKind.OWN]
        slots = tuple(
            VehicleSlot(
                v, params.operational_capacity_kg(v), core.depot_point, params.departure_min
            )
            for v in own
        )
        problem = RoutingProblem(core.depot_point, slots, nodes, params, resolver)

        candidates: list[tuple[RoutingSolution, float, bool]] = []
        notes: list[str] = []
        try:
            solved = core.solver.solve(problem, SOLVER_TIME_LIMIT_S)
            candidates.append(
                (solved, solution_score(problem, solved), self._feasible(problem, solved))
            )
        except Exception as exc:  # noqa: BLE001 - el solver es externo; el plan no debe depender de él
            notes.append(
                f"El solver no pudo resolver ({type(exc).__name__}); se usa la heurística."
            )
        heuristic = solve_with_heuristic(problem)
        candidates.append(
            (heuristic, solution_score(problem, heuristic), self._feasible(problem, heuristic))
        )

        eligible = [c for c in candidates if c[2]]
        if not eligible:
            raise ConflictError(
                "Ningún motor produjo un plan que respete la capacidad de los vehículos."
            )
        chosen = min(
            eligible,
            key=lambda c: (len(c[0].unassigned), round(c[1], 6), 0 if c[0] is not heuristic else 1),
        )
        solution = chosen[0]
        comparison = tuple(
            EngineResult(
                engine=s.engine,
                score=score,
                assigned_orders=s.assigned_count,
                unassigned_orders=len(s.unassigned),
                elapsed_s=s.elapsed_s,
                chosen=s is solution,
            )
            for s, score, ok in candidates
            if ok
        )
        if resolver.degraded:
            notes.append(DEGRADED_NOTICE + ": el proveedor de tiempos no respondió.")
        notes.append("DATOS DE DEMOSTRACIÓN: pedidos y clientes sintéticos.")

        routes = self._routes(core, problem, solution)
        unassigned = tuple(
            UnassignedOrder(oid, problem.node(oid).customer.code, reason)
            for oid, reason in sorted(solution.unassigned.items())
        )
        plan = RoutePlan(
            version=1,
            base_version=None,
            created_at=core.clock.now(),
            created_by=actor,
            reason="Plan inicial de la mañana",
            routes=routes,
            unassigned=unassigned,
            engine=solution.engine,
            comparison=comparison,
            notes=tuple(notes),
        )
        core.repo.add_plan(plan)
        return plan

    @staticmethod
    def _feasible(problem: RoutingProblem, solution: RoutingSolution) -> bool:
        return all(e.capacity_ok for e in evaluate_solution(problem, solution).values())

    @staticmethod
    def _routes(
        core: RoutingCore, problem: RoutingProblem, solution: RoutingSolution
    ) -> tuple[VehicleRoute, ...]:
        params = core.params
        slot_by_id = {s.vehicle.id: s for s in problem.slots}
        routes: list[VehicleRoute] = []
        for vehicle in core.dataset.vehicles:
            capacity = params.operational_capacity_kg(vehicle)
            anchor = RouteAnchor(core.depot_point, params.departure_min, "CEDI")
            slot = slot_by_id.get(vehicle.id)
            if slot is None:  # reserva o tercero: disponible, sin ruta
                empty = problem.evaluate(
                    VehicleSlot(vehicle, capacity, core.depot_point, params.departure_min), []
                )
                routes.append(
                    VehicleRoute(
                        vehicle.id,
                        vehicle.plate,
                        vehicle.vehicle_type,
                        capacity,
                        anchor,
                        0.0,
                        (),
                        (),
                        empty,
                        status=RouteStatus.STANDBY,
                        note="Reserva disponible"
                        if vehicle.kind is VehicleKind.RESERVE
                        else "Tercero a demanda",
                    )
                )
                continue
            ids = solution.routes.get(vehicle.id, ())
            specs = tuple(problem.node(i).to_spec() for i in ids)
            routes.append(
                VehicleRoute(
                    vehicle.id, vehicle.plate, vehicle.vehicle_type, capacity, anchor,
                    sum(problem.node(i).kg for i in ids), (), specs,
                    problem.evaluate(slot, ids),
                )
            )  # fmt: skip
        return tuple(routes)
