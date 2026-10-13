"""Acceso autorizado al tablero de capacidad del tenant de la identidad."""

from __future__ import annotations

from fleetplanner.application.dto.capacity import CapacityDashboard
from fleetplanner.application.dto.security import AuditEvent, AuditOutcome
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import AuditLogPort, TenantWorkspaceProvider
from fleetplanner.domain.shared.errors import PermissionDeniedError
from fleetplanner.domain.tenancy.access_policy import AccessPolicy, Permission
from fleetplanner.domain.tenancy.models import Principal


class GetCapacityDashboard:
    def __init__(
        self, workspaces: TenantWorkspaceProvider, audit: AuditLogPort, clock: ClockPort
    ) -> None:
        self._workspaces = workspaces
        self._audit = audit
        self._clock = clock

    def execute(self, principal: Principal) -> CapacityDashboard:
        if not AccessPolicy.can(principal, Permission.CAPACITY_READ):
            self._record(principal, AuditOutcome.DENIED)
            raise PermissionDeniedError("No tiene permiso para ver la capacidad de flota.")
        # El tenant sale de la identidad autenticada; la función no recibe ningún identificador.
        dashboard = self._workspaces.workspace_for(principal).capacity_dashboard.execute()
        self._record(principal, AuditOutcome.SUCCESS)
        return dashboard

    def _record(self, principal: Principal, outcome: AuditOutcome) -> None:
        self._audit.record(
            AuditEvent(
                at=self._clock.now(),
                action="capacity.dashboard.view",
                outcome=outcome,
                tenant_id=str(principal.tenant_id) if principal.tenant_id else None,
                actor_user_id=principal.user_id,
                actor_username=principal.username,
                resource="capacity/dashboard",
            )
        )
