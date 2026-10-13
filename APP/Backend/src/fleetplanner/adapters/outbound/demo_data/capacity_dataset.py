"""DEMO-ONLY: conjunto de datos sintético para el módulo de capacidad.

DATOS DE DEMOSTRACIÓN. Valores inventados y reproducibles con semilla; no provienen de ninguna
planilla ni de operación real, y no reproducen las cifras de referencia de ``DOCS.MD`` §10.
Debe sustituirse por un lector real de maestros y demanda (ver ``docs/DEUDA_DEMO.md``).
"""

from __future__ import annotations

import random
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

DEMO_LABEL = "DATOS DE DEMOSTRACIÓN"

_VEHICLE_TYPES = [
    VehicleType("turbo", 4.5, 20, 8, 4_500_000, 1_100, 450_000),
    VehicleType("sencillo", 8.0, 35, 14, 6_800_000, 1_600, 650_000),
    VehicleType("doble_troque", 17.0, 55, 24, 9_500_000, 2_300, 2_200_000),
    VehicleType("tractomula", 32.0, 80, 34, 14_500_000, 3_400, 5_500_000),
]


def _corridor(
    code: str,
    name: str,
    vehicle_type: str,
    km: float,
    speed: float,
    hours: float,
    loading: float,
    dock: float,
    stops: int,
    min_stop: float,
    customer_wait: float,
    fill: float,
    backhaul: float,
) -> Corridor:
    return Corridor(
        code=code,
        name=name,
        assigned_vehicle_type=vehicle_type,
        one_way_km=km,
        average_speed_kmh=speed,
        operating_hours=hours,
        loading_h=loading,
        dock_wait_h=dock,
        stops=stops,
        minutes_per_stop=min_stop,
        customer_wait_h=customer_wait,
        fill=Percentage.from_percent(fill),
        backhaul=Percentage.from_percent(backhaul),
    )


# (corredor, demanda media t/día)
_CORRIDORS: list[tuple[Corridor, float]] = [
    (
        _corridor(
            "URB-N", "Distribución urbana norte", "turbo", 35, 25, 10, 0.75, 0.5, 8, 12, 0.5, 85, 0
        ),
        30,
    ),
    (
        _corridor(
            "URB-S", "Distribución urbana sur", "turbo", 40, 22, 10, 0.75, 0.5, 9, 12, 0.5, 85, 0
        ),
        25,
    ),
    (
        _corridor(
            "URB-O",
            "Distribución urbana occidente",
            "sencillo",
            30,
            28,
            10,
            0.75,
            0.5,
            6,
            15,
            0.5,
            85,
            0,
        ),
        32,
    ),
    (
        _corridor(
            "SAB-01", "Sabana de Bogotá", "sencillo", 60, 40, 10, 1.0, 0.5, 3, 20, 0.5, 90, 10
        ),
        25,
    ),
    (
        _corridor(
            "INT-IBG", "Bogotá–Ibagué", "doble_troque", 200, 50, 18, 1.5, 1.0, 1, 30, 1.5, 90, 30
        ),
        70,
    ),
    (
        _corridor(
            "INT-VVC",
            "Bogotá–Villavicencio",
            "doble_troque",
            120,
            45,
            16,
            1.5,
            1.0,
            1,
            30,
            1.0,
            90,
            25,
        ),
        50,
    ),
    (
        _corridor(
            "TRK-MED", "Bogotá–Medellín", "tractomula", 420, 55, 20, 2.0, 1.0, 1, 60, 2.0, 92, 40
        ),
        95,
    ),
    (
        _corridor(
            "TRK-CTG", "Bogotá–Cartagena", "tractomula", 1000, 60, 20, 2.0, 1.0, 1, 60, 2.0, 90, 35
        ),
        55,
    ),
]

