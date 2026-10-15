"""Puertos de salida del módulo de capacidad."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from fleetplanner.application.dto.capacity import CapacityInputs
from fleetplanner.application.dto.ml import ForecastComparison
from fleetplanner.domain.capacity.fleet_mix import FleetMixProblem, FleetMixSolution
from fleetplanner.domain.capacity.results import CapacityResult


class CapacityInputsReader(Protocol):
    """Lectura de maestros, parámetros e historial para una corrida (solo lectura)."""

    def load(self) -> CapacityInputs: ...


class CapacityResultWriter(Protocol):
    """Escritura de resultados de capacidad (append-only)."""

    def save_all(self, results: Sequence[CapacityResult]) -> None: ...


class CapacityResultReader(Protocol):
    """Lectura de resultados guardados (contrato separado del de escritura)."""

    def list_all(self) -> list[CapacityResult]: ...


class FleetMixSolverPort(Protocol):
    """Solver MIP del mix de flota. El estado devuelto debe ser veraz."""

    def solve(self, problem: FleetMixProblem, time_limit_s: float) -> FleetMixSolution: ...


class MlForecastSource(Protocol):
    """Pronóstico de demanda con ML frente al percentil histórico (opcional)."""

    def forecast_comparison(self) -> list[ForecastComparison]: ...
