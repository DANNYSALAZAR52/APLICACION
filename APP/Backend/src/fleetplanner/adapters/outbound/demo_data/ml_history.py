"""DEMO-ONLY: historia operativa sintética para entrenar los modelos de ML.

DATOS DE DEMOSTRACIÓN. Todo se genera con una semilla fija a partir de los corredores y clientes
de UNA empresa; no proviene de ninguna operación real. Los patrones que los modelos "descubren"
son los que se siembran aquí (``SEEDED_PATTERNS``), lo que permite probar que los encuentran.
Debe sustituirse por un lector de la historia real (ver ``docs/DEUDA_DEMO.md``).
"""

from __future__ import annotations

import math
import random
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from fleetplanner.adapters.outbound.demo_data.profiles import (
    DEMO_A_SLUG,
    DEMO_B_SLUG,
    capacity_reader_for_slug,
)
from fleetplanner.adapters.outbound.demo_data.routing_dataset import routing_reader_for_slug
from fleetplanner.domain.capacity.models import DemandSeries
from fleetplanner.domain.ml.calendar_co import is_holiday, is_quincena
from fleetplanner.domain.ml.records import OperationalHistory, ServiceVisit

SEEDED_PATTERNS: tuple[str, ...] = (
    "picos de demanda los lunes",
    "demanda más alta en los días de pago quincenal",
    "menor demanda en festivos",
    "un cliente con esperas largas los viernes entre las 10:00 y las 12:00",
    "mayor tráfico y más retrasos en horas pico (07:00–09:00 y 17:00–19:00)",
)

DEFAULT_END_DATE = date(2026, 10, 9)
DEFAULT_DAYS = 90

# Más demanda el lunes, menos el domingo (patrón sembrado).
_WEEKDAY_FACTOR = (1.18, 1.04, 1.0, 1.0, 1.04, 0.88, 0.45)
_QUINCENA_FACTOR = 1.12
_HOLIDAY_FACTOR = 0.6
_MISSING_RATE = 0.04
_FRIDAY_WAIT_FACTOR = 3.2
_RUSH_HOURS = frozenset({7, 8, 17, 18})


@dataclass(frozen=True)
class MlCorridor:
    code: str
    name: str
    mean_t: float


@dataclass(frozen=True)
class MlCustomer:
    code: str
    name: str
    window_start_min: int
    window_end_min: int


