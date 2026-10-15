"""Puertos de salida de ML. El dominio y la aplicación no conocen scikit-learn."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from fleetplanner.application.dto.ml import LoadedModel, TrainedArtifact
from fleetplanner.domain.ml.records import OperationalHistory
from fleetplanner.domain.ml.results import (
    Anomaly,
    DelayRisk,
    Forecast,
    ModelMetadata,
    Segment,
)


class HistoryReaderPort(Protocol):
    """Historia operativa de UNA empresa (la instancia se crea por tenant)."""

    def load(self) -> OperationalHistory: ...


class DemandForecaster(Protocol):
    def train(self, history: OperationalHistory, seed: int) -> TrainedArtifact: ...

    def forecast(
        self, payload: bytes, history: OperationalHistory, first_day: date, horizon_days: int
    ) -> list[Forecast]: ...


class AnomalyDetector(Protocol):
    def train(self, history: OperationalHistory, seed: int) -> TrainedArtifact: ...

    def detect(self, payload: bytes, history: OperationalHistory, limit: int) -> list[Anomaly]: ...


class DelayRiskPredictor(Protocol):
    def train(self, history: OperationalHistory, seed: int) -> TrainedArtifact: ...

    def predict(
        self, payload: bytes, history: OperationalHistory, limit: int
    ) -> list[DelayRisk]: ...


class PatternMiner(Protocol):
    def train(self, history: OperationalHistory, seed: int) -> TrainedArtifact: ...

    def segments(self, payload: bytes, history: OperationalHistory) -> list[Segment]: ...


class ModelRegistryPort(Protocol):
    """Registro de versiones y artefactos de UNA empresa, con verificación de integridad."""

    def register(
        self,
        name: str,
        artifact: TrainedArtifact,
        trained_at: datetime,
        seed: int,
    ) -> ModelMetadata: ...

    def latest(self, name: str) -> ModelMetadata | None: ...

    def load(self, name: str) -> LoadedModel:
        """Devuelve la última versión **tras verificar su hash**; si no coincide, falla."""
        ...

    def versions(self, name: str) -> list[ModelMetadata]: ...
