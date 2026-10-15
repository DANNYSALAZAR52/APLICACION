"""Esquemas de maestros: campos tipados y validación con mensajes en español.

Un maestro se describe con datos (`EntitySpec`) para que el backend valide, la API publique el
esquema y la interfaz dibuje formularios y tablas sin código por entidad.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from fleetplanner.domain.routing.time_window import format_clock, parse_clock, window_issues
from fleetplanner.domain.shared.errors import InvalidValueError

# Texto que una hoja de cálculo podría interpretar como fórmula (OWASP: inyección en CSV/Excel).
FORMULA_START = re.compile(r"^[=+\-@\t\r]")


def neutralize_cell(value: object) -> object:
    """Texto que una hoja de cálculo tomaría por fórmula se antepone con una comilla (OWASP).

    Los números reales no se tocan: -3 sigue siendo el número -3.
    """
    if isinstance(value, str) and FORMULA_START.match(value):
        return "'" + value
    return value


class FieldType(StrEnum):
    TEXT = "text"
    INT = "int"
    NUMBER = "number"
    PERCENT = "percent"  # se escribe como 0–100 y se guarda así
    TIME = "time"  # HH:MM
    DATE = "date"  # AAAA-MM-DD
    SELECT = "select"
    BOOL = "bool"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    type: FieldType
    required: bool = True
    min: float | None = None
    max: float | None = None
    exclusive_min: bool = False  # min no incluido (por ejemplo, "mayor que cero")
    max_length: int = 120
    options: tuple[tuple[str, str], ...] = ()  # (valor, etiqueta) para SELECT estático
    options_from: str | None = None  # búsqueda dinámica: vehicle_types | corridors | customers
    help: str = ""
    unit: str = ""


@dataclass(frozen=True)
class EntitySpec:
    name: str
    label: str
    plural: str
    description: str
    fields: tuple[FieldSpec, ...]
    key_fields: tuple[str, ...]
    csv: bool = True

    def field(self, name: str) -> FieldSpec:
        return next(f for f in self.fields if f.name == name)

    def key_of(self, values: Mapping[str, object]) -> str:
        return "|".join(str(values[k]) for k in self.key_fields)

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)


@dataclass(frozen=True)
class FieldIssue:
    field: str
    message: str


def _es(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _range_issue(spec: FieldSpec, number: float) -> str | None:
    if spec.min is not None:
        if spec.exclusive_min and number <= spec.min:
            return f"{spec.label} debe ser mayor que {_es(spec.min)}."
        if not spec.exclusive_min and number < spec.min:
            return f"{spec.label} no puede ser menor que {_es(spec.min)}."
    if spec.max is not None and number > spec.max:
        return f"{spec.label} no puede ser mayor que {_es(spec.max)}."
    return None


def coerce(spec: FieldSpec, raw: object) -> tuple[object | None, str | None]:
    """Convierte y valida un valor. Devuelve (valor normalizado, mensaje de error)."""
    empty = raw is None or (isinstance(raw, str) and not raw.strip())
    if empty:
        if spec.required:
            return None, f"{spec.label} es obligatorio."
        return None, None
    try:
        return _coerce_present(spec, raw)
    except InvalidValueError as error:
        return None, str(error)
    except (ValueError, OverflowError):
        # Nunca se muestra el mensaje interno de Python (llegaría en inglés al usuario).
        numeric = spec.type in (FieldType.INT, FieldType.NUMBER, FieldType.PERCENT)
        return (
            None,
            f"{spec.label} debe ser un número." if numeric else f"{spec.label} no es válido.",
        )


def _coerce_present(spec: FieldSpec, raw: object) -> tuple[object | None, str | None]:
    kind = spec.type
    if kind is FieldType.TEXT:
        text = " ".join(str(raw).split())
        if len(text) > spec.max_length:
            return None, f"{spec.label} admite como máximo {spec.max_length} caracteres."
        if FORMULA_START.match(text):
            return None, (
                f"{spec.label} no puede empezar con = + - @ (podría interpretarse como fórmula)."
            )
        return text, None
    if kind is FieldType.BOOL:
        if isinstance(raw, bool):
            return raw, None
        text = str(raw).strip().lower()
        if text in {"1", "true", "si", "sí", "verdadero", "x"}:
            return True, None
        if text in {"0", "false", "no", "falso"}:
            return False, None
        return None, f"{spec.label} debe ser sí o no."
    if kind is FieldType.SELECT:
        text = str(raw).strip()
        allowed = {v for v, _ in spec.options}
        if spec.options and text not in allowed:
            return None, f"{spec.label} debe ser uno de: {', '.join(sorted(allowed))}."
        return text, None
    if kind is FieldType.TIME:
        try:
            return format_clock(parse_clock(str(raw))), None
        except InvalidValueError:
            return None, f"{spec.label} debe tener el formato HH:MM (por ejemplo, 08:30)."
    if kind is FieldType.DATE:
        try:
            return date.fromisoformat(str(raw).strip()).isoformat(), None
        except ValueError:
            return None, f"{spec.label} debe tener el formato AAAA-MM-DD."
    # numéricos
    if isinstance(raw, bool):
        return None, f"{spec.label} debe ser un número."
    candidate: float | str = (
        str(raw).strip().replace(",", ".") if isinstance(raw, str) else float(str(raw))
    )
    number = float(candidate)
    if not math.isfinite(number):
        return None, f"{spec.label} debe ser un número."
    if kind is FieldType.INT:
        if number != int(number):
            return None, f"{spec.label} debe ser un número entero."
        whole = int(number)
        issue = _range_issue(spec, whole)
        return (None, issue) if issue else (whole, None)
    issue = _range_issue(spec, number)
    return (None, issue) if issue else (number, None)


def coerce_row(
    entity: EntitySpec, raw: Mapping[str, object]
) -> tuple[dict[str, object], list[FieldIssue]]:
    """Valida una fila completa y reporta TODOS los problemas a la vez."""
    values: dict[str, object] = {}
    issues: list[FieldIssue] = []
    unknown = sorted(set(raw) - set(entity.column_names))
    for name in unknown:
        issues.append(FieldIssue(name, f"El campo «{name}» no existe en {entity.plural}."))
    for spec in entity.fields:
        value, error = coerce(spec, raw.get(spec.name))
        if error:
            issues.append(FieldIssue(spec.name, error))
        elif value is not None:
            values[spec.name] = value
    # Regla entre campos: la ventana final debe ser posterior a la inicial. Se revisa en el mismo
    # paso que lo demás para que quien corrige vea TODOS los problemas de una vez (criterio 11).
    if "window_start" in values and "window_end" in values:
        start, end = (
            parse_clock(str(values["window_start"])),
            parse_clock(str(values["window_end"])),
        )
        issues.extend(FieldIssue("window_end", m) for m in window_issues(start, end))
    return values, issues


def issues_text(issues: list[FieldIssue]) -> str:
    return " ".join(i.message for i in issues)
