"""Ventanas horarias y formato de horas (minutos desde la medianoche del día operativo)."""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.domain.shared.errors import InvalidValueError

MINUTES_PER_DAY = 24 * 60


def format_clock(minutes: float) -> str:
    """Minutos desde la medianoche a ``HH:MM`` (redondeado al minuto más cercano)."""
    total = round(minutes)
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def parse_clock(text: str) -> int:
    """``HH:MM`` a minutos desde la medianoche. Lanza `InvalidValueError` si es inválida."""
    parts = text.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise InvalidValueError(f"La hora '{text}' no es válida; use el formato HH:MM.")
    hours, minutes = int(parts[0]), int(parts[1])
    if hours > 23 or minutes > 59:
        raise InvalidValueError(
            f"La hora '{text}' no es válida; use el formato HH:MM (00:00-23:59)."
        )
    return hours * 60 + minutes


def window_issues(start_min: float, end_min: float) -> list[str]:
    """Problemas de una ventana. No se aceptan ventanas que cruzan la medianoche (DOCS.MD §8)."""
    issues: list[str] = []
    if not 0 <= start_min < MINUTES_PER_DAY or not 0 < end_min <= MINUTES_PER_DAY:
        issues.append("Las horas de la ventana deben estar dentro del mismo día (00:00 a 24:00).")
    elif end_min <= start_min:
        issues.append(
            f"La ventana {format_clock(start_min)}–{format_clock(end_min)} no es válida: la hora "
            "final debe ser posterior a la inicial. Las ventanas que cruzan la medianoche no se "
            "admiten; divídalas en dos o corrija las horas."
        )
    return issues


@dataclass(frozen=True)
class TimeWindow:
    start_min: float
    end_min: float

    def __post_init__(self) -> None:
        issues = window_issues(self.start_min, self.end_min)
        if issues:
            raise InvalidValueError(" ".join(issues))

    def label(self) -> str:
        return f"{format_clock(self.start_min)}–{format_clock(self.end_min)}"
