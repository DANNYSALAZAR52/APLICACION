"""Vistas de salida del módulo de maestros (no son entidades de dominio)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from fleetplanner.application.ports.outbound.masters import ChangeRecord, Row
from fleetplanner.domain.masters.catalog import ParameterSpec
from fleetplanner.domain.masters.schema import EntitySpec


@dataclass(frozen=True)
class Lookups:
    """Listas para los campos de selección dinámica de la interfaz."""

    vehicle_types: tuple[str, ...]
    corridors: tuple[tuple[str, str], ...]
    customers: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SchemaView:
    entities: tuple[EntitySpec, ...]
    parameters: tuple[ParameterSpec, ...]
    lookups: Lookups


@dataclass(frozen=True)
class Listing:
    entity: str
    total: int
    rows: tuple[Row, ...]
    truncated: bool


@dataclass(frozen=True)
class CsvIssue:
    row: int  # fila del archivo (la 1 es el encabezado); 0 = problema general
    column: str
    message: str


@dataclass(frozen=True)
class CsvPreview:
    entity: str
    rows_total: int
    rows_valid: int
    to_create: int
    to_update: int
    errors: tuple[CsvIssue, ...]
    errors_truncated: bool
    sample: tuple[Row, ...]

    @property
    def can_apply(self) -> bool:
        return not self.errors and self.rows_total > 0


@dataclass(frozen=True)
class CsvApplyResult:
    entity: str
    created: int
    updated: int


@dataclass(frozen=True)
class ParameterVersionView:
    value: object
    valid_from: date
    set_by: str
    set_at: datetime
    note: str
    in_force: bool  # es la versión que se está usando hoy
    scheduled: bool  # vigencia futura


@dataclass(frozen=True)
class ParameterView:
    spec: ParameterSpec
    value: object  # valor vigente hoy
    valid_from: date
    versions: tuple[ParameterVersionView, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HistoryView:
    records: tuple[ChangeRecord, ...]
