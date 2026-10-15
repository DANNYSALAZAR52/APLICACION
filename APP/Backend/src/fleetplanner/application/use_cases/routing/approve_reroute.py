"""ApproveReroute: el despachador aprueba o rechaza una propuesta de re-ruteo."""

from __future__ import annotations

from dataclasses import replace

from fleetplanner.application.dto.routing import DecisionResult
from fleetplanner.application.ports.outbound.clock import SimulationClockPort
from fleetplanner.application.use_cases.routing.core import RoutingCore
from fleetplanner.application.use_cases.routing.proposals import store_proposal
from fleetplanner.application.use_cases.routing.rerouting import ReroutePlanner
from fleetplanner.domain.routing.events import ProposalStatus, RerouteProposal
from fleetplanner.domain.shared.errors import ConflictError, NotFoundError

# Pasados estos minutos de reloj desde que se calculó, una propuesta se recalcula.
STALE_AFTER_MIN = 5.0


class ApproveReroute:
    """Aprobar crea una versión nueva del plan; rechazar deja el plan vigente intacto.

    Si el plan cambió desde que se generó la propuesta (o el reloj avanzó demasiado), aprobarla
    no la aplica a ciegas: se marca obsoleta y se genera una propuesta nueva con la situación
    actual, que el despachador debe volver a confirmar.
    """

    def __init__(
        self,
        core: RoutingCore,
        planner: ReroutePlanner,
        sim_clock: SimulationClockPort | None = None,
    ) -> None:
        self._core = core
        self._planner = planner
        self._sim_clock = sim_clock

    def execute(
        self, actor: str, proposal_id: str, approve: bool, comment: str = ""
    ) -> DecisionResult:
        core = self._core
        proposal = core.repo.get_proposal(proposal_id)
        if proposal is None:
            raise NotFoundError("La propuesta no existe.")
        if proposal.status is not ProposalStatus.PENDING:
            raise ConflictError("La propuesta ya fue resuelta o quedó obsoleta.")
        now = core.clock.now()
        comment = comment.strip()[:500]

        if not approve:
            rejected = replace(
                proposal,
                status=ProposalStatus.REJECTED,
                decided_by=actor,
                decided_at=now,
                decision_comment=comment,
            )
            core.repo.save_proposal(rejected)
            self._set_outcome(rejected, f"Rechazada por {actor}")
            return DecisionResult(
                rejected, None, None, "Propuesta rechazada; el plan vigente no cambió."
            )

        active = core.repo.active_plan()
        plan = proposal.proposed_plan
        stale = (
            active is None
            or active.version != proposal.base_version
            or core.now_min() - proposal.created_minute > STALE_AFTER_MIN
        )
        if plan is None:  # pragma: no cover - solo hay propuestas PENDING con plan
            raise ConflictError("La propuesta no tiene cambios que aplicar.")
        if stale:
            return self._refresh(actor, proposal)

        applied = replace(plan, created_at=now, created_by=actor)
        core.repo.add_plan(applied)
        approved = replace(
            proposal,
            status=ProposalStatus.APPROVED,
            decided_by=actor,
            decided_at=now,
            decision_comment=comment,
            applied_version=applied.version,
        )
        core.repo.save_proposal(approved)
        self._set_outcome(approved, f"Aprobada por {actor}: plan versión {applied.version}")
        return DecisionResult(
            approved, applied, None, f"Plan actualizado a la versión {applied.version}."
        )

    # ----------------------------------------------------------------- privados
    def _refresh(self, actor: str, old: RerouteProposal) -> DecisionResult:
        core = self._core
        event = next((e for e in core.repo.events() if e.id == old.event_id), None)
        if event is None:  # pragma: no cover - el evento siempre existe
            raise NotFoundError("El evento de la propuesta no existe.")
        superseded = replace(old, status=ProposalStatus.SUPERSEDED)
        core.repo.save_proposal(superseded)
        draft = self._planner.propose(event, actor)
        _, fresh = store_proposal(core, event, draft, self._sim_clock)
        return DecisionResult(
            superseded,
            None,
            fresh,
            "La situación cambió desde que se generó la propuesta: se recalculó. "
            "Revise la propuesta nueva y confirme de nuevo.",
        )

    def _set_outcome(self, proposal: RerouteProposal, text: str) -> None:
        events = {e.id: e for e in self._core.repo.events()}
        event = events.get(proposal.event_id)
        if event is not None:
            self._core.repo.update_event(replace(event, outcome=text))
