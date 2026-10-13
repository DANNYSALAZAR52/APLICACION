"""Ayudas para armar la aplicación completa en memoria dentro de las pruebas."""

from __future__ import annotations

from datetime import datetime

from fleetplanner.adapters.outbound.clock import BOGOTA_TZ, FixedClock
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.bootstrap.application import (
    Application,
    SeedCredential,
    build_application,
    seed_demo,
)
from fleetplanner.bootstrap.settings import load_settings

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


def make_app(
    clock: ClockPort | None = None,
) -> tuple[Application, list[SeedCredential], FixedClock]:
    fixed = clock if isinstance(clock, FixedClock) else FixedClock(NOW)
    application = build_application(
        load_settings({"JWT_SIGNING_KEY": SIGNING_KEY}), clock=fixed, hasher=FakeHasher()
    )
    return application, seed_demo(application), fixed


def password_of(credentials: list[SeedCredential], tenant: str, username: str) -> str:
    return next(c.password for c in credentials if c.tenant == tenant and c.username == username)
