"""P5. Flota Lean."""

from __future__ import annotations

import pytest

from builders import make_corridor, make_lean_targets, make_type, pct
from fleetplanner.domain.capacity.effective_capacity import trip_cycle_hours
from fleetplanner.domain.capacity.lean import LeanFleetCalculator, LeanTargets, standard_corridor
from fleetplanner.domain.shared.errors import InvalidValueError


def test_standard_cycle_applies_reduction_targets() -> None:
    std = standard_corridor(make_corridor(), make_lean_targets())
    # carga 0.5 + muelle 0.25 + tránsito 2 + paradas 1 + espera cliente 0.25
    assert trip_cycle_hours(std) == pytest.approx(4.0)


def test_lean_fleet_and_indicators_by_hand() -> None:
    result = LeanFleetCalculator(make_lean_targets()).calculate(
        [make_corridor()], {"X": make_type()}, {"R1": 16.0}
    )
    corridor = result.by_corridor[0]
    # viajes = 16·1.1 / (10·0.8) = 2.2 ; flota = 2.2·4 / (10·0.8) = 1.1 → 2
    assert corridor.trips_required == pytest.approx(2.2)
    assert corridor.fleet_fractional == pytest.approx(1.1)
    assert result.required_by_type == {"X": 2}
    assert result.total_required == 2
    # valor agregado = tránsito cargado (1 h) / ciclo 4 h
    assert corridor.value_added_pct == pytest.approx(0.25)
    # muda = (0.25 + 0.25 + retorno vacío 1) / 4
    assert corridor.waste_pct == pytest.approx(0.375)
    # takt = 600 min / 2.2 viajes
    assert corridor.takt_min == pytest.approx(600 / 2.2)


def test_backhaul_raises_value_added_and_lowers_waste() -> None:
    calc = LeanFleetCalculator(make_lean_targets())
    base = calc.calculate([make_corridor()], {"X": make_type()}, {"R1": 16.0}).by_corridor[0]
    with_backhaul = calc.calculate(
        [make_corridor(backhaul_pct=50)], {"X": make_type()}, {"R1": 16.0}
    ).by_corridor[0]
    assert with_backhaul.value_added_pct > base.value_added_pct
    assert with_backhaul.waste_pct < base.waste_pct


def test_zero_demand_gives_zero_fleet_and_infinite_takt() -> None:
    result = LeanFleetCalculator(make_lean_targets()).calculate(
        [make_corridor()], {"X": make_type()}, {"R1": 0.0}
    )
    assert result.required_by_type == {"X": 0}
    assert result.by_corridor[0].takt_min == float("inf")


def test_missing_mean_demand_is_error() -> None:
    with pytest.raises(InvalidValueError, match="no se asume cero"):
        LeanFleetCalculator(make_lean_targets()).calculate(
            [make_corridor()], {"X": make_type()}, {}
        )


def test_zero_target_oee_is_rejected() -> None:
    with pytest.raises(InvalidValueError):
        LeanTargets(pct(0), pct(0), pct(0), pct(0), pct(10), pct(0))
