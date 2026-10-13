"""P6. Simulación Monte Carlo de la flota requerida."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fleetplanner.domain.shared.errors import InvalidValueError
from fleetplanner.domain.shared.stats import ceil_fleet, percentile_nearest_rank


@dataclass(frozen=True)
class MonteCarloConfig:
    days: int = 1000
    seed: int = 20260101
    cycle_cv: float = 0.10

    def __post_init__(self) -> None:
        if self.days < 1:
            raise InvalidValueError("La simulación necesita al menos un día.")
        if self.cycle_cv < 0:
            raise InvalidValueError("El coeficiente de variación del ciclo no puede ser negativo.")


@dataclass(frozen=True)
class MonteCarloCorridor:
    """Entrada de un corredor: demanda histórica y capacidad efectiva (t/día/vehículo)."""

    code: str
    vehicle_type: str
    mean_t: float
    std_t: float
    effective_t_per_day: float

    def __post_init__(self) -> None:
        if self.mean_t < 0 or self.std_t < 0:
            raise InvalidValueError(
                f"La demanda promedio y la desviación del corredor {self.code} "
                "no pueden ser negativas."
            )
        if self.effective_t_per_day <= 0:
            raise InvalidValueError(
                f"La capacidad efectiva del corredor {self.code} debe ser mayor que cero."
            )


@dataclass(frozen=True)
class MonteCarloResult:
    seed: int
    days: int
    p50_total: int
    p90_total: int
    p95_total: int
    percentiles_by_type: Mapping[str, Mapping[str, int]]
    coverage_pct: float
    current_total: int


def _lognormal_params(mean: float, std: float) -> tuple[float, float]:
    """(mu, sigma) de una lognormal con la media y la desviación dadas."""
    sigma_sq = math.log(1.0 + (std / mean) ** 2)
    return math.log(mean) - sigma_sq / 2.0, math.sqrt(sigma_sq)


def _positive_draw(rng: random.Random, mean: float, std: float) -> float:
    """Valor estrictamente positivo con la media/desviación dadas.

    Se usa una lognormal en vez de una normal para no generar demandas ni factores de ciclo
    negativos. Si la media es 0 el resultado es 0; si la desviación es 0 es la media.
    """
    if mean <= 0:
        return 0.0
    if std <= 0:
        return mean
    mu, sigma = _lognormal_params(mean, std)
    return rng.lognormvariate(mu, sigma)


class MonteCarloSimulator:
    """Simula días de demanda y ciclo.

    Supuestos (ver ``docs/DECISIONES.md``): demanda y factor de ciclo se sortean de forma
    independiente por corredor y por día; el factor de ciclo tiene media 1 y CV configurable;
    ambos con distribución lognormal. Cada día la flota se redondea hacia arriba por tipo.
    Los percentiles usan rango más cercano para devolver siempre una flota observada.
    """

    def __init__(self, config: MonteCarloConfig) -> None:
        self._config = config

    def simulate(
        self, corridors: Sequence[MonteCarloCorridor], current_fleet: Mapping[str, int]
    ) -> MonteCarloResult:
        if not corridors:
            raise InvalidValueError("No hay corredores para simular.")
        # PRNG con semilla para reproducir la simulación; no se usa para seguridad (B311).
        rng = random.Random(self._config.seed)  # noqa: S311  # nosec B311
        types = sorted({c.vehicle_type for c in corridors})
        per_type: dict[str, list[int]] = {t: [] for t in types}
        totals: list[int] = []
        covered_days = 0

        for _ in range(self._config.days):
            fractional = dict.fromkeys(types, 0.0)
            for corridor in corridors:
                demand = _positive_draw(rng, corridor.mean_t, corridor.std_t)
                cycle_factor = _positive_draw(rng, 1.0, self._config.cycle_cv)
                fractional[corridor.vehicle_type] += (
                    demand * cycle_factor / corridor.effective_t_per_day
                )
            day_by_type = {t: ceil_fleet(f) for t, f in fractional.items()}
            for t, n in day_by_type.items():
                per_type[t].append(n)
            totals.append(sum(day_by_type.values()))
            if all(n <= current_fleet.get(t, 0) for t, n in day_by_type.items()):
                covered_days += 1

        def pcts(samples: list[int]) -> dict[str, int]:
            return {
                "p50": percentile_nearest_rank(samples, 0.50),
                "p90": percentile_nearest_rank(samples, 0.90),
                "p95": percentile_nearest_rank(samples, 0.95),
            }

        by_type = {t: pcts(samples) for t, samples in per_type.items()}
        total_p = pcts(totals)
        return MonteCarloResult(
            seed=self._config.seed,
            days=self._config.days,
            p50_total=total_p["p50"],
            p90_total=total_p["p90"],
            p95_total=total_p["p95"],
            percentiles_by_type=by_type,
            coverage_pct=100.0 * covered_days / self._config.days,
            current_total=sum(current_fleet.values()),
        )
