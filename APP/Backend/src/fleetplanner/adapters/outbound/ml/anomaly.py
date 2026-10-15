"""Detección de anomalías en esperas y tiempos de servicio con Isolation Forest.

Cada visita se compara con el patrón habitual DE SU cliente (razón entre lo observado y la
mediana del cliente) junto con la hora y el día de la semana. Las visitas marcadas se agrupan por
cliente, día de la semana y franja de dos horas, y se explican con una frase. Es evidencia
estadística: no se afirma causalidad.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from fleetplanner.adapters.outbound.ml import codec
from fleetplanner.application.dto.ml import TrainedArtifact
from fleetplanner.domain.ml.records import OperationalHistory, ServiceVisit
from fleetplanner.domain.ml.results import Anomaly
from fleetplanner.domain.shared.errors import InsufficientDataError

CONTAMINATION = 0.03
BAND_HOURS = 2
MIN_FLAGGED_IN_SLOT = 3
MIN_RATIO = 1.5
FEATURES = ("espera / habitual", "servicio / habitual", "hora", "día de la semana")


def _baselines(visits: tuple[ServiceVisit, ...]) -> dict[str, tuple[float, float]]:
    waits: dict[str, list[float]] = defaultdict(list)
    services: dict[str, list[float]] = defaultdict(list)
    for v in visits:
        waits[v.customer_code].append(v.wait_min)
        services[v.customer_code].append(v.service_min)
    return {
        code: (
            max(statistics.median(waits[code]), 1.0),
            max(statistics.median(services[code]), 1.0),
        )
        for code in waits
    }


def _row(v: ServiceVisit, base: tuple[float, float]) -> list[float]:
    return [v.wait_min / base[0], v.service_min / base[1], float(v.hour), float(v.day.weekday())]


class SklearnAnomalyDetector:
    """Implementa `AnomalyDetector` con IsolationForest."""

    def train(self, history: OperationalHistory, seed: int) -> TrainedArtifact:
        if len(history.visits) < 100:
            raise InsufficientDataError("Hay muy pocas visitas para detectar anomalías.")
        baselines = _baselines(history.visits)
        matrix = np.array([_row(v, baselines[v.customer_code]) for v in history.visits])
        forest = IsolationForest(
            n_estimators=200, contamination=CONTAMINATION, random_state=seed
        ).fit(matrix)
        flagged = int(np.sum(forest.predict(matrix) == -1))
        return TrainedArtifact(
            payload=codec.dump({"forest": forest, "baselines": baselines}),
            metrics={"n_visits": float(len(history.visits)), "n_flagged": float(flagged)},
            importances={},
            notes=(
                "Cada visita se compara con la mediana de su propio cliente.",
                "Se agrupan las visitas marcadas por cliente, día de la semana y franja de "
                f"{BAND_HOURS} h; se reportan franjas con al menos {MIN_FLAGGED_IN_SLOT} visitas "
                f"marcadas y {MIN_RATIO:g} veces el patrón habitual.",
            ),
            dataset_description=history.provenance,
            library=codec.library_version(),
        )

    def detect(self, payload: bytes, history: OperationalHistory, limit: int) -> list[Anomaly]:
        bundle: dict[str, Any] = codec.load(payload)
        forest: IsolationForest = bundle["forest"]
        baselines: dict[str, tuple[float, float]] = bundle["baselines"]
        visits = [v for v in history.visits if v.customer_code in baselines]
        if not visits:
            return []
        matrix = np.array([_row(v, baselines[v.customer_code]) for v in visits])
        flags = forest.predict(matrix) == -1

        slots: dict[tuple[str, int, int], list[tuple[ServiceVisit, bool]]] = defaultdict(list)
        for visit, flagged in zip(visits, flags, strict=True):
            band = visit.hour // BAND_HOURS * BAND_HOURS
            slots[(visit.customer_code, visit.day.weekday(), band)].append((visit, bool(flagged)))

        found: list[Anomaly] = []
        for (code, weekday, band), items in slots.items():
            flagged_count = sum(1 for _, f in items if f)
            if flagged_count < MIN_FLAGGED_IN_SLOT:
                continue
            base_wait, base_service = baselines[code]
            mean_wait = statistics.fmean(v.wait_min for v, _ in items)
            mean_service = statistics.fmean(v.service_min for v, _ in items)
            wait_ratio = mean_wait / base_wait
            service_ratio = mean_service / base_service
            kind, observed, usual, ratio = (
                ("espera", mean_wait, base_wait, wait_ratio)
                if wait_ratio >= service_ratio
                else ("servicio", mean_service, base_service, service_ratio)
            )
            if ratio < MIN_RATIO:
                continue
            found.append(
                Anomaly(
                    customer_code=code,
                    customer_name=history.customer_name(code),
                    kind=kind,
                    weekday=weekday,
                    hour_from=band,
                    hour_to=band + BAND_HOURS,
                    events=len(items),
                    observed_min=round(observed, 1),
                    usual_min=round(usual, 1),
                    severity=round((ratio - 1.0) * (flagged_count**0.5), 2),
                )
            )
        found.sort(key=lambda a: a.severity, reverse=True)
        return found[:limit]
