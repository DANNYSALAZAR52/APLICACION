"""Puerto de exportación a hojas de cálculo (el formato concreto lo decide el adaptador)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Sheet:
    """Una hoja con encabezado y filas. El texto se neutraliza (fórmulas) al exportar."""

    name: str
    header: Sequence[str]
    rows: Sequence[Sequence[object]]
    notes: Sequence[str] = field(default_factory=tuple)  # líneas sobre el encabezado


class SpreadsheetExporterPort(Protocol):
    def to_xlsx(self, sheets: Sequence[Sheet]) -> bytes: ...

    def to_csv(self, sheet: Sheet) -> bytes:
        """CSV con BOM UTF-8 (Excel respeta los acentos) y fórmulas neutralizadas."""
        ...
