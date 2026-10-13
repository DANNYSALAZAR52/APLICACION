"""Porcentaje normalizado a fracción.

La entrada de usuario llega en 0–100 %; internamente todo se maneja como fracción 0–1.
"""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.domain.shared.errors import InvalidValueError


@dataclass(frozen=True)
class Percentage:
    """Fracción entre 0 y 1 (ambos incluidos)."""

    fraction: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.fraction <= 1.0:
            raise InvalidValueError(
                "El porcentaje debe estar entre 0 % y 100 % "
                f"(se recibió {self.fraction * 100:g} %)."
            )

    @classmethod
    def from_percent(cls, percent: float) -> Percentage:
        """Crea el valor desde una entrada 0–100."""
        if not 0.0 <= percent <= 100.0:
            raise InvalidValueError(
                f"El porcentaje debe estar entre 0 y 100 (se recibió {percent:g})."
            )
        return cls(percent / 100.0)

    @classmethod
    def from_fraction(cls, fraction: float) -> Percentage:
        """Crea el valor desde una fracción 0–1."""
        return cls(fraction)

    @property
    def percent(self) -> float:
        return self.fraction * 100.0
