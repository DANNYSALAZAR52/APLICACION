"""Festivos de Colombia (Ley Emiliani): calculados, sin tablas ni librerías externas."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def easter_sunday(year: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_offset) // 451
    month, day = divmod(h + weekday_offset - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _next_monday(day: date) -> date:
    """Si el festivo no cae en lunes se traslada al lunes siguiente."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


@lru_cache(maxsize=64)
def colombia_holidays(year: int) -> frozenset[date]:
    """Festivos nacionales del año: fijos, trasladables al lunes y los que dependen de la Pascua."""
    fixed = {
        date(year, 1, 1),
        date(year, 5, 1),
        date(year, 7, 20),
        date(year, 8, 7),
        date(year, 12, 8),
        date(year, 12, 25),
    }
    moved_to_monday = {
        date(year, 1, 6),  # Reyes Magos
        date(year, 3, 19),  # San José
        date(year, 6, 29),  # San Pedro y San Pablo
        date(year, 8, 15),  # Asunción
        date(year, 10, 12),  # Día de la Raza
        date(year, 11, 1),  # Todos los Santos
        date(year, 11, 11),  # Independencia de Cartagena
    }
    easter = easter_sunday(year)
    easter_based = {
        easter - timedelta(days=3),  # Jueves Santo
        easter - timedelta(days=2),  # Viernes Santo
        _next_monday(easter + timedelta(days=39)),  # Ascensión
        _next_monday(easter + timedelta(days=60)),  # Corpus Christi
        _next_monday(easter + timedelta(days=68)),  # Sagrado Corazón
    }
    return frozenset(fixed | {_next_monday(d) for d in moved_to_monday} | easter_based)


def is_holiday(day: date) -> bool:
    return day in colombia_holidays(day.year)


def is_quincena(day: date) -> bool:
    """Días de pago quincenal (14–16 y 29–2), cuando el patrón sembrado eleva la demanda."""
    return day.day in (14, 15, 16, 29, 30, 31, 1, 2)
