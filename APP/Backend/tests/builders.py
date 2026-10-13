"""Constructores de datos de prueba con valores calculables a mano.

Caso base (corredor R1, tipo X):

* ciclo = 1 + 0,5 + 2·(30/30) + 4·15/60 + 0,5 = 5 h  →  viajes/día = 10/5 = 2
* OEE = 1 · 0,5 · 1 = 0,5
* capacidad efectiva = 10 t · 0,8 · 2 · 0,5 = 8 t/día por vehículo
"""

from __future__ import annotations

from datetime import date, timedelta

from fleetplanner.application.dto.capacity import CapacityInputs, CapacityParameters
from fleetplanner.domain.capacity.lean import LeanTargets
from fleetplanner.domain.capacity.models import (
    CompatibilityMatrix,
    Corridor,
    DemandSeries,
    OeeFactors,
    VehicleType,
)
from fleetplanner.domain.capacity.monte_carlo import MonteCarloConfig
from fleetplanner.domain.capacity.projection import GrowthScenario
from fleetplanner.domain.shared.percentage import Percentage


def pct(value: float) -> Percentage:
    return Percentage.from_percent(value)


def make_oee(utilization_pct: float = 50.0) -> OeeFactors:
    return OeeFactors(pct(100), pct(utilization_pct), pct(100))


def make_type(
    name: str = "X",
    capacity_t: float = 10.0,
    fixed_month: float = 2_600_000,
    var_km: float = 5.0,
    third_party: float = 150.0,
) -> VehicleType:
    return VehicleType(name, capacity_t, 40.0, 10, fixed_month, var_km, third_party)


def make_corridor(
    code: str = "R1",
    vehicle_type: str = "X",
    km: float = 30.0,
    speed: float = 30.0,
    hours: float = 10.0,
    loading: float = 1.0,
    dock: float = 0.5,
    stops: int = 4,
    minutes_per_stop: float = 15.0,
    customer_wait: float = 0.5,
    fill_pct: float = 80.0,
    backhaul_pct: float = 0.0,
) -> Corridor:
    return Corridor(
        code=code,
        name=f"Corredor {code}",
        assigned_vehicle_type=vehicle_type,
        one_way_km=km,
        average_speed_kmh=speed,
        operating_hours=hours,
        loading_h=loading,
        dock_wait_h=dock,
        stops=stops,
        minutes_per_stop=minutes_per_stop,
        customer_wait_h=customer_wait,
        fill=pct(fill_pct),
        backhaul=pct(backhaul_pct),
    )


def make_series(
    code: str, values: list[float | None], end: date = date(2026, 10, 9)
) -> DemandSeries:
    """Serie diaria que termina en ``end``; ``None`` es un día sin observación (ausente)."""
    start = end - timedelta(days=len(values) - 1)
    observations = {start + timedelta(days=i): v for i, v in enumerate(values) if v is not None}
    return DemandSeries(code, observations)


def make_lean_targets() -> LeanTargets:
    return LeanTargets(
        dock_wait_reduction=pct(50),
        loading_reduction=pct(50),
        stop_time_reduction=pct(0),
        customer_wait_reduction=pct(50),
        heijunka_buffer=pct(10),
        target_oee=pct(80),
    )


def make_parameters(**overrides: object) -> CapacityParameters:
    values: dict[str, object] = {
        "design_percentile": pct(90),
        "reserve": pct(8),
        "days_per_month": 26,
        "window_days": 60,
        "oee": make_oee(),
        "lean_targets": make_lean_targets(),
        "monte_carlo": MonteCarloConfig(days=200, seed=7, cycle_cv=0.1),
        "solver_time_limit_s": 5.0,
        "base_year": 2026,
    }
    values.update(overrides)
    return CapacityParameters(**values)  # type: ignore[arg-type]


def make_inputs(
    demand: dict[str, list[float | None]] | None = None,
    current_fleet: dict[str, int] | None = None,
) -> CapacityInputs:
    """Dos corredores (R1→X, R2→Y) con demanda alterna 19/21 y 9,5/10,5 t (media 20 y 10)."""
    pattern = demand or {
        "R1": [19.0, 21.0] * 15,
        "R2": [9.5, 10.5] * 15,
    }
    return CapacityInputs(
        vehicle_types={"X": make_type("X", 10.0), "Y": make_type("Y", 20.0, 5_200_000, 8.0, 300.0)},
        corridors=[make_corridor("R1", "X"), make_corridor("R2", "Y")],
        compatibility=CompatibilityMatrix.of([("R1", "X"), ("R1", "Y"), ("R2", "Y")]),
        demand={code: make_series(code, values) for code, values in pattern.items()},
        current_fleet=current_fleet or {"X": 3, "Y": 1},
        parameters=make_parameters(),
        scenarios=[
            GrowthScenario("base", cagr=0.06),
            GrowthScenario("optimista", cagr=0.10),
        ],
    )
