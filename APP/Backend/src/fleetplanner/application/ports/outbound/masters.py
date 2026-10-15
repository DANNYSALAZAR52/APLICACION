"""Puerto del almacén de maestros y parámetros de UNA empresa."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

Row = dict[str, object]


@dataclass(frozen=True)
class ChangeRecord:
    """Historial inmutable de cambios: quién, cuándo, qué y el valor anterior."""

    id: str
    at: datetime
    actor: str
    entity: str
    key: str
    action: str  # create | update | delete | csv | parameter
    before: Row | None
    after: Row | None
    valid_from: date | None = None
    note: str = ""


@dataclass(frozen=True)
class ParameterVersion:
    """Una versión de un parámetro. Las anteriores nunca se modifican ni se borran."""

    key: str
    value: object
    valid_from: date
    set_by: str
    set_at: datetime
    note: str = ""


class MasterDataStorePort(Protocol):
    def rows(self, entity: str) -> list[Row]: ...

    def get(self, entity: str, key: str) -> Row | None: ...

    def put(self, entity: str, key: str, values: Row) -> None: ...

    def remove(self, entity: str, key: str) -> Row | None: ...

    def parameter_versions(self, key: str) -> list[ParameterVersion]: ...

    def add_parameter_version(self, version: ParameterVersion) -> None: ...

    def append_history(self, record: ChangeRecord) -> None: ...

    def history(self, limit: int = 100, entity: str | None = None) -> list[ChangeRecord]:
        """Más recientes primero."""
        ...

    def next_id(self, prefix: str) -> str: ...
