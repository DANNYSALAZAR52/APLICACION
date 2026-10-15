"""DEMO-ONLY: reloj acelerado que se puede pausar, acelerar, adelantar y reiniciar."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from fleetplanner.application.ports.outbound.clock import SimulationStatus


class SimulatedClock:
    """Implementa `SimulationClockPort`. ``speed`` = minutos simulados por minuto real.

    Con la velocidad por defecto (30) una jornada de 12 h dura 24 min reales. Para pruebas se
    inyecta ``monotonic`` y el tiempo avanza solo cuando la prueba lo decide.
    """

    def __init__(
        self,
        start: datetime,
        speed: float = 30.0,
        paused: bool = True,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if start.tzinfo is None:
            raise ValueError("El reloj necesita un instante con zona horaria.")
        self._lock = threading.RLock()
        self._monotonic = monotonic
        self._speed = speed
        self._paused = paused
        self._sim_anchor = start
        self._real_anchor = monotonic()

    def _now_unlocked(self) -> datetime:
        if self._paused:
            return self._sim_anchor
        elapsed_real_min = (self._monotonic() - self._real_anchor) / 60.0
        return self._sim_anchor + timedelta(minutes=elapsed_real_min * self._speed)

    def _rebase(self) -> None:
        self._sim_anchor = self._now_unlocked()
        self._real_anchor = self._monotonic()

    def now(self) -> datetime:
        with self._lock:
            return self._now_unlocked()

    def status(self) -> SimulationStatus:
        with self._lock:
            return SimulationStatus(self._now_unlocked(), self._speed, self._paused)

    def pause(self) -> None:
        with self._lock:
            self._rebase()
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._rebase()
            self._paused = False

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("La velocidad debe ser positiva.")
        with self._lock:
            self._rebase()
            self._speed = speed

    def advance(self, minutes: float) -> None:
        with self._lock:
            self._rebase()
            self._sim_anchor += timedelta(minutes=minutes)

    def reset(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("El reloj necesita un instante con zona horaria.")
        with self._lock:
            self._sim_anchor = start
            self._real_anchor = self._monotonic()
            self._paused = True
