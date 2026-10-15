"""Alta de propuestas ligadas a su evento (compartido por eventos, seguimiento y reaprobación)."""

from __future__ import annotations

from dataclasses import replace

from fleetplanner.application.ports.outbound.clock import SimulationClockPort
from fleetplanner.application.use_cases.routing.core import RoutingCore
from fleetplanner.application.use_cases.routing.rerouting import ProposalDraft
from fleetplanner.domain.routing.events import (
    OperationalEvent,
    ProposalStatus,
    RerouteProposal,
)


def store_proposal(
    core: RoutingCore,
    event: OperationalEvent,
    draft: ProposalDraft,
    sim_clock: SimulationClockPort | None = None,
) -> tuple[OperationalEvent, RerouteProposal]:
    """Guarda la propuesta, la liga al evento y pausa el reloj simulado si espera decisión.

    La pausa evita que la propuesta quede obsoleta mientras el despachador la lee (DEMO-ONLY).
    """
    repo = core.repo
    active = repo.active_plan()
    pending = draft.plan is not None
    proposal = RerouteProposal(
        id=repo.next_id("PR"),
        event_id=event.id,
        event_type=event.type,
        base_version=active.version if active else 0,
        created_at=core.clock.now(),
        reason=draft.reason,
        summary=draft.summary,
        impact=draft.impact,
        proposed_plan=draft.plan,
        status=ProposalStatus.PENDING if pending else ProposalStatus.NONE_NEEDED,
        requires_confirmation=draft.requires_confirmation,
        created_minute=core.now_min(),
    )
    repo.save_proposal(proposal)
    updated = replace(
        event,
        proposal_ids=(*event.proposal_ids, proposal.id),
        outcome=draft.summary,
    )
    repo.update_event(updated)
    if pending and sim_clock is not None:
        sim_clock.pause()
    return updated, proposal
