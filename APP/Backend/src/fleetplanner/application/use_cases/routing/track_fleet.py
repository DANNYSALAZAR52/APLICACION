"""TrackFleet: seguimiento periódico (DOCS.MD §7.4).

Recalcula los horarios de las paradas pendientes con lo que se sabe y, si alguna queda en
retraso, propone re-secuenciar ese vehículo y alerta al despachador.
"""

from __future__ import annotations

from fleetplanner.application.ports.outbound.clock import SimulationClockPort
from fleetplanner.application.use_cases.routing.core import RoutingCore
from fleetplanner.application.use_cases.routing.gps_support import GpsMonitor
from fleetplanner.application.use_cases.routing.proposals import store_proposal
from fleetplanner.application.use_cases.routing.rerouting import ReroutePlanner
from fleetplanner.domain.routing.events import (
    DelayRiskData,
    EventType,
    OperationalEvent,
    ProposalStatus,
    RerouteProposal,
)
from fleetplanner.domain.routing.plan import RouteStatus

SYSTEM_ACTOR = "sistema (seguimiento)"
_EPS = 1e-6


class TrackFleet:
    def __init__(
        self,
        core: RoutingCore,
        planner: ReroutePlanner,
        sim_clock: SimulationClockPort | None = None,
        monitor: GpsMonitor | None = None,
    ) -> None:
        self._core = core
        self._planner = planner
        self._sim_clock = sim_clock
        self._monitor = monitor

    def execute(self) -> list[RerouteProposal]:
        """Devuelve las propuestas nuevas generadas por riesgo de retraso (puede ser ninguna)."""
        core = self._core
        active = core.repo.active_plan()
        if active is None:
            return []
        created: list[RerouteProposal] = []
        ctx = self._planner.context()
        if self._monitor is not None:
            self._monitor.evaluate_geofence(ctx.views, ctx.now)
        proposals = core.repo.proposals()
        for vid, view in sorted(ctx.views.items()):
            if view.route.status is not RouteStatus.ACTIVE:
                continue
            if not any(t.delay_min > _EPS for t in view.evaluation.timings):
                continue
            if self._already_handled(vid, active.version, proposals):
                continue
            event = OperationalEvent(
                id=core.repo.next_id("EV"),
                type=EventType.DELAY_RISK,
                occurred_at=core.clock.now(),
                minute=ctx.now,
                created_by=SYSTEM_ACTOR,
                summary=f"Riesgo de retraso en {view.route.plate}",
                payload=DelayRiskData(vid),
            )
            draft = self._planner.propose(event, SYSTEM_ACTOR)
            if draft.plan is None:
                continue  # re-secuenciar no mejora: solo queda la alerta
            core.repo.add_event(event)
            _, proposal = store_proposal(core, event, draft, self._sim_clock)
            created.append(proposal)
            break  # una propuesta a la vez: la siguiente se calcula sobre el plan resultante
        return created

    @staticmethod
    def _already_handled(vehicle_id: str, version: int, proposals: list[RerouteProposal]) -> bool:
        """Hay una propuesta pendiente para el vehículo o se rechazó una sobre esta versión."""
        for p in proposals:
            if vehicle_id not in p.impact.affected_vehicles:
                continue
            if p.status is ProposalStatus.PENDING:
                return True
            if p.status is ProposalStatus.REJECTED and p.base_version == version:
                return True
        return False