_COMPATIBILITY = [
    ("URB-N", "turbo"),
    ("URB-N", "sencillo"),
    ("URB-S", "turbo"),
    ("URB-S", "sencillo"),
    ("URB-O", "turbo"),
    ("URB-O", "sencillo"),
    ("SAB-01", "turbo"),
    ("SAB-01", "sencillo"),
    ("SAB-01", "doble_troque"),
    ("INT-IBG", "doble_troque"),
    ("INT-IBG", "tractomula"),
    ("INT-VVC", "doble_troque"),
    ("INT-VVC", "tractomula"),
    ("TRK-MED", "doble_troque"),
    ("TRK-MED", "tractomula"),
    ("TRK-CTG", "tractomula"),
]

# Lunes más cargado (patrón sembrado), domingo bajo.
_WEEKDAY_FACTOR = [1.15, 1.05, 1.0, 1.0, 1.05, 0.9, 0.55]


class DemoCapacityInputsReader:
    """Implementa `CapacityInputsReader` con datos sintéticos deterministas (DEMO-ONLY)."""

    def __init__(
        self,
        seed: int = 20261009,
        history_days: int = 75,
        end_date: date = date(2026, 10, 9),
        missing_rate: float = 0.06,
        demand_scale: float = 1.0,
        current_fleet: dict[str, int] | None = None,
    ) -> None:
        self._current_fleet = current_fleet or {
            "turbo": 15,
            "sencillo": 10,
            "doble_troque": 8,
            "tractomula": 12,
        }
        self._seed = seed
        self._history_days = history_days
        self._end_date = end_date
        self._missing_rate = missing_rate
        self._scale = demand_scale

    def load(self) -> CapacityInputs:
        # Datos sintéticos reproducibles con semilla; no se usa para seguridad (B311).
        rng = random.Random(self._seed)  # noqa: S311  # nosec B311
        demand: dict[str, DemandSeries] = {}
        for corridor, mean_t in _CORRIDORS:
            observations: dict[date, float] = {}
            for offset in range(self._history_days):
                day = self._end_date - timedelta(days=offset)
                # Un día sin observación es dato ausente: no se registra (no es cero).
                if rng.random() < self._missing_rate:
                    continue
                factor = _WEEKDAY_FACTOR[day.weekday()]
                value = rng.gauss(mean_t * self._scale * factor, mean_t * self._scale * 0.12)
                observations[day] = round(max(value, 0.0), 2)
            demand[corridor.code] = DemandSeries(corridor.code, observations)

        parameters = CapacityParameters(
            design_percentile=Percentage.from_percent(90),
            reserve=Percentage.from_percent(8),
            days_per_month=26,
            window_days=60,
            oee=OeeFactors(
                Percentage.from_percent(90),
                Percentage.from_percent(85),
                Percentage.from_percent(95),
            ),
            lean_targets=LeanTargets(
                dock_wait_reduction=Percentage.from_percent(40),
                loading_reduction=Percentage.from_percent(25),
                stop_time_reduction=Percentage.from_percent(20),
                customer_wait_reduction=Percentage.from_percent(30),
                heijunka_buffer=Percentage.from_percent(10),
                target_oee=Percentage.from_percent(80),
            ),
            monte_carlo=MonteCarloConfig(days=1000, seed=self._seed, cycle_cv=0.10),
            solver_time_limit_s=30.0,
            base_year=self._end_date.year,
        )
        scenarios = [
            GrowthScenario(
                "base",
                cagr=0.06,
                route_adjustments={"URB-N": 0.02},
                new_volume_t={"URB-O": 10.0},
                entry_year=2028,
            ),
            GrowthScenario(
                "optimista",
                cagr=0.09,
                route_adjustments={"URB-N": 0.02, "TRK-MED": 0.02},
                new_volume_t={"URB-O": 20.0, "TRK-MED": 25.0},
                entry_year=2027,
            ),
            GrowthScenario("pesimista", cagr=0.02, entry_year=2030),
        ]
        return CapacityInputs(
            vehicle_types={v.name: v for v in _VEHICLE_TYPES},
            corridors=[c for c, _ in _CORRIDORS],
            compatibility=CompatibilityMatrix.of(_COMPATIBILITY),
            demand=demand,
            current_fleet=dict(self._current_fleet),
            parameters=parameters,
            scenarios=scenarios,
        )
