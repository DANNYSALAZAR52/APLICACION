"""Caso de uso BuildCapacityDashboard (P9): consolida todos los métodos con una sola lectura."""

from __future__ import annotations

from fleetplanner.application.dto.capacity import CapacityDashboard
from fleetplanner.application.dto.ml import ForecastComparison
from fleetplanner.application.ports.outbound.capacity import CapacityInputsReader, MlForecastSource
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.use_cases.capacity_common import prepare_capacity
from fleetplanner.application.use_cases.optimize_fleet_mix import OptimizeFleetMix
from fleetplanner.application.use_cases.project_five_years import ProjectFiveYears
from fleetplanner.application.use_cases.run_capacity_analysis import (
    CapacityAnalysis,
    RunCapacityAnalysis,
)
from fleetplanner.application.use_cases.simulate_monte_carlo import SimulateMonteCarlo
from fleetplanner.domain.capacity.fleet_mix import FleetMixSolution, SolverStatus
from fleetplanner.domain.capacity.monte_carlo import MonteCarloResult
from fleetplanner.domain.capacity.projection import ScenarioProjection
from fleetplanner.domain.capacity.results import ALGORITHM_VERSION
from fleetplanner.domain.shared.errors import DomainError


class BuildCapacityDashboard:
    def __init__(
        self,
        reader: CapacityInputsReader,
        analysis: RunCapacityAnalysis,
        projection: ProjectFiveYears,
        monte_carlo: SimulateMonteCarlo,
        mix: OptimizeFleetMix,
        clock: ClockPort,
        ml: MlForecastSource | None = None,
    ) -> None:
        self._reader = reader
        self._ml = ml
        self._analysis = analysis
        self._projection = projection
        self._monte_carlo = monte_carlo
        self._mix = mix
        self._clock = clock

    def execute(self) -> CapacityDashboard:
        inputs = self._reader.load()
        prepared = prepare_capacity(inputs)
        analysis = self._analysis.run(inputs, prepared)
        projections = self._projection.run(inputs, prepared)
        monte_carlo = self._monte_carlo.run(inputs, prepared)
        mix = self._mix.run(inputs, prepared)

        run_at = self._clock.now()
        base_year = (
            inputs.parameters.base_year if inputs.parameters.base_year is not None else run_at.year
        )
        warnings = list(prepared.warnings)
        if not analysis.own_vs_third.by_type:
            warnings.append(
                "Propio vs. tercero: no hay días con datos completos en todos los corredores."
            )
        if mix.status is not SolverStatus.OPTIMAL:
            warnings.append(
                f"El optimizador del mix terminó con estado '{mix.status.value}', no 'óptimo'. "
                f"{mix.message}".strip()
            )
        ml_forecast: list[ForecastComparison] = []
        if self._ml is not None:
            try:
                ml_forecast = self._ml.forecast_comparison()
            except DomainError as error:
                warnings.append(
                    f"Pronóstico de demanda con ML no disponible ({error}); "
                    "se usa el percentil histórico."
                )
        else:
            warnings.append(
                "Pronóstico de demanda con ML no disponible en esta configuración; "
                "se usa el percentil histórico."
            )
        return CapacityDashboard(
            run_at=run_at,
            algorithm_version=ALGORITHM_VERSION,
            base_year=base_year,
            balance=analysis.balance,
            lean=analysis.lean,
            monte_carlo=monte_carlo,
            mix=mix,
            own_vs_third=analysis.own_vs_third,
            projections=projections,
            findings=_findings(analysis, monte_carlo, mix, projections),
            parameters=inputs.parameters,
            corridor_names={c.code: c.name for c in inputs.corridors},
            warnings=warnings,
            ml_forecast_available=bool(ml_forecast),
            ml_forecast=ml_forecast,
        )


def _findings(
    analysis: CapacityAnalysis,
    monte_carlo: MonteCarloResult,
    mix: FleetMixSolution,
    projections: list[ScenarioProjection],
) -> list[str]:
    """Hallazgos orientativos en español, derivados solo de los resultados calculados."""
    findings: list[str] = []
    requirement = analysis.balance.requirement
    findings.append(
        f"Balance: se requieren {requirement.total_required} vehículos frente a "
        f"{requirement.total_current} en la flota actual."
    )
    for vehicle_type, gap in requirement.gap_by_type.items():
        if gap < 0:
            findings.append(
                f"Déficit actual de {-gap} vehículo(s) tipo {vehicle_type} "
                f"(requeridos {requirement.required_by_type.get(vehicle_type, 0)}, "
                f"disponibles {requirement.current_by_type.get(vehicle_type, 0)})."
            )
    if analysis.lean.total_required < requirement.total_required:
        findings.append(
            f"Con las metas Lean la flota requerida bajaría de {requirement.total_required} a "
            f"{analysis.lean.total_required} vehículos."
        )
    findings.append(
        f"Monte Carlo ({monte_carlo.days} días, semilla {monte_carlo.seed}): P95 = "
        f"{monte_carlo.p95_total} vehículos; la flota actual cubre el "
        f"{monte_carlo.coverage_pct:.1f} % de los días simulados."
    )
    if mix.has_solution:
        qualifier = "óptimo" if mix.status is SolverStatus.OPTIMAL else f"({mix.status.value})"
        findings.append(f"Mix de flota {qualifier}: {mix.total_vehicles} vehículos.")
    if analysis.own_vs_third.by_type:
        findings.append(
            f"Propio vs. tercero: la flota propia de menor costo suma "
            f"{analysis.own_vs_third.total_own} vehículos."
        )
    for projection in projections:
        if projection.first_deficit_year is None:
            findings.append(
                f"Escenario '{projection.scenario}': la flota actual alcanza "
                "durante todo el horizonte."
            )
        else:
            findings.append(
                f"Escenario '{projection.scenario}': la flota actual deja de alcanzar en "
                f"{projection.first_deficit_year}."
            )
    findings.append(
        "Estos resultados son recomendaciones de apoyo; no disparan compras ni contratos."
    )
    return findings
