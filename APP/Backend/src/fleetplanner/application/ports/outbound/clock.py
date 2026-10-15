"""Puerto de reloj: permite inyectar tiempo real o simulado."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime:
        """Instante actual con zona horaria (nunca naïve)."""
        ...


@dataclass(frozen=True)
class SimulationStatus:
    now: datetime
    speed: float  # minutos simulados por minuto real
    paused: bool


class SimulationClockPort(ClockPort, Protocol):
    """Reloj acelerado de la demo (DEMO-ONLY): se puede pausar, acelerar y reiniciar."""

    def status(self) -> SimulationStatus: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...

    def set_speed(self, speed: float) -> None: ...

    def advance(self, minutes: float) -> None: ...

    def reset(self, start: datetime) -> None: ...
