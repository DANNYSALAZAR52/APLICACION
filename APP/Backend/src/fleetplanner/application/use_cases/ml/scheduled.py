"""Reentrenamiento programado de los modelos (DOCS.MD §13.5): corre solo, por empresa."""

from __future__ import annotations

from fleetplanner.application.dto.security import AuditEvent, AuditOutcome
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import AuditLogPort, TenantWorkspaceCatalog

SCHEDULER_ACTOR = "sistema (tarea programada)"


class ScheduledRetraining:
    """Reentrena las empresas activas cuyos modelos superan el intervalo de reentrenamiento.

    El contexto de tenant sale del registro central y cada empresa se procesa solo con SU
    servicio de ML. Un fallo en una empresa se audita y no frena a las demás. Nunca entrena en
    frío: el primer entrenamiento ocurre cuando alguien consulta los patrones.
    """

    def __init__(
        self, catalog: TenantWorkspaceCatalog, audit: AuditLogPort, clock: ClockPort
    ) -> None:
        self._catalog = catalog
        self._audit = audit
        self._clock = clock

    def execute(self) -> int:
        """Devuelve cuántas empresas se reentrenaron."""
        retrained = 0
        for tenant, workspace in self._catalog.active_workspaces():
            if workspace.ml is None:
                continue
            try:
                done = workspace.ml.retrain_if_due()
            except Exception:  # noqa: BLE001 - una empresa con error no debe frenar a las demás
                self._record(str(tenant.id), AuditOutcome.FAILURE)
                continue
            if done:
                retrained += 1
                self._record(str(tenant.id), AuditOutcome.SUCCESS)
        return retrained

    def _record(self, tenant_id: str, outcome: AuditOutcome) -> None:
        self._audit.record(
            AuditEvent(
                at=self._clock.now(),
                action="patterns.retrain.scheduled",
                outcome=outcome,
                tenant_id=tenant_id,
                actor_user_id=None,
                actor_username=SCHEDULER_ACTOR,
                resource="patterns",
            )
        )
