"""Preparación común de datos para los casos de uso de capacidad (P1 + P2)."""

from __future__ import annotations

from fleetplanner.application.dto.capacity import (
    CapacityInputs,
    CapacityParameters,
    PreparedCapacity,
)
from fleetplanner.domain.capacity.design_demand import DesignDemand, DesignDemandCalculator
from fleetplanner.domain.capacity.effective_capacity import (
    EffectiveCapacity,
    EffectiveCapacityCalculator,
)
from fleetplanner.domain.capacity.models import Corridor, DemandSeries
from fleetplanner.domain.capacity.results import ALGORITHM_VERSION
from fleetplanner.domain.shared.errors import InsufficientDataError, InvalidValueError


def validate_master_data(inputs: CapacityInputs) -> None:
    """Falla con un mensaje claro si un corredor usa un tipo inexistente o no compatible."""
    for corridor in inputs.corridors:
        type_name = corridor.assigned_vehicle_type
        if type_name not in inputs.vehicle_types:
            raise InvalidValueError(
                f"El corredor {corridor.code} usa el tipo de vehículo '{type_name}', "
                "que no existe en el maestro de tipos."
            )
        if not inputs.compatibility.is_allowed(corridor.code, type_name):
            raise InvalidValueError(
                f"El corredor {corridor.code} tiene asignado el tipo '{type_name}', pero esa "
                "combinación no está marcada como compatible."
            )


def prepare_capacity(inputs: CapacityInputs) -> PreparedCapacity:
    """Calcula P1 y P2; excluye (con advertencia) los corredores sin datos suficientes."""
    validate_master_data(inputs)
    params = inputs.parameters
    design_calc = DesignDemandCalculator(params.design_percentile, params.window_days)
    capacity_calc = EffectiveCapacityCalculator(params.oee)

    valid: list[Corridor] = []
    design: dict[str, DesignDemand] = {}
    capacities: dict[str, EffectiveCapacity] = {}
    excluded: dict[str, str] = {}
    warnings: list[str] = []
    for corridor in inputs.corridors:
        series = inputs.demand.get(corridor.code, DemandSeries(corridor.code))
        try:
            design[corridor.code] = design_calc.calculate(series)
        except InsufficientDataError as error:
            excluded[corridor.code] = str(error)
            warnings.append(f"Corredor {corridor.code} excluido: {error}")
            continue
        capacities[corridor.code] = capacity_calc.calculate(
            corridor, inputs.vehicle_types[corridor.assigned_vehicle_type]
        )
        valid.append(corridor)
    if not valid:
        raise InsufficientDataError("Ningún corredor tiene datos suficientes para calcular.")
    return PreparedCapacity(valid, design, capacities, excluded, warnings)


def base_parameters(params: CapacityParameters, prepared: PreparedCapacity) -> dict[str, object]:
    """Parámetros efectivos y procedencia que se guardan con cada resultado."""
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "design_percentile": params.design_percentile.fraction,
        "reserve": params.reserve.fraction,
        "days_per_month": params.days_per_month,
        "window_days": params.window_days,
        "oee": params.oee.oee,
        "corridors_used": [c.code for c in prepared.corridors],
        "corridors_excluded": dict(prepared.excluded),
        "valid_days_by_corridor": {code: d.valid_days for code, d in prepared.design.items()},
    }
