"""Evaluación de una ruta: llegadas, esperas, retrasos, carga y puntaje (DOCS.MD §7.2).

```text
llegada         = salida_anterior + tiempo_de_viaje
inicio_servicio = max(llegada, inicio_ventana)
retraso         = max(llegada - fin_ventana, 0)
salida          = inicio_servicio + minutos_servicio
puntaje         = viaje + w_espera·espera + w_retraso·retraso + w_extra·min_fuera_de_turno
```
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.models import RoutingParams
from fleetplanner.domain.routing.time_window import TimeWindow

_EPS = 1e-9


@dataclass(frozen=True)
class TravelLeg:
    minutes: float
    km: float


# (origen, destino, minuto de salida) -> tramo; el caso de uso lo arma con el puerto de tiempos.
TravelFn = Callable[[GeoPoint, GeoPoint, float], TravelLeg]


class StopKind(StrEnum):
    DELIVERY = "delivery"
    TRANSFER = "transfer"  # transbordo en el punto de avería
    RELOAD = "reload"  # recarga en el CEDI


@dataclass(frozen=True)
class StopSpec:
    """Parada por visitar. ``load_delta_kg`` es negativo al entregar y positivo al cargar."""

    key: str
    kind: StopKind
    point: GeoPoint
    label: str
    service_min: float
    load_delta_kg: float
    window: TimeWindow | None = None
    order_id: str | None = None
    customer_code: str | None = None
    priority: int = 2


@dataclass(frozen=True)
class StopTiming:
    spec: StopSpec
    arrival_min: float
    service_start_min: float
    departure_min: float
    wait_min: float
    delay_min: float
    travel_min: float
    km: float
    load_after_kg: float

    @property
    def is_late(self) -> bool:
        return self.delay_min > _EPS


@dataclass(frozen=True)
class RouteEvaluation:
    timings: tuple[StopTiming, ...]
    return_arrival_min: float
    return_travel_min: float
    return_km: float
    travel_min: float
    km: float
    wait_min: float
    delay_min: float
    overtime_min: float
    peak_load_kg: float
    capacity_ok: bool
    score: float

    @property
    def late_stops(self) -> int:
        return sum(1 for t in self.timings if t.is_late)

    @property
    def end_min(self) -> float:
        return self.return_arrival_min


def evaluate_route(
    anchor_point: GeoPoint,
    anchor_time_min: float,
    initial_load_kg: float,
    specs: Sequence[StopSpec],
    depot_point: GeoPoint,
    capacity_kg: float,
    params: RoutingParams,
    travel: TravelFn,
    return_to_depot: bool = True,
) -> RouteEvaluation:
    """Calcula la línea de tiempo de ``specs`` en ese orden, desde el ancla y de vuelta al CEDI.

    ``capacity_kg`` es la capacidad operativa. ``capacity_ok`` es falso si la carga a bordo
    supera ese límite en algún momento o si se intenta entregar más de lo que hay a bordo.
    ``return_to_depot=False`` se usa para un vehículo averiado, que no regresa por sí mismo.
    """
    point = anchor_point
    clock = anchor_time_min
    load = initial_load_kg
    peak = load
    capacity_ok = load <= capacity_kg + _EPS
    timings: list[StopTiming] = []
    travel_total = wait_total = delay_total = km_total = 0.0

    for spec in specs:
        leg = travel(point, spec.point, clock)
        arrival = clock + leg.minutes
        start = arrival
        delay = 0.0
        if spec.window is not None:
            start = max(arrival, spec.window.start_min)
            delay = max(arrival - spec.window.end_min, 0.0)
        wait = start - arrival
        departure = start + spec.service_min
        load += spec.load_delta_kg
        peak = max(peak, load)
        if load > capacity_kg + _EPS or load < -_EPS:
            capacity_ok = False
        timings.append(
            StopTiming(
                spec=spec,
                arrival_min=arrival,
                service_start_min=start,
                departure_min=departure,
                wait_min=wait,
                delay_min=delay,
                travel_min=leg.minutes,
                km=leg.km,
                load_after_kg=load,
            )
        )
        travel_total += leg.minutes
        wait_total += wait
        delay_total += delay
        km_total += leg.km
        point, clock = spec.point, departure

    back = travel(point, depot_point, clock) if return_to_depot else TravelLeg(0.0, 0.0)
    return_arrival = clock + back.minutes
    travel_total += back.minutes
    km_total += back.km
    overtime = max(return_arrival - params.shift_end_min, 0.0)
    score = (
        params.weight_travel * travel_total
        + params.weight_wait * wait_total
        + params.weight_delay * delay_total
        + params.weight_overtime * overtime
    )
    return RouteEvaluation(
        timings=tuple(timings),
        return_arrival_min=return_arrival,
        return_travel_min=back.minutes,
        return_km=back.km,
        travel_min=travel_total,
        km=km_total,
        wait_min=wait_total,
        delay_min=delay_total,
        overtime_min=overtime,
        peak_load_kg=peak,
        capacity_ok=capacity_ok,
        score=score,
    )
