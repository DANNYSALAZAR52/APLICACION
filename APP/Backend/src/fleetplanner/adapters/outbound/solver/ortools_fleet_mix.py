"""Adaptador OR-Tools (MIP con SCIP) para `FleetMixSolverPort` (P7)."""

from __future__ import annotations

from ortools.linear_solver import pywraplp

from fleetplanner.domain.capacity.fleet_mix import (
    FleetMixProblem,
    FleetMixSolution,
    SolverStatus,
)


class OrToolsFleetMixSolver:
    """Resuelve el MIP del mix de flota y devuelve un estado veraz.

    * ``OPTIMAL`` solo cuando el solver demuestra optimalidad.
    * ``FEASIBLE`` si hay solución entera factible sin prueba de optimalidad (p. ej. por límite
      de tiempo): se devuelve como mejor solución encontrada, **nunca** etiquetada como óptima.
    * ``TIME_LIMIT`` si se agotó el tiempo sin encontrar ninguna solución.
    * ``INFEASIBLE`` si no hay combinación posible (incluye corredores sin tipo compatible).
    """

    def solve(self, problem: FleetMixProblem, time_limit_s: float) -> FleetMixSolution:
        unservable = problem.unservable_corridors()
        if unservable:
            return FleetMixSolution(
                SolverStatus.INFEASIBLE,
                message=(
                    "No hay ningún tipo de vehículo compatible para los corredores: "
                    + ", ".join(unservable)
                    + "."
                ),
            )

        solver = pywraplp.Solver.CreateSolver("SCIP")
        if solver is None:
            return FleetMixSolution(
                SolverStatus.ERROR, message="El solver SCIP no está disponible en OR-Tools."
            )
        solver.SetTimeLimit(max(1, int(time_limit_s * 1000)))
        infinity = solver.infinity()

        x = {(r, t): solver.IntVar(0, infinity, f"x[{r},{t}]") for (r, t) in problem.capacity_t}
        y = {t: solver.IntVar(0, infinity, f"y[{t}]") for t in problem.vehicle_types}

        for corridor in problem.corridors:
            terms = [
                problem.capacity_t[pair] * var for pair, var in x.items() if pair[0] == corridor
            ]
            if terms:
                solver.Add(sum(terms) >= problem.required_t[corridor])
        for vehicle_type, fleet_var in y.items():
            solver.Add(sum(var for pair, var in x.items() if pair[1] == vehicle_type) <= fleet_var)

        objective = solver.Objective()
        for vehicle_type, fleet_var in y.items():
            objective.SetCoefficient(fleet_var, problem.fixed_cost_per_day[vehicle_type])
        for pair, var in x.items():
            objective.SetCoefficient(var, problem.variable_cost_per_day[pair])
        objective.SetMinimization()

        raw_status = solver.Solve()
        return self._to_solution(solver, raw_status, x, y, time_limit_s)

    @staticmethod
    def _to_solution(
        solver: pywraplp.Solver,
        raw_status: int,
        x: dict[tuple[str, str], pywraplp.Variable],
        y: dict[str, pywraplp.Variable],
        time_limit_s: float,
    ) -> FleetMixSolution:
        if raw_status == pywraplp.Solver.INFEASIBLE:
            return FleetMixSolution(
                SolverStatus.INFEASIBLE, message="El modelo no tiene solución factible."
            )
        if raw_status == pywraplp.Solver.NOT_SOLVED:
            return FleetMixSolution(
                SolverStatus.TIME_LIMIT,
                message=f"Se agotó el límite de {time_limit_s:g} s sin encontrar solución.",
            )
        if raw_status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return FleetMixSolution(
                SolverStatus.ERROR, message=f"Estado del solver no reconocido: {raw_status}."
            )

        optimal = raw_status == pywraplp.Solver.OPTIMAL
        assignments = {
            pair: round(var.solution_value())
            for pair, var in x.items()
            if var.solution_value() > 0.5
        }
        fleet = {
            t: round(var.solution_value()) for t, var in y.items() if var.solution_value() > 0.5
        }
        return FleetMixSolution(
            status=SolverStatus.OPTIMAL if optimal else SolverStatus.FEASIBLE,
            assignments=assignments,
            fleet_by_type=fleet,
            total_cost_per_day=solver.Objective().Value(),
            message=""
            if optimal
            else (
                "Solución factible sin prueba de optimalidad (límite de "
                f"{time_limit_s:g} s o brecha no cerrada)."
            ),
        )
