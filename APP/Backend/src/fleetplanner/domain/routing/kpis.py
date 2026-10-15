"""Indicadores diarios de ruteo. Puntualidad y OTIF son métricas DISTINTAS (DOCS.MD §8).

* **Puntualidad** = pedidos entregados dentro de su ventana / pedidos comprometidos.
* **OTIF** (on time, in full) = pedidos entregados completos **y** a tiempo / pedidos comprometidos.

El denominador es el mismo en ambas y en todas las comparaciones: todos los pedidos comprometidos
del día, incluidos los urgentes y los que quedaron sin atender (esos cuentan como no cumplidos).
Un pedido es puntual si la llegada ocurre antes o en el fin de su ventana. Ninguna definición se
ajusta para que un resultado coincida con una referencia.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from fleetplanner.domain.routing.evaluation import StopKind, StopTiming

_EPS = 1e-6


@dataclass(frozen=True)
class DailyKpis:
    committed_orders: int
    delivered_orders: int
    on_time_orders: int
    otif_orders: int
    late_orders: int
    unattended_orders: int
    incomplete_orders: int
    total_delay_min: float

    @property
    def punctuality(self) -> float | None:
        return self.on_time_orders / self.committed_orders if self.committed_orders else None

    @property
    def otif(self) -> float | None:
        return self.otif_orders / self.committed_orders if self.committed_orders else None


def incomplete_every(rate: float) -> int | None:
    """Cada cuántas entregas una queda incompleta para lograr ``rate`` (0 = ninguna)."""
    if rate <= 0:
        return None
    return max(1, round(1.0 / rate))


def compute_kpis(
    timings: Iterable[StopTiming],
    committed_order_ids: Sequence[str],
    incomplete_rate: float = 0.0,
) -> DailyKpis:
    """KPIs a partir de las entregas realizadas o proyectadas.

    ``incomplete_rate`` marca de forma determinista (cada k-ésimo pedido entregado, por
    identificador) entregas incompletas para ilustrar escenarios de cumplimiento (D-013). No es
    una medición: es un parámetro del escenario y se rotula como tal.
    """
    delivered = sorted(
        (t for t in timings if t.spec.kind is StopKind.DELIVERY and t.spec.order_id),
        key=lambda t: t.spec.order_id or "",
    )
    every = incomplete_every(incomplete_rate)
    on_time = otif = late = incomplete = 0
    delay = 0.0
    for i, t in enumerate(delivered, start=1):
        punctual = t.delay_min <= _EPS
        full = not (every is not None and i % every == 0)
        on_time += punctual
        late += not punctual
        incomplete += not full
        otif += punctual and full
        delay += t.delay_min
    committed = len(committed_order_ids)
    return DailyKpis(
        committed_orders=committed,
        delivered_orders=len(delivered),
        on_time_orders=on_time,
        otif_orders=otif,
        late_orders=late,
        unattended_orders=max(committed - len(delivered), 0),
        incomplete_orders=incomplete,
        total_delay_min=delay,
    )
