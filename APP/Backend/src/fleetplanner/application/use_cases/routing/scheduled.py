"""Tarea programada de seguimiento (DOCS.MD §7.4): corre sola, sin una solicitud de usuario."""

from __future__ import annotations

from fleetplanner.application.dto.security import AuditEvent, AuditOutcome
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import AuditLogPort, TenantWorkspaceCatalog

SCHEDULER_ACTOR = "sistema (tarea programada)"


class ScheduledTracking:
    """Recorre las empresas con un día en curso y ejecuta su seguimiento.

    El contexto de tenant viene del registro central y cada empresa se procesa únicamente con SU
    espacio de trabajo. Los días con el reloj en pausa se omiten (no pasa el tiempo). Un fallo en
    una empresa no detiene a las demás.
    """

    def __init__(
        self, catalog: TenantWorkspaceCatalog, audit: AuditLogPort, clock: ClockPort
    ) -> None:
        self._catalog = catalog
        self._audit = audit
        self._clock = clock

    def execute(self) -> int:
        """Devuelve cuántas propuestas nuevas se generaron en total."""
        created = 0
        for tenant, workspace in self._catalog.active_workspaces():
            routing = workspace.routing
            try:
                with routing.lock:
                    if routing.core.repo.active_plan() is None or routing.is_paused():
                        continue
                    proposals = routing.track.execute()
            except Exception:  # noqa: BLE001 - una empresa con error no debe frenar a las demás
                self._audit.record(
                    AuditEvent(
                        at=self._clock.now(),
                        action="routing.tracking.scheduled",
                        outcome=AuditOutcome.FAILURE,
                        tenant_id=str(tenant.id),
                        actor_user_id=None,
                        actor_username=SCHEDULER_ACTOR,
                        resource="routing/tracking",
                    )
                )
                continue
            for proposal in proposals:
                created += 1
                self._audit.record(
                    AuditEvent(
                        at=self._clock.now(),
                        action="routing.proposal.auto",
                        outcome=AuditOutcome.SUCCESS,
                        tenant_id=str(tenant.id),
                        actor_user_id=None,
                        actor_username=SCHEDULER_ACTOR,
                        resource=f"routing/proposals/{proposal.id}",
                        detail={"reason": proposal.reason},
                    )
                )
        return created
