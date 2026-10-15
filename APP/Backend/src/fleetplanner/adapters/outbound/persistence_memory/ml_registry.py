"""DEMO-ONLY: registro de modelos en memoria, uno por empresa, con verificación de hash.

La instancia pertenece a UN tenant (se crea en su espacio de trabajo): no tiene operación alguna
que reciba un tenant ni un nombre de empresa, por lo que no puede devolver artefactos ajenos.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
from dataclasses import dataclass
from datetime import datetime

from fleetplanner.application.dto.ml import LoadedModel, TrainedArtifact
from fleetplanner.domain.ml.results import ModelMetadata
from fleetplanner.domain.shared.errors import ArtifactIntegrityError


@dataclass
class _Record:
    metadata: ModelMetadata
    payload: bytes
    importances: dict[str, float]
    notes: tuple[str, ...]


class InMemoryModelRegistry:
    """Implementa `ModelRegistryPort`."""

    def __init__(self) -> None:
        self._records: dict[str, list[_Record]] = {}
        self._lock = threading.RLock()

    def register(
        self, name: str, artifact: TrainedArtifact, trained_at: datetime, seed: int
    ) -> ModelMetadata:
        with self._lock:
            history = self._records.setdefault(name, [])
            metadata = ModelMetadata(
                name=name,
                version=len(history) + 1,
                trained_at=trained_at,
                seed=seed,
                metrics=dict(artifact.metrics),
                artifact_sha256=hashlib.sha256(artifact.payload).hexdigest(),
                dataset_description=artifact.dataset_description,
                library=artifact.library,
            )
            history.append(
                _Record(metadata, artifact.payload, dict(artifact.importances), artifact.notes)
            )
            return metadata

    def latest(self, name: str) -> ModelMetadata | None:
        with self._lock:
            records = self._records.get(name)
            return records[-1].metadata if records else None

    def load(self, name: str) -> LoadedModel:
        with self._lock:
            records = self._records.get(name)
            if not records:
                raise ArtifactIntegrityError(f"El modelo '{name}' no está registrado.")
            record = records[-1]
            digest = hashlib.sha256(record.payload).hexdigest()
            if not hmac.compare_digest(digest, record.metadata.artifact_sha256):
                raise ArtifactIntegrityError(
                    f"El artefacto del modelo '{name}' no coincide con el hash registrado; "
                    "no se carga."
                )
            return LoadedModel(
                record.metadata, record.payload, dict(record.importances), record.notes
            )

    def versions(self, name: str) -> list[ModelMetadata]:
        with self._lock:
            return [r.metadata for r in self._records.get(name, [])]
