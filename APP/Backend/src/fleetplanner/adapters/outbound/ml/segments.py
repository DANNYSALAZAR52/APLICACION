"""Segmentación de clientes con KMeans sobre su comportamiento de servicio.

Variables por cliente: tiempo de servicio medio, tamaño de pedido medio, amplitud de ventana y
variación semanal del pedido (estacionalidad). El número de segmentos se elige por el coeficiente
de silueta. Los nombres describen lo que distingue a cada grupo del conjunto: no son categorías
objetivas ni universales.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from fleetplanner.adapters.outbound.ml import codec
from fleetplanner.application.dto.ml import TrainedArtifact
from fleetplanner.domain.ml.records import OperationalHistory
from fleetplanner.domain.ml.results import Segment
from fleetplanner.domain.shared.errors import InsufficientDataError

FEATURES = (
    "tiempo de servicio medio",
    "tamaño de pedido medio",
    "amplitud de la ventana",
    "variación semanal del pedido",
)
_MIN_CUSTOMERS = 8
_MAX_K = 4
_LABELS = (
    ("servicio largo", "servicio corto"),
    ("pedidos grandes", "pedidos pequeños"),
    ("ventana amplia", "ventana estrecha"),
    ("demanda variable en la semana", "demanda estable en la semana"),
)


def _customer_matrix(history: OperationalHistory) -> tuple[list[str], np.ndarray]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for v in history.visits:
        grouped[v.customer_code].append(v)
    codes: list[str] = []
    rows: list[list[float]] = []
    for code in sorted(grouped):
        items = grouped[code]
        by_weekday: dict[int, list[float]] = defaultdict(list)
        for v in items:
            by_weekday[v.day.weekday()].append(v.order_kg)
        means = [statistics.fmean(values) for values in by_weekday.values()]
        overall = statistics.fmean(means)
        variation = statistics.pstdev(means) / overall if len(means) > 1 and overall > 0 else 0.0
        codes.append(code)
        rows.append(
            [
                statistics.fmean(v.service_min for v in items),
                statistics.fmean(v.order_kg for v in items),
                statistics.fmean(v.window_width_min for v in items),
                variation,
            ]
        )
    return codes, np.array(rows)


def _standardize(
    matrix: np.ndarray, mean: np.ndarray | None = None, std: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = matrix.mean(axis=0) if mean is None else mean
    std = matrix.std(axis=0) if std is None else std
    safe = np.where(std < 1e-9, 1.0, std)
    return (matrix - mean) / safe, mean, std


class SklearnPatternMiner:
    """Implementa `PatternMiner` con KMeans."""

    def train(self, history: OperationalHistory, seed: int) -> TrainedArtifact:
        codes, matrix = _customer_matrix(history)
        if len(codes) < _MIN_CUSTOMERS:
            raise InsufficientDataError(
                f"Se necesitan al menos {_MIN_CUSTOMERS} clientes para segmentar."
            )
        scaled, mean, std = _standardize(matrix)
        best: tuple[float, int, KMeans] | None = None
        for k in range(2, min(_MAX_K, len(codes) - 1) + 1):
            model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(scaled)
            score = float(silhouette_score(scaled, model.labels_))
            if best is None or score > best[0] + 1e-9:
                best = (score, k, model)
        if best is None:
            raise InsufficientDataError("No se pudo formar ningún segmento.")
        score, k, model = best
        return TrainedArtifact(
            payload=codec.dump({"model": model, "mean": mean, "std": std}),
            metrics={"k": float(k), "silhouette": score, "n_customers": float(len(codes))},
            importances={},
            notes=(
                "El número de segmentos (2 a 4) se eligió por el coeficiente de silueta.",
                "Los nombres describen diferencias relativas dentro de esta empresa.",
            ),
            dataset_description=history.provenance,
            library=codec.library_version(),
        )

    def segments(self, payload: bytes, history: OperationalHistory) -> list[Segment]:
        bundle: dict[str, Any] = codec.load(payload)
        codes, matrix = _customer_matrix(history)
        if not codes:
            return []
        scaled, _, _ = _standardize(matrix, bundle["mean"], bundle["std"])
        labels = bundle["model"].predict(scaled)
        # Z-scores respecto del conjunto actual para nombrar de forma relativa.
        z_all, _, _ = _standardize(matrix)

        order = sorted({int(x) for x in labels}, key=lambda c: -int(np.sum(labels == c)))
        segments: list[Segment] = []
        used_names: set[str] = set()
        for new_id, cluster in enumerate(order, start=1):
            mask = labels == cluster
            z_mean = z_all[mask].mean(axis=0)
            ranked = sorted(range(4), key=lambda i: abs(float(z_mean[i])), reverse=True)
            parts = [
                _LABELS[i][0 if z_mean[i] > 0 else 1] for i in ranked[:2] if abs(z_mean[i]) >= 0.5
            ]
            name = " y ".join(parts).capitalize() if parts else "Perfil promedio"
            if name in used_names:
                name = f"{name} ({new_id})"
            used_names.add(name)
            members = tuple(c for c, m in zip(codes, mask, strict=True) if m)
            raw = matrix[mask]
            service, kg, window, variation = (float(v) for v in raw.mean(axis=0))
            segments.append(
                Segment(
                    segment_id=new_id,
                    name=name,
                    description=(
                        f"{len(members)} clientes; servicio medio {service:.0f} min, pedido medio "
                        f"{kg:.0f} kg, ventana media {window:.0f} min."
                    ),
                    customers=members,
                    mean_service_min=round(service, 1),
                    mean_order_kg=round(kg, 0),
                    mean_window_min=round(window, 0),
                    weekly_variation=round(variation, 3),
                )
            )
        return segments
