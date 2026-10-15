"""Casos de uso de ML expuestos a los adaptadores de entrada: autorizan y auditan.

La empresa sale siempre de la `Principal`; no existe parámetro para elegir otra.
"""

from __future__ import annotations

from fleetplanner.application.dto.ml import PatternsReport
from fleetplanner.application.dto.security import AuditEvent, AuditOutcome
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import (
    AuditLogPort,
    RateLimiterPort,
    TenantWorkspaceProvider,
)
from fleetplanner.application.use_cases.ml.service import MlService
from fleetplanner.domain.shared.errors import (
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
)
from fleetplanner.domain.tenancy.access_policy import AccessPolicy, Permission
from fleetplanner.domain.tenancy.models import Principal

RETRAIN_LIMIT_PER_MINUTE = 3


class _MlAccess:
    def __init__(
        self,
        workspaces: TenantWorkspaceProvider,
        audit: AuditLogPort,
        clock: ClockPort,
    ) -> None:
        self._workspaces = workspaces
        self._audit = audit
        self._clock = clock

    def _service(self, principal: Principal, permission: Permission, action: str) -> MlService:
        if not AccessPolicy.can(principal, permission):
            self._record(principal, action, AuditOutcome.DENIED)
            raise PermissionDeniedError("No tiene permiso para esta operación de patrones.")
        ml = self._workspaces.workspace_for(principal).ml
        if ml is None:
            raise NotFoundError("Los modelos de ML no están disponibles para esta empresa.")
        return ml

    def _record(
        self,
        principal: Principal,
        action: str,
        outcome: AuditOutcome,
        detail: dict[str, str] | None = None,
    ) -> None:
        self._audit.record(
            AuditEvent(
                at=self._clock.now(),
                action=action,
                outcome=outcome,
                tenant_id=str(principal.tenant_id) if principal.tenant_id else None,
                actor_user_id=principal.user_id,
                actor_username=principal.username,
                resource="patterns",
                detail=detail or {},
            )
        )


class GetPatterns(_MlAccess):
    """`DetectPatterns`: pronósticos, anomalías, riesgo de retraso y segmentos de la empresa."""

    def execute(self, principal: Principal) -> PatternsReport:
        ml = self._service(principal, Permission.PATTERNS_READ, "patterns.view")
        report = ml.report()
        self._record(principal, "patterns.view", AuditOutcome.SUCCESS)
        return report


class RetrainModels(_MlAccess):
    """`TrainModels` disparado a mano para la empresa de la identidad."""

    def __init__(
        self,
        workspaces: TenantWorkspaceProvider,
        audit: AuditLogPort,
        clock: ClockPort,
        limiter: RateLimiterPort | None = None,
    ) -> None:
        super().__init__(workspaces, audit, clock)
        self._limiter = limiter

    def execute(self, principal: Principal) -> PatternsReport:
        ml = self._service(principal, Permission.PATTERNS_TRAIN, "patterns.retrain")
        if self._limiter is not None:
            key = f"patterns:retrain:{principal.tenant_id}:{principal.user_id}"
            if not self._limiter.allow(key, RETRAIN_LIMIT_PER_MINUTE, 60):
                self._record(
                    principal, "patterns.retrain", AuditOutcome.DENIED, {"motivo": "límite"}
                )
                raise RateLimitedError("Demasiados reentrenamientos seguidos; espere un momento.")
        models = ml.train()
        report = ml.report()
        self._record(
            principal,
            "patterns.retrain",
            AuditOutcome.SUCCESS,
            {"versiones": ",".join(f"{m.name}:v{m.version}" for m in models)},
        )
        return report
