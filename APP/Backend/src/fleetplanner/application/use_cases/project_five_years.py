"""Caso de uso ProjectFiveYears (P4)."""

from __future__ import annotations

from fleetplanner.application.dto.capacity import CapacityInputs, PreparedCapacity
from fleetplanner.application.ports.outbound.capacity import (
    CapacityInputsReader,
    CapacityResultWriter,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.use_cases.capacity_common import base_parameters, prepare_capacity
from fleetplanner.domain.capacity.fleet_requirement import FleetRequirementCalculator
from fleetplanner.domain.capacity.projection import FiveYearProjector, ScenarioProjection
from fleetplanner.domain.capacity.results import (
    ALGORITHM_VERSION,
    CapacityMethod,
    CapacityResult,
)


class ProjectFiveYears:
    def __init__(
        self,
        reader: CapacityInputsReader,
        writer: CapacityResultWriter,
        clock: ClockPort,
        horizon_years: int = 5,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._clock = clock
        self._horizon = horizon_years

    def execute(self) -> list[ScenarioProjection]:
        inputs = self._reader.load()
        return self.run(inputs, prepare_capacity(inputs))

    def run(self, inputs: CapacityInputs, prepared: PreparedCapacity) -> list[ScenarioProjection]:
        params = inputs.parameters
        run_at = self._clock.now()
        base_year = params.base_year if params.base_year is not None else run_at.year
        projector = FiveYearProjector(FleetRequirementCalculator(params.reserve), self._horizon)
        common = base_parameters(params, prepared)

        projections: list[ScenarioProjection] = []
        results: list[CapacityResult] = []
        for scenario in inputs.scenarios:
            projection = projector.project(
                scenario,
                base_year,
                prepared.corridors,
                prepared.design_t,
                prepared.capacities,
                inputs.current_fleet,
            )
            projections.append(projection)
            for year in projection.years:
                for vehicle_type, fleet in year.requirement.required_by_type.items():
                    results.append(
                        CapacityResult(
                            run_at,
                            CapacityMethod.PROJECTION,
                            vehicle_type,
                            year.year,
                            fleet,
                            ALGORITHM_VERSION,
                            {
                                **common,
                                "scenario": scenario.name,
                                "cagr": scenario.cagr,
                                "route_adjustments": dict(scenario.route_adjustments),
                                "new_volume_t": dict(scenario.new_volume_t),
                                "entry_year": scenario.entry_year,
                                "base_year": base_year,
                            },
                        )
                    )
        self._writer.save_all(results)
        return projections
