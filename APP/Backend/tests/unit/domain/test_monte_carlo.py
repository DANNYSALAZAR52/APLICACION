"""P6. Monte Carlo."""

from __future__ import annotations

import pytest

from fleetplanner.domain.capacity.monte_carlo import (
    MonteCarloConfig,
    MonteCarloCorridor,
    MonteCarloSimulator,
)
from fleetplanner.domain.shared.errors import InvalidValueError


def _corridors(std: float = 2.0) -> list[MonteCarloCorridor]:
    return [
        MonteCarloCorridor("R1", "X", mean_t=16.0, std_t=std, effective_t_per_day=8.0),
        MonteCarloCorridor("R2", "Y", mean_t=40.0, std_t=std * 2, effective_t_per_day=20.0),
    ]


def test_same_seed_reproduces_exactly() -> None:
    config = MonteCarloConfig(days=300, seed=123)
    a = MonteCarloSimulator(config).simulate(_corridors(), {"X": 2, "Y": 2})
    b = MonteCarloSimulator(config).simulate(_corridors(), {"X": 2, "Y": 2})
    assert a == b
    assert a.seed == 123


def test_different_seed_changes_the_draws() -> None:
    results = {
        MonteCarloSimulator(MonteCarloConfig(days=300, seed=s))
        .simulate(_corridors(6.0), {"X": 2, "Y": 2})
        .coverage_pct
        for s in range(1, 6)
    }
    assert len(results) > 1


def test_zero_variability_is_deterministic_by_hand() -> None:
    config = MonteCarloConfig(days=50, seed=1, cycle_cv=0.0)
    result = MonteCarloSimulator(config).simulate(
        [MonteCarloCorridor("R1", "X", 16.0, 0.0, 8.0)], {"X": 2}
    )
    # 16 t / 8 t por vehículo = 2 exactos todos los días
    assert (result.p50_total, result.p90_total, result.p95_total) == (2, 2, 2)
    assert result.coverage_pct == 100.0


def test_coverage_is_zero_when_fleet_is_always_short() -> None:
    config = MonteCarloConfig(days=50, seed=1, cycle_cv=0.0)
    result = MonteCarloSimulator(config).simulate(
        [MonteCarloCorridor("R1", "X", 16.0, 0.0, 8.0)], {"X": 1}
    )
    assert result.coverage_pct == 0.0
    assert result.current_total == 1


def test_percentiles_are_ordered_integers_and_never_negative() -> None:
    # Desviación enorme: una normal produciría demandas negativas; la lognormal no.
    config = MonteCarloConfig(days=500, seed=9, cycle_cv=0.5)
    result = MonteCarloSimulator(config).simulate(_corridors(std=40.0), {"X": 2, "Y": 2})
    assert 0 <= result.p50_total <= result.p90_total <= result.p95_total
    for per_type in result.percentiles_by_type.values():
        assert 0 <= per_type["p50"] <= per_type["p90"] <= per_type["p95"]
        assert all(isinstance(v, int) for v in per_type.values())


def test_zero_mean_demand_yields_zero_fleet() -> None:
    config = MonteCarloConfig(days=20, seed=1)
    result = MonteCarloSimulator(config).simulate(
        [MonteCarloCorridor("R1", "X", 0.0, 0.0, 8.0)], {"X": 0}
    )
    assert result.p95_total == 0
    assert result.coverage_pct == 100.0


def test_result_is_plausible_around_expected_value() -> None:
    # 16 t + variación pequeña sobre 8 t/vehículo ≈ 2 → resultados entre 2 y 3.
    result = MonteCarloSimulator(MonteCarloConfig(days=400, seed=5)).simulate(
        [MonteCarloCorridor("R1", "X", 16.0, 1.0, 8.0)], {"X": 3}
    )
    assert 2 <= result.p50_total <= 3
    assert 2 <= result.p95_total <= 4


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        MonteCarloConfig(days=0)
    with pytest.raises(InvalidValueError):
        MonteCarloConfig(cycle_cv=-0.1)
    with pytest.raises(InvalidValueError):
        MonteCarloCorridor("R1", "X", -1.0, 0.0, 8.0)
    with pytest.raises(InvalidValueError):
        MonteCarloCorridor("R1", "X", 1.0, 0.0, 0.0)
    with pytest.raises(InvalidValueError):
        MonteCarloSimulator(MonteCarloConfig()).simulate([], {})
