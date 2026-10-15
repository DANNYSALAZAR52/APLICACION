"""Adaptador OR-Tools (VRP con ventanas horarias y capacidad) para `RoutingSolverPort`.

Objetivo (multiplicado por 10 para trabajar con enteros), igual al puntaje de dominio:

    10·viaje + 2·espera + 200·retraso + 20·minutos_fuera_de_turno

* costo por arco = 8·minutos de viaje, más 2 por cada minuto de duración de la ruta (viaje +
  espera + servicio) con el coeficiente de "span" de la dimensión de tiempo;
* ventana: inicio duro (se espera) y fin blando con 200 por minuto de retraso;
* fin de turno blando con 20 por minuto;
* capacidad operativa dura por vehículo;
* un pedido solo se omite si no cabe: la penalidad por omitirlo es enorme.

La matriz de tiempos es única (OR-Tools no admite velocidades que cambian con la hora). Se calcula
a media jornada (hora de arranque + 3 h) y no a las 06:00: a esa hora las velocidades son más
altas que el resto del día y el solver subestimaba los viajes (planes con retrasos). El puntaje
final lo calcula el evaluador de dominio, no OR-Tools, para comparar motores con la misma regla.
"""

from __future__ import annotations

import time

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from fleetplanner.domain.routing.problem import RoutingProblem, RoutingSolution, explain_unassigned

ENGINE_NAME = "OR-Tools (VRP con ventanas y capacidad)"
_DROP_PENALTY = 5_000_000
_HORIZON = 3 * 24 * 60
MATRIX_OFFSET_MIN = 180  # la matriz se calcula a arranque + 3 h (media jornada)
_SOLUTION_LIMIT = 4000  # corta por soluciones antes que por reloj para repetir resultados


class OrToolsRoutingSolver:
    def solve(self, problem: RoutingProblem, time_limit_s: float) -> RoutingSolution:
        started = time.perf_counter()
        slots, nodes = problem.slots, problem.nodes
        if not slots or not nodes:
            return RoutingSolution(
                routes={s.vehicle.id: () for s in slots},
                unassigned={n.id: explain_unassigned(problem, n.id) for n in nodes},
                engine=ENGINE_NAME,
                elapsed_s=time.perf_counter() - started,
            )

        n_veh = len(slots)
        # nodos: [inicio de cada vehículo] + [CEDI] + [pedidos]
        points = (
            [s.anchor_point for s in slots]
            + [problem.depot_point]
            + [n.customer.point for n in nodes]
        )
        depot_idx = n_veh
        first_order = n_veh + 1
        ref = min(s.anchor_time_min for s in slots) + MATRIX_OFFSET_MIN
        size = len(points)

        travel = [[0] * size for _ in range(size)]
        for i in range(size):
            for j in range(size):
                if i != j:
                    travel[i][j] = round(problem.travel(points[i], points[j], ref).minutes)
        service = [0] * size
        for k, node in enumerate(nodes):
            service[first_order + k] = round(node.service_min)

        manager = pywrapcp.RoutingIndexManager(size, n_veh, list(range(n_veh)), [depot_idx] * n_veh)
        routing = pywrapcp.RoutingModel(manager)

        def arc_cost(from_index: int, to_index: int) -> int:
            i, j = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
            return int(8 * travel[i][j])

        arc = routing.RegisterTransitCallback(arc_cost)
        routing.SetArcCostEvaluatorOfAllVehicles(arc)

        def time_transit(from_index: int, to_index: int) -> int:
            i, j = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
            return int(travel[i][j] + service[i])

        t_cb = routing.RegisterTransitCallback(time_transit)
        routing.AddDimension(t_cb, _HORIZON, _HORIZON, False, "Time")
        time_dim = routing.GetDimensionOrDie("Time")
        weights = problem.params
        span = round(10 * weights.weight_wait)  # espera (y servicio, constante por pedido)
        for v in range(n_veh):
            time_dim.SetSpanCostCoefficientForVehicle(span, v)

        for v, slot in enumerate(slots):
            start = routing.Start(v)
            time_dim.CumulVar(start).SetRange(
                round(slot.anchor_time_min), round(slot.anchor_time_min)
            )
            end = routing.End(v)
            time_dim.SetCumulVarSoftUpperBound(
                end, round(weights.shift_end_min), round(10 * weights.weight_overtime)
            )

        for k, node in enumerate(nodes):
            index = manager.NodeToIndex(first_order + k)
            window = node.order.window
            time_dim.CumulVar(index).SetRange(round(window.start_min), _HORIZON)
            time_dim.SetCumulVarSoftUpperBound(
                index, round(window.end_min), round(10 * weights.weight_delay)
            )
            routing.AddDisjunction([index], _DROP_PENALTY)

        demand = [0] * size
        for k, node in enumerate(nodes):
            demand[first_order + k] = round(node.kg)

        def demand_cb(from_index: int) -> int:
            return int(demand[manager.IndexToNode(from_index)])

        d_cb = routing.RegisterUnaryTransitCallback(demand_cb)
        routing.AddDimensionWithVehicleCapacity(
            d_cb, 0, [int(s.capacity_kg) for s in slots], True, "Capacity"
        )

        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        params.time_limit.FromMilliseconds(max(500, int(min(time_limit_s, 5.0) * 1000)))
        params.solution_limit = _SOLUTION_LIMIT

        assignment = routing.SolveWithParameters(params)
        elapsed = time.perf_counter() - started
        if assignment is None:
            return RoutingSolution(
                routes={s.vehicle.id: () for s in slots},
                unassigned={n.id: explain_unassigned(problem, n.id) for n in nodes},
                engine=ENGINE_NAME,
                elapsed_s=elapsed,
                note="OR-Tools no encontró solución dentro del límite.",
            )

        routes: dict[str, tuple[str, ...]] = {}
        assigned: set[str] = set()
        for v, slot in enumerate(slots):
            ids: list[str] = []
            index = assignment.Value(routing.NextVar(routing.Start(v)))
            while not routing.IsEnd(index):
                ids.append(nodes[manager.IndexToNode(index) - first_order].id)
                index = assignment.Value(routing.NextVar(index))
            routes[slot.vehicle.id] = tuple(ids)
            assigned.update(ids)
        unassigned = {
            n.id: explain_unassigned(problem, n.id) for n in nodes if n.id not in assigned
        }
        return RoutingSolution(routes, unassigned, ENGINE_NAME, elapsed)
