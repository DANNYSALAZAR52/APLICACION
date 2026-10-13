"""Puerto de reloj: permite inyectar tiempo real o simulado."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime:
        """Instante actual con zona horaria (nunca naïve)."""
        ...
