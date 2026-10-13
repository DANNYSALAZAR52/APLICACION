"""Implementaciones de `ClockPort`.

La hora operacional de la demo es la de Bogotá (UTC−5, sin horario de verano).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

BOGOTA_TZ = timezone(timedelta(hours=-5), "America/Bogota")


class SystemClock:
    """Reloj real."""

    def now(self) -> datetime:
        return datetime.now(UTC).astimezone(BOGOTA_TZ)


class FixedClock:
    """Reloj controlable para pruebas y simulaciones; no espera tiempo real."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("El reloj necesita un instante con zona horaria.")
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def advance(self, delta: timedelta) -> None:
        self._instant += delta
