"""P1. Demanda de diseño por corredor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from fleetplanner.domain.capacity.models import DemandSeries
from fleetplanner.domain.shared.errors import InsufficientDataError
from fleetplanner.domain.shared.percentage import Percentage
from fleetplanner.domain.shared.stats import mean, percentile_linear, sample_std


@dataclass(frozen=True)
class DesignDemand:
    """Resultado de P1 para un corredor (toneladas por día)."""

    corridor_code: str
    mean_t: float
    std_t: float
    design_t: float
    percentile: Percentage
    valid_days: int
    window_start: date
    window_end: date


class DesignDemandCalculator:
    """Calcula promedio, desviación y percentil de diseño sobre una ventana de días.

    La ventana son los ``window_days`` días calendario que terminan en la última fecha con
    observación del corredor. Los días sin observación quedan fuera del cálculo (no son cero)
    y se informa cuántos días válidos entraron.
    """

    def __init__(
        self,
        percentile: Percentage | None = None,
        window_days: int = 60,
        min_valid_days: int = 2,
    ) -> None:
        if window_days < 1:
            raise ValueError("La ventana debe tener al menos un día.")
        if min_valid_days < 2:
            raise ValueError("Se requieren al menos 2 días válidos para estimar la desviación.")
        self._percentile = percentile if percentile is not None else Percentage(0.90)
        self._window_days = window_days
        self._min_valid_days = min_valid_days

    def calculate(self, series: DemandSeries) -> DesignDemand:
        end = series.last_date()
        if end is None:
            raise InsufficientDataError(
                f"El corredor {series.corridor_code} no tiene demanda registrada."
            )
        start = end - timedelta(days=self._window_days - 1)
        values = [t for day, t in series.observations.items() if start <= day <= end]
        if len(values) < self._min_valid_days:
            raise InsufficientDataError(
                f"El corredor {series.corridor_code} tiene {len(values)} día(s) con datos en la "
                f"ventana de {self._window_days} días; se requieren al menos "
                f"{self._min_valid_days}."
            )
        return DesignDemand(
            corridor_code=series.corridor_code,
            mean_t=mean(values),
            std_t=sample_std(values),
            design_t=percentile_linear(values, self._percentile.fraction),
            percentile=self._percentile,
            valid_days=len(values),
            window_start=start,
            window_end=end,
        )

    def window_for(self, series: DemandSeries) -> tuple[date, date] | None:
        """Ventana [inicio, fin] aplicada a una serie, o ``None`` si está vacía."""
        end = series.last_date()
        if end is None:
            return None
        return end - timedelta(days=self._window_days - 1), end
