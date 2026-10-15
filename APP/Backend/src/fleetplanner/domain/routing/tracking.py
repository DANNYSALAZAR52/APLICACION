"""Seguimiento: dónde está un vehículo y qué hace en un instante, según su línea de tiempo.

La posición se interpola en línea recta entre paradas (DEMO-ONLY: no sigue calles).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from fleetplanner.domain.routing.evaluation import StopTiming
from fleetplanner.domain.routing.geo import GeoPoint, interpolate


class VehicleStatus(StrEnum):
    NOT_STARTED = "not_started"  # en el CEDI esperando la hora de salida
    TRAVELING = "traveling"
    WAITING = "waiting"  # llegó antes de que abra la ventana
    SERVING = "serving"
    RETURNING = "returning"  # de regreso al CEDI
    AT_DEPOT = "at_depot"  # terminó la ruta
    BROKEN = "broken"
    STANDBY = "standby"  # reserva sin ruta asignada


class SegmentKind(StrEnum):
    TRAVEL = "travel"
    WAIT = "wait"
    SERVICE = "service"
    RETURN = "return"


@dataclass(frozen=True)
class Segment:
    kind: SegmentKind
    start_min: float
    end_min: float
    origin: GeoPoint
    destination: GeoPoint
    stop_key: str | None = None


@dataclass(frozen=True)
class VehicleState:
    status: VehicleStatus
    point: GeoPoint
    minute: float
    current_stop_key: str | None
    next_stop_key: str | None
    completed_stops: int
    pending_stops: int


def build_segments(
    frozen: Sequence[StopTiming],
    anchor_point: GeoPoint,
    anchor_time_min: float,
    pending: Sequence[StopTiming],
    depot_point: GeoPoint,
    return_arrival_min: float,
) -> list[Segment]:
    """Segmentos de espera/servicio de lo ya congelado y viaje completo de lo pendiente."""
    segments: list[Segment] = []
    for t in frozen:
        _stop_segments(segments, t)
    point, clock = anchor_point, anchor_time_min
    for t in pending:
        segments.append(
            Segment(SegmentKind.TRAVEL, clock, t.arrival_min, point, t.spec.point, t.spec.key)
        )
        _stop_segments(segments, t)
        point, clock = t.spec.point, t.departure_min
    segments.append(Segment(SegmentKind.RETURN, clock, return_arrival_min, point, depot_point))
    return segments


def _stop_segments(segments: list[Segment], t: StopTiming) -> None:
    p = t.spec.point
    if t.service_start_min > t.arrival_min:
        segments.append(
            Segment(SegmentKind.WAIT, t.arrival_min, t.service_start_min, p, p, t.spec.key)
        )
    segments.append(
        Segment(SegmentKind.SERVICE, t.service_start_min, t.departure_min, p, p, t.spec.key)
    )


def locate(
    segments: Sequence[Segment],
    now_min: float,
    start_point: GeoPoint,
    depot_point: GeoPoint,
    timings: Sequence[StopTiming],
) -> VehicleState:
    """Estado del vehículo en ``now_min``. ``timings`` = frozen + pendientes (para contar)."""
    completed = sum(1 for t in timings if t.departure_min <= now_min)
    pending = len(timings) - completed
    next_stop = next((t.spec.key for t in timings if t.departure_min > now_min), None)

    first = segments[0] if segments else None
    if first is not None and now_min < first.start_min:
        return VehicleState(
            VehicleStatus.NOT_STARTED, start_point, now_min, None, next_stop, completed, pending
        )
    for seg in segments:
        if not seg.start_min <= now_min < seg.end_min:
            continue
        if seg.kind is SegmentKind.SERVICE:
            return VehicleState(
                VehicleStatus.SERVING,
                seg.origin,
                now_min,
                seg.stop_key,
                next_stop,
                completed,
                pending,
            )
        if seg.kind is SegmentKind.WAIT:
            return VehicleState(
                VehicleStatus.WAITING,
                seg.origin,
                now_min,
                seg.stop_key,
                next_stop,
                completed,
                pending,
            )
        span = seg.end_min - seg.start_min
        fraction = (now_min - seg.start_min) / span if span > 0 else 1.0
        status = (
            VehicleStatus.RETURNING if seg.kind is SegmentKind.RETURN else VehicleStatus.TRAVELING
        )
        return VehicleState(
            status,
            interpolate(seg.origin, seg.destination, fraction),
            now_min,
            None,
            next_stop,
            completed,
            pending,
        )
    return VehicleState(VehicleStatus.AT_DEPOT, depot_point, now_min, None, None, completed, 0)
