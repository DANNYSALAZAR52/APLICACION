"""Auditoría de las exportaciones generadas (quién exportó qué y cuándo)."""

from __future__ import annotations

from fleetplanner.application.dto.security import AuditEvent, AuditOutcome
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import AuditLogPort
from fleetplanner.domain.tenancy.models import Principal


class RecordExport:
    def __init__(self, audit: AuditLogPort, clock: ClockPort) -> None:
        self._audit = audit
        self._clock = clock

    def execute(self, principal: Principal, resource: str, fmt: str) -> None:
        self._audit.record(
            AuditEvent(
                at=self._clock.now(),
                action="export.generate",
                outcome=AuditOutcome.SUCCESS,
                tenant_id=str(principal.tenant_id) if principal.tenant_id else None,
                actor_user_id=principal.user_id,
                actor_username=principal.username,
                resource=resource,
                detail={"formato": fmt},
            )
        )
