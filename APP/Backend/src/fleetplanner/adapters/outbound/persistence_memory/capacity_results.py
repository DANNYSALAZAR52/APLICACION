"""DEMO-ONLY: repositorio en memoria de resultados de capacidad (append-only)."""

from __future__ import annotations

from collections.abc import Sequence

from fleetplanner.domain.capacity.results import CapacityResult


class InMemoryCapacityResultRepository:
    """Implementa `CapacityResultWriter` y `CapacityResultReader`.

    Los resultados no se modifican ni se borran: cada corrida agrega filas nuevas.
    """

    def __init__(self) -> None:
        self._rows: list[CapacityResult] = []

    def save_all(self, results: Sequence[CapacityResult]) -> None:
        self._rows.extend(results)

    def list_all(self) -> list[CapacityResult]:
        return list(self._rows)
