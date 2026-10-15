"""Ayudas para armar la aplicación completa en memoria dentro de las pruebas."""

from __future__ import annotations

from datetime import datetime

from fleetplanner.adapters.outbound.clock import BOGOTA_TZ, FixedClock
from fleetplanner.adapters.outbound.demo_data.ml_history import (
    DemoHistoryReader,
    MlCorridor,
    MlCustomer,
)
from fleetplanner.adapters.outbound.demo_data.routing_dataset import (
    DemoRoutingInputsReader,
    RoutingProfile,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.bootstrap.application import (
    Application,
    SeedCredential,
    build_application,
    seed_demo,
)
from fleetplanner.bootstrap.settings import load_settings
from routing_flow_helpers import HeuristicSolver

NOW = datetime(2026, 10, 13, 8, 0, tzinfo=BOGOTA_TZ)
SIGNING_KEY = "clave-de-pruebas-solo-para-tests-0123456789"
A = "empresa-demo-a"
B = "empresa-demo-b"


class FakeHasher:
    """Hasher rápido y determinista, solo para pruebas que no verifican Argon2."""

    def hash(self, password: str) -> str:
        return f"fake${password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"fake${password}"

    def verify_dummy(self, password: str) -> None:
        return None


def _small_routing_reader(slug: str) -> DemoRoutingInputsReader:
    """Datos de ruteo pequeños y distintos por empresa: mantienen rápidas las pruebas HTTP."""
    size = RoutingProfile(seed=11, customers=8, active_vehicles=2)
    if slug == B:
        size = RoutingProfile(seed=29, customers=5, active_vehicles=2)
    return DemoRoutingInputsReader(size)


def _small_history_reader(slug: str) -> DemoHistoryReader:
    """Historia de ML pequeña (más rápida) y distinta por empresa."""
    corridors = [
        MlCorridor("C1", "Corredor uno", 20.0),
        MlCorridor("C2", "Corredor dos", 35.0),
        MlCorridor("C3", "Corredor tres", 12.0),
    ]
    count = 12 if slug == A else 10
    customers = [
        MlCustomer(f"K-{i:02d}", f"Cliente {i:02d}", 420 + 20 * (i % 6), 540 + 20 * (i % 6))
        for i in range(1, count + 1)
    ]
    return DemoHistoryReader(corridors, customers, seed=5 if slug == A else 9, days=70)


def make_app(
    clock: ClockPort | None = None,
    ml: bool = False,
) -> tuple[Application, list[SeedCredential], FixedClock]:
    fixed = clock if isinstance(clock, FixedClock) else FixedClock(NOW)
    application = build_application(
        load_settings({"JWT_SIGNING_KEY": SIGNING_KEY}),
        clock=fixed,
        hasher=FakeHasher(),
        routing_solver=HeuristicSolver(),
        routing_reader_factory=_small_routing_reader,
        # Entrenar scikit-learn tarda segundos: solo las pruebas de ML lo activan.
        ml_reader_factory=_small_history_reader if ml else (lambda slug: None),
    )
    return application, seed_demo(application), fixed


def password_of(credentials: list[SeedCredential], tenant: str, username: str) -> str:
    return next(c.password for c in credentials if c.tenant == tenant and c.username == username)
