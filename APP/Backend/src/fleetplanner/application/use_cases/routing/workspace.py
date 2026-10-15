"""Espacio de trabajo de ruteo de UN tenant y control del día operativo simulado."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

from fleetplanner.application.dto.routing import SimControl, SimControlAction
from fleetplanner.application.ports.outbound.clock import SimulationClockPort
from fleetplanner.application.ports.outbound.routing import TrafficProviderControl
from fleetplanner.application.use_cases.routing.approve_reroute import ApproveReroute
from fleetplanner.application.use_cases.routing.build_morning_plan import BuildMorningPlan
from fleetplanner.application.use_cases.routing.core import RoutingCore
from fleetplanner.application.use_cases.routing.driver import DriverService
from fleetplanner.application.use_cases.routing.handle_event import HandleEvent
from fleetplanner.application.use_cases.routing.rerouting import ReroutePlanner
from fleetplanner.application.use_cases.routing.snapshot import GetOperationsSnapshot
from fleetplanner.application.use_cases.routing.track_fleet import TrackFleet
from fleetplanner.domain.routing.plan import RoutePlan
from fleetplanner.domain.shared.errors import InvalidValueError

if TYPE_CHECKING:
    from fleetplanner.application.use_cases.routing.indicators import IndicatorsService

DAY_START = time(5, 0)  # a las 05:00 se arma el plan de la mañana (DOCS.MD §7.3)
ALLOWED_SPEEDS = (1.0, 10.0, 30.0, 60.0, 120.0)


class OperatingDay:
    """Reinicia el día, controla el reloj acelerado y el proveedor de tiempos (DEMO-ONLY)."""

    def __init__(
        self,
        core: RoutingCore,
        build: BuildMorningPlan,
        sim_clock: SimulationClockPort,
        provider: TrafficProviderControl,
    ) -> None:
        self._core = core
        self._build = build
        self._clock = sim_clock
        self._provider = provider

    def start(self, actor: str) -> RoutePlan:
        """Día nuevo: reloj a las 05:00 en pausa, proveedor disponible y plan de la mañana."""
        self._core.reload()  # maestros vigentes
        now = self._clock.now()
        self._clock.reset(datetime.combine(now.date(), DAY_START, tzinfo=now.tzinfo))
        self._provider.set_available(True)
        if self._core.gps_control is not None:
            self._core.gps_control.reset()
        self._core.repo.reset(now.date(), self._core.dataset.orders)
        return self._build.execute(actor)

    def is_paused(self) -> bool:
        return self._clock.status().paused

    def seek(self, minute: float) -> None:
        """Lleva el reloj a una hora del día en curso (escenarios y pruebas); queda en pausa."""
        now = self._clock.now()
        base = datetime.combine(now.date(), time(0, 0), tzinfo=now.tzinfo)
        self._clock.reset(base + timedelta(minutes=minute))

    def control(self, command: SimControl) -> None:
        action, value = command.action, command.value
        if action is SimControlAction.PAUSE:
            self._clock.pause()
        elif action is SimControlAction.RESUME:
            self._clock.resume()
        elif action is SimControlAction.SPEED:
            if value not in ALLOWED_SPEEDS:
                options = ", ".join(f"{s:g}×" for s in ALLOWED_SPEEDS)
                raise InvalidValueError(f"Velocidad no permitida. Opciones: {options}.")
            self._clock.set_speed(float(value))
        elif action is SimControlAction.ADVANCE:
            if value is None or not 0 < value <= 240:
                raise InvalidValueError("Indique cuántos minutos avanzar (entre 1 y 240).")
            self._clock.advance(float(value))
        elif action is SimControlAction.PROVIDER:
            self._provider.set_available(bool(value))
        elif action is SimControlAction.GPS_SIGNAL:
            control = self._core.gps_control
            if control is None or not command.target:
                raise InvalidValueError("Indique el vehículo cuya señal GPS se corta o restablece.")
            control.set_signal(self._core.vehicle(command.target).id, bool(value))
        else:  # pragma: no cover - el enum es cerrado
            raise InvalidValueError("Acción de simulación no soportada.")


@dataclass(frozen=True)
class RoutingWorkspace:
    core: RoutingCore
    build_plan: BuildMorningPlan
    handle_event: HandleEvent
    approve: ApproveReroute
    track: TrackFleet
    snapshot: GetOperationsSnapshot
    day: OperatingDay
    planner: ReroutePlanner
    driver: DriverService
    # Serializa las operaciones sobre el estado del día de esta empresa (peticiones en paralelo).
    lock: threading.RLock = field(default_factory=threading.RLock)
    # Escenarios del día: lo asigna el ensamblado (usa un espacio de trabajo aparte).
    indicators: IndicatorsService | None = None

    def is_paused(self) -> bool:
        return self.day.is_paused()
