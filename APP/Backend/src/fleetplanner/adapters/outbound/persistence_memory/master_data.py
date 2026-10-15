"""DEMO-ONLY: almacén de maestros y parámetros de UNA empresa en memoria."""

from __future__ import annotations

import copy
import threading
from collections import deque

from fleetplanner.application.ports.outbound.masters import ChangeRecord, ParameterVersion, Row


class InMemoryMasterDataStore:
    """Cada empresa tiene su propia instancia. El historial y las versiones son append-only."""

    def __init__(self, history_capacity: int = 20000) -> None:
        self._lock = threading.RLock()
        self._rows: dict[str, dict[str, Row]] = {}
        self._versions: dict[str, list[ParameterVersion]] = {}
        self._history: deque[ChangeRecord] = deque(maxlen=history_capacity)
        self._counters: dict[str, int] = {}

    def rows(self, entity: str) -> list[Row]:
        with self._lock:
            return [copy.deepcopy(r) for r in self._rows.get(entity, {}).values()]

    def get(self, entity: str, key: str) -> Row | None:
        with self._lock:
            row = self._rows.get(entity, {}).get(key)
            return copy.deepcopy(row) if row is not None else None

    def put(self, entity: str, key: str, values: Row) -> None:
        with self._lock:
            self._rows.setdefault(entity, {})[key] = copy.deepcopy(values)

    def remove(self, entity: str, key: str) -> Row | None:
        with self._lock:
            return self._rows.get(entity, {}).pop(key, None)

    def parameter_versions(self, key: str) -> list[ParameterVersion]:
        with self._lock:
            return list(self._versions.get(key, []))

    def add_parameter_version(self, version: ParameterVersion) -> None:
        with self._lock:
            self._versions.setdefault(version.key, []).append(version)

    def append_history(self, record: ChangeRecord) -> None:
        with self._lock:
            self._history.append(record)

    def history(self, limit: int = 100, entity: str | None = None) -> list[ChangeRecord]:
        with self._lock:
            items = [r for r in self._history if entity is None or r.entity == entity]
        return list(reversed(items))[:limit]

    def next_id(self, prefix: str) -> str:
        with self._lock:
            n = self._counters.get(prefix, 0) + 1
            self._counters[prefix] = n
            return f"{prefix}-{n:05d}"