class DemoHistoryReader:
    """Implementa `HistoryReaderPort` con datos sintéticos deterministas de UNA empresa."""

    def __init__(
        self,
        corridors: Sequence[MlCorridor],
        customers: Sequence[MlCustomer],
        seed: int,
        days: int = DEFAULT_DAYS,
        end_date: date = DEFAULT_END_DATE,
    ) -> None:
        if not corridors or not customers:
            raise ValueError("Se necesitan corredores y clientes para generar historia.")
        self._corridors = tuple(corridors)
        self._customers = tuple(customers)
        self._seed = seed
        self._days = days
        self._end_date = end_date
        self._cached: OperationalHistory | None = None

    @property
    def seeded_customer(self) -> str:
        """Cliente con esperas largas los viernes 10:00–12:00 (determinista por semilla)."""
        return self._customers[self._seed % len(self._customers)].code

    def load(self) -> OperationalHistory:
        if self._cached is None:
            self._cached = self._generate()
        return self._cached

    # ------------------------------------------------------------------ generación
    def _generate(self) -> OperationalHistory:
        # Semilla fija y datos de demostración: no es criptografía (B311).
        rng = random.Random(self._seed)  # noqa: S311  # nosec B311
        first = self._end_date - timedelta(days=self._days - 1)
        days = [first + timedelta(days=i) for i in range(self._days)]

        demand: dict[str, DemandSeries] = {}
        for corridor in self._corridors:
            observations: dict[date, float] = {}
            for day in days:
                if rng.random() < _MISSING_RATE:
                    continue  # dato ausente: no es cero
                mean = corridor.mean_t * _WEEKDAY_FACTOR[day.weekday()]
                if is_quincena(day):
                    mean *= _QUINCENA_FACTOR
                if is_holiday(day):
                    mean *= _HOLIDAY_FACTOR
                value = rng.gauss(mean, corridor.mean_t * 0.07)
                observations[day] = round(max(value, 0.0), 2)
            demand[corridor.code] = DemandSeries(corridor.code, observations)

        base = {c.code: self._customer_profile(rng) for c in self._customers}
        corridor_of = {
            c.code: self._corridors[i % len(self._corridors)].code
            for i, c in enumerate(self._customers)
        }
        seeded = self.seeded_customer
        visits: list[ServiceVisit] = []
        for day in days:
            weekday = day.weekday()
            if weekday == 6 or is_holiday(day):
                continue  # domingos y festivos no hay reparto
            for customer in self._customers:
                profile = base[customer.code]
                width = customer.window_end_min - customer.window_start_min
                is_seeded = customer.code == seeded
                if is_seeded:
                    # El cliente sembrado siempre llega entre las 10:00 y las 12:00.
                    arrival = 10 * 60 + rng.uniform(0, 119)
                    width = 120
                else:
                    arrival = customer.window_start_min + rng.uniform(0, width * 0.8)
                hour = min(23, int(arrival // 60))
                traffic = 1.5 if hour in _RUSH_HOURS else 1.1
                traffic = max(1.0, rng.gauss(traffic, 0.1))
                order_kg = max(
                    20.0, rng.gauss(profile.kg * (1.15 if weekday == 0 else 1.0), profile.kg * 0.15)
                )
                service = max(
                    2.0,
                    rng.gauss(
                        profile.service_min * (1 + order_kg / 2500), profile.service_min * 0.12
                    ),
                )
                wait = max(0.0, rng.gauss(profile.wait_min, profile.wait_min * 0.25))
                if is_seeded and weekday == 4:
                    wait *= _FRIDAY_WAIT_FACTOR
                stops_remaining = rng.randint(0, 14)
                logit = (
                    -2.6
                    + 2.4 * (traffic - 1.0)
                    + 0.09 * stops_remaining
                    + profile.unreliable
                    + 0.0008 * order_kg
                    + (0.5 if hour in _RUSH_HOURS else 0.0)
                    + (0.4 if weekday == 4 else 0.0)
                )
                late = rng.random() < 1.0 / (1.0 + math.exp(-logit))
                visits.append(
                    ServiceVisit(
                        customer_code=customer.code,
                        corridor_code=corridor_of[customer.code],
                        day=day,
                        hour=hour,
                        wait_min=round(wait, 1),
                        service_min=round(service, 1),
                        order_kg=round(order_kg, 1),
                        window_width_min=max(30, int(width)),
                        traffic_factor=round(traffic, 3),
                        stops_remaining=stops_remaining,
                        late=late,
                    )
                )

        provenance = (
            f"DATOS SINTÉTICOS de demostración, semilla {self._seed}: {self._days} días "
            f"({first.isoformat()} a {self._end_date.isoformat()}), {len(self._corridors)} "
            f"corredores, {len(self._customers)} clientes y {len(visits)} visitas. Patrones "
            f"sembrados: {'; '.join(SEEDED_PATTERNS)}."
        )
        return OperationalHistory(
            demand=demand,
            visits=tuple(visits),
            provenance=provenance,
            seed=self._seed,
            corridor_names={c.code: c.name for c in self._corridors},
            customer_names={c.code: c.name for c in self._customers},
        )

    @staticmethod
    def _customer_profile(rng: random.Random) -> _CustomerProfile:
        return _CustomerProfile(
            kg=rng.uniform(90, 600),
            service_min=rng.uniform(8, 28),
            wait_min=rng.uniform(3, 14),
            unreliable=1.1 if rng.random() < 0.15 else 0.0,
        )


@dataclass(frozen=True)
class _CustomerProfile:
    kg: float
    service_min: float
    wait_min: float
    unreliable: float


def history_reader_for_slug(slug: str) -> DemoHistoryReader:
    """Historia de UNA empresa: sus corredores y clientes, su semilla. A y B son distintas."""
    capacity = capacity_reader_for_slug(slug).load()
    routing = routing_reader_for_slug(slug).read()
    corridors = []
    for corridor in capacity.corridors:
        values = list(capacity.demand[corridor.code].observations.values())
        mean_t = sum(values) / len(values) if values else 10.0
        corridors.append(MlCorridor(corridor.code, corridor.name, round(mean_t, 2)))
    customers = [
        MlCustomer(c.code, c.name, int(c.window.start_min), int(c.window.end_min))
        for c in routing.customers
    ]
    if slug == DEMO_A_SLUG:
        seed = 20261001
    elif slug == DEMO_B_SLUG:
        seed = 20261002
    else:
        seed = zlib.crc32(f"ml:{slug}".encode()) & 0x7FFFFFFF
    return DemoHistoryReader(corridors, customers, seed)


__all__ = [
    "SEEDED_PATTERNS",
    "DemoHistoryReader",
    "MlCorridor",
    "MlCustomer",
    "history_reader_for_slug",
]
