"""Caso de uso OptimizeFleetMix (P7)."""

from __future__ import annotations

from fleetplanner.application.dto.capacity import CapacityInputs, PreparedCapacity
from fleetplanner.application.ports.outbound.capacity import (
    CapacityInputsReader,
    CapacityResultWriter,
    FleetMixSolverPort,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.use_cases.capacity_common import base_parameters, prepare_capacity
from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacityCalculator
from fleetplanner.domain.capacity.fleet_mix import FleetMixProblemBuilder, FleetMixSolution
from fleetplanner.domain.capacity.results import (
    ALGORITHM_VERSION,
    CapacityMethod,
    CapacityResult,
)


class OptimizeFleetMix:
    def __init__(
        self,
        reader: CapacityInputsReader,
        solver: FleetMixSolverPort,
        writer: CapacityResultWriter,
        clock: ClockPort,
    ) -> None:
        self._reader = reader
        self._solver = solver
        self._writer = writer
        self._clock = clock

    def execute(self) -> FleetMixSolution:
        inputs = self._reader.load()
        return self.run(inputs, prepare_capacity(inputs))

    def run(self, inputs: CapacityInputs, prepared: PreparedCapacity) -> FleetMixSolution:
        params = inputs.parameters
        problem = FleetMixProblemBuilder(
            EffectiveCapacityCalculator(params.oee), params.reserve, params.days_per_month
        ).build(prepared.corridors, inputs.vehicle_types, inputs.compatibility, prepared.design_t)
        solution = self._solver.solve(problem, params.solver_time_limit_s)

        # Solo se guarda una solución utilizable, siempre con su estado real (nunca "óptima" falsa).
        if solution.has_solution:
            run_at = self._clock.now()
            common = base_parameters(params, prepared)
            self._writer.save_all(
                [
                    CapacityResult(
                        run_at,
                        CapacityMethod.MIX_OPTIMIZATION,
                        vehicle_type,
                        None,
                        fleet,
                        ALGORITHM_VERSION,
                        {
                            **common,
                            "solver_status": solution.status.value,
                            "total_cost_per_day": solution.total_cost_per_day,
                            "time_limit_s": params.solver_time_limit_s,
                            "assignments": {
                                f"{r}|{t}": n
                                for (r, t), n in solution.assignments.items()
                                if t == vehicle_type
                            },
                        },
                    )
                    for vehicle_type, fleet in solution.fleet_by_type.items()
                ]
            )
        return solution
