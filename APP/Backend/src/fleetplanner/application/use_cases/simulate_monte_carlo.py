"""Caso de uso SimulateMonteCarlo (P6)."""

from __future__ import annotations

from fleetplanner.application.dto.capacity import CapacityInputs, PreparedCapacity
from fleetplanner.application.ports.outbound.capacity import (
    CapacityInputsReader,
    CapacityResultWriter,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.use_cases.capacity_common import base_parameters, prepare_capacity
from fleetplanner.domain.capacity.monte_carlo import (
    MonteCarloCorridor,
    MonteCarloResult,
    MonteCarloSimulator,
)
from fleetplanner.domain.capacity.results import (
    ALGORITHM_VERSION,
    CapacityMethod,
    CapacityResult,
)


class SimulateMonteCarlo:
    def __init__(
        self,
        reader: CapacityInputsReader,
        writer: CapacityResultWriter,
        clock: ClockPort,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._clock = clock

    def execute(self) -> MonteCarloResult:
        inputs = self._reader.load()
        return self.run(inputs, prepare_capacity(inputs))

    def run(self, inputs: CapacityInputs, prepared: PreparedCapacity) -> MonteCarloResult:
        params = inputs.parameters
        corridors = [
            MonteCarloCorridor(
                code=c.code,
                vehicle_type=c.assigned_vehicle_type,
                mean_t=prepared.design[c.code].mean_t,
                std_t=prepared.design[c.code].std_t,
                effective_t_per_day=prepared.capacities[c.code].effective_t_per_day,
            )
            for c in prepared.corridors
        ]
        result = MonteCarloSimulator(params.monte_carlo).simulate(corridors, inputs.current_fleet)

        run_at = self._clock.now()
        common = base_parameters(params, prepared)
        self._writer.save_all(
            [
                CapacityResult(
                    run_at,
                    CapacityMethod.MONTE_CARLO,
                    vehicle_type,
                    None,
                    percentiles["p95"],
                    ALGORITHM_VERSION,
                    {
                        **common,
                        "seed": result.seed,
                        "days": result.days,
                        "cycle_cv": params.monte_carlo.cycle_cv,
                        "percentiles": dict(percentiles),
                        "coverage_pct_total": result.coverage_pct,
                    },
                )
                for vehicle_type, percentiles in result.percentiles_by_type.items()
            ]
        )
        return result
