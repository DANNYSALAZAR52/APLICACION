"""P3. Flota requerida por balance."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from fleetplanner.domain.capacity.effective_capacity import EffectiveCapacity
from fleetplanner.domain.capacity.models import Corridor
from fleetplanner.domain.shared.errors import InvalidValueError
from fleetplanner.domain.shared.percentage import Percentage
from fleetplanner.domain.shared.stats import ceil_fleet


@dataclass(frozen=True)
class FleetRequirement:
    """Flota requerida por tipo.

    ``fractional_by_corridor`` es la flota sin reserva ni redondeo. ``fractional_by_type`` suma
    esas fracciones por tipo. ``required_by_type`` aplica la reserva y redondea hacia arriba
    **una sola vez**, sobre la suma por tipo.
    """

    fractional_by_corridor: Mapping[str, float]
    fractional_by_type: Mapping[str, float]
    required_by_type: Mapping[str, int]
    current_by_type: Mapping[str, int]
    reserve: Percentage

    @property
    def total_required(self) -> int:
        return sum(self.required_by_type.values())

    @property
    def total_current(self) -> int:
        return sum(self.current_by_type.values())

    @property
    def gap_by_type(self) -> dict[str, int]:
        """Brecha = flota actual − requerida. Un valor negativo es déficit."""
        types = set(self.required_by_type) | set(self.current_by_type)
        return {
            t: self.current_by_type.get(t, 0) - self.required_by_type.get(t, 0)
            for t in sorted(types)
        }

    @property
    def total_gap(self) -> int:
        return self.total_current - self.total_required


class FleetRequirementCalculator:
    """vehículos_ruta = demanda_ruta / capacidad_efectiva; suma por tipo, × (1+reserva), techo.

    Orden de redondeo (decisión documentada): se suman las fracciones por tipo, se multiplica por
    (1 + reserva) y se redondea hacia arriba una sola vez. Redondear antes por corredor inflaría
    el total de forma injustificada.
    """

    def __init__(self, reserve: Percentage) -> None:
        self._reserve = reserve

    def calculate(
        self,
        corridors: list[Corridor],
        demand_t_per_day: Mapping[str, float],
        capacities: Mapping[str, EffectiveCapacity],
        current_fleet: Mapping[str, int],
    ) -> FleetRequirement:
        fractional_by_corridor: dict[str, float] = {}
        fractional_by_type: dict[str, float] = {}
        for corridor in corridors:
            if corridor.code not in demand_t_per_day:
                raise InvalidValueError(
                    f"Falta la demanda del corredor {corridor.code}; no se asume cero."
                )
            capacity = capacities[corridor.code]
            if capacity.effective_t_per_day <= 0:
                raise InvalidValueError(
                    f"La capacidad efectiva del corredor {corridor.code} no es positiva."
                )
            vehicles = demand_t_per_day[corridor.code] / capacity.effective_t_per_day
            fractional_by_corridor[corridor.code] = vehicles
            fractional_by_type[corridor.assigned_vehicle_type] = (
                fractional_by_type.get(corridor.assigned_vehicle_type, 0.0) + vehicles
            )
        required = {
            vehicle_type: ceil_fleet(fraction * (1.0 + self._reserve.fraction))
            for vehicle_type, fraction in fractional_by_type.items()
        }
        return FleetRequirement(
            fractional_by_corridor=fractional_by_corridor,
            fractional_by_type=fractional_by_type,
            required_by_type=required,
            current_by_type=dict(current_fleet),
            reserve=self._reserve,
        )
