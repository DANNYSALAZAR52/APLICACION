"""DEMO-ONLY: simulador de dispositivos GPS.

Cada vehículo "reporta" una lectura cada ``interval_min`` minutos simulados mientras tiene señal.
Las lecturas se generan al consultar (se pone al día hasta la hora del reloj), a partir de la
posición que dicta el plan (``truth``). Se puede cortar la señal de un vehículo para probar la
alerta de "sin señal"; al cortarla no se generan lecturas y la última queda envejeciendo.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Sequence

from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.domain.routing.gps import GpsFix, GpsSample

Truth = Callable[[str, float], GpsSample | None]


class SimulatedGps:
    def __init__(
        self,
        truth: Truth,
        clock: ClockPort,
        vehicle_ids: Sequence[str],
        interval_min: float = 2.0,
        max_catch_up_min: float = 300.0,
        keep: int = 400,
    ) -> None:
        if not 1.0 <= interval_min <= 5.0:
            raise ValueError("El intervalo del GPS simulado debe ser de 1 a 5 minutos.")
        self._truth = truth
        self._clock = clock
        self._interval = interval_min
        self._max_catch_up = max_catch_up_min
        self._ids = tuple(vehicle_ids)
        self._fixes: dict[str, deque[GpsFix]] = {v: deque(maxlen=keep) for v in self._ids}
        self._last: dict[str, float] = {}
        self._muted: set[str] = set()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ interno
    def _now_min(self) -> float:
        now = self._clock.now()
        return now.hour * 60 + now.minute + now.second / 60 + now.microsecond / 6e7

    def _record(self, vehicle_id: str, minute: float) -> None:
        if vehicle_id in self._muted:
            return
        sample = self._truth(vehicle_id, minute)
        if sample is not None:
            self._fixes[vehicle_id].append(
                GpsFix(vehicle_id, minute, sample.point, sample.speed_kmh, sample.engine_on)
            )

    def _catch_up(self) -> None:
        now = self._now_min()
        for vid in self._ids:
            last = self._last.get(vid)
            if last is None or now < last - 1e-9:  # primera lectura o el reloj retrocedió
                self._fixes[vid].clear()
                self._last[vid] = now
                self._record(vid, now)
                continue
            t = max(last + self._interval, now - self._max_catch_up)
            while t <= now + 1e-9:
                self._record(vid, t)
                last = t
                t += self._interval
            self._last[vid] = last

    # ------------------------------------------------------------------ GpsPort
    def latest_fix(self, vehicle_id: str) -> GpsFix | None:
        with self._lock:
            self._catch_up()
            fixes = self._fixes.get(vehicle_id)
            return fixes[-1] if fixes else None

    def fixes_since(self, vehicle_id: str, since_min: float) -> list[GpsFix]:
        with self._lock:
            self._catch_up()
            return [f for f in self._fixes.get(vehicle_id, ()) if f.at_min >= since_min]

    # ------------------------------------------------------- GpsSimulationControl
    def set_signal(self, vehicle_id: str, enabled: bool) -> None:
        with self._lock:
            self._catch_up()  # lo anterior ocurrió con la señal que había
            if enabled:
                self._muted.discard(vehicle_id)
            else:
                self._muted.add(vehicle_id)

    def signal_enabled(self, vehicle_id: str) -> bool:
        with self._lock:
            return vehicle_id not in self._muted

    def reset(self) -> None:
        with self._lock:
            for fixes in self._fixes.values():
                fixes.clear()
            self._last.clear()
            self._muted.clear()
