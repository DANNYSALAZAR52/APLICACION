"""Caso de uso RunCapacityAnalysis: balance (P3), Lean (P5), propio vs tercero (P8) y KPI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fleetplanner.application.dto.capacity import (
    BalanceReport,
    CapacityInputs,
    PreparedCapacity,
)
from fleetplanner.application.ports.outbound.capacity import (
    CapacityInputsReader,
    CapacityResultWriter,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.use_cases.capacity_common import base_parameters, prepare_capacity
from fleetplanner.domain.capacity.effective_capacity import vehicle_daily_km
from fleetplanner.domain.capacity.fleet_requirement import FleetRequirementCalculator
from fleetplanner.domain.capacity.kpis import CapacityKpiCalculator
from fleetplanner.domain.capacity.lean import LeanFleetCalculator, LeanResult
from fleetplanner.domain.capacity.own_vs_third import (
    OwnFleetCosts,
    OwnVsThirdPartyAnalyzer,
    OwnVsThirdResult,
    daily_required_vehicles,
)
from fleetplanner.domain.capacity.results import (
    ALGORITHM_VERSION,
    CapacityMethod,
    CapacityResult,
)


@dataclass(frozen=True)
class CapacityAnalysis:
    balance: BalanceReport
    lean: LeanResult
    own_vs_third: OwnVsThirdResult


class RunCapacityAnalysis:
    """Calcula y guarda los métodos deterministas de capacidad sobre los datos vigentes."""

    def __init__(
        self,
        reader: CapacityInputsReader,
        writer: CapacityResultWriter,
        clock: ClockPort,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._clock = clock

    def execute(self) -> CapacityAnalysis:
        inputs = self._reader.load()
        return self.run(inputs, prepare_capacity(inputs))

    def run(self, inputs: CapacityInputs, prepared: PreparedCapacity) -> CapacityAnalysis:
        params = inputs.parameters
        run_at = self._clock.now()
        common = base_parameters(params, prepared)

        # P3: balance
        requirement = FleetRequirementCalculator(params.reserve).calculate(
            prepared.corridors, prepared.design_t, prepared.capacities, inputs.current_fleet
        )
        kpis = CapacityKpiCalculator(params.days_per_month).calculate(
            prepared.corridors,
            inputs.vehicle_types,
            prepared.design_t,
            prepared.capacities,
            requirement,
        )
        balance = BalanceReport(requirement, prepared.design, prepared.capacities, kpis)

        # P5: Lean
        lean = LeanFleetCalculator(params.lean_targets).calculate(
            prepared.corridors, inputs.vehicle_types, prepared.mean_t
        )

        # P8: propio vs tercero
        window = _common_window(prepared)
        daily_r = daily_required_vehicles(
            prepared.corridors, prepared.capacities, inputs.demand, window
        )
        costs = {
            name: OwnFleetCosts(
                fixed_per_day=vt.fixed_cost_per_day(params.days_per_month),
                variable_per_used_vehicle_day=_variable_cost_per_vehicle_day(
                    inputs, prepared, name
                ),
                third_party_per_day=vt.third_party_daily_rate,
            )
            for name, vt in inputs.vehicle_types.items()
            if name in daily_r
        }
        own_vs_third = OwnVsThirdPartyAnalyzer().analyze(daily_r, costs)

        results = [
            CapacityResult(
                run_at,
                CapacityMethod.BALANCE,
                vehicle_type,
                None,
                fleet,
                ALGORITHM_VERSION,
                {**common, "fractional": requirement.fractional_by_type[vehicle_type]},
            )
            for vehicle_type, fleet in requirement.required_by_type.items()
        ]
        results += [
            CapacityResult(
                run_at,
                CapacityMethod.LEAN,
                vehicle_type,
                None,
                fleet,
                ALGORITHM_VERSION,
                {**common, "heijunka_buffer": params.lean_targets.heijunka_buffer.fraction},
            )
            for vehicle_type, fleet in lean.required_by_type.items()
        ]
        results += [
            CapacityResult(
                run_at,
                CapacityMethod.OWN_VS_THIRD_PARTY,
                vehicle_type,
                None,
                item.optimal_own,
                ALGORITHM_VERSION,
                {
                    **common,
                    "days_used": item.days_used,
                    "optimal_cost_per_day": item.optimal_cost_per_day,
                },
            )
            for vehicle_type, item in own_vs_third.by_type.items()
        ]
        self._writer.save_all(results)
        return CapacityAnalysis(balance, lean, own_vs_third)


def _common_window(prepared: PreparedCapacity) -> tuple[date, date]:
    """Ventana común: intersección de las ventanas de P1 de todos los corredores.

    Si las ventanas no se solapan, el inicio queda después del fin y no hay días completos.
    """
    start = max(d.window_start for d in prepared.design.values())
    end = min(d.window_end for d in prepared.design.values())
    return start, end


def _variable_cost_per_vehicle_day(
    inputs: CapacityInputs, prepared: PreparedCapacity, vehicle_type: str
) -> float:
    """Costo variable diario promedio de un vehículo del tipo, ponderado por flota fraccional."""
    cost_per_km = inputs.vehicle_types[vehicle_type].variable_cost_per_km
    weighted = 0.0
    weight = 0.0
    for corridor in prepared.corridors:
        if corridor.assigned_vehicle_type != vehicle_type:
            continue
        capacity = prepared.capacities[corridor.code]
        share = prepared.design[corridor.code].design_t / capacity.effective_t_per_day
        weighted += share * cost_per_km * vehicle_daily_km(corridor, capacity)
        weight += share
    return weighted / weight if weight > 0 else 0.0
