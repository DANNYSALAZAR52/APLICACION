"""Casos de uso de maestros expuestos a los adaptadores de entrada: autorizan y auditan.

La empresa sale siempre de la `Principal`. Cada cambio queda en la auditoría de la plataforma
(quién, qué y cuándo) y en el historial de la empresa (con el valor anterior y la vigencia).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from fleetplanner.application.dto.masters import (
    CsvApplyResult,
    CsvPreview,
    Listing,
    ParameterView,
    SchemaView,
)
from fleetplanner.application.dto.security import AuditEvent, AuditOutcome
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.masters import ChangeRecord, Row
from fleetplanner.application.ports.outbound.tenancy import (
    AuditLogPort,
    RateLimiterPort,
    TenantWorkspaceProvider,
)
from fleetplanner.application.use_cases.masters.service import MasterDataService
from fleetplanner.domain.shared.errors import PermissionDeniedError, RateLimitedError
from fleetplanner.domain.tenancy.access_policy import AccessPolicy, Permission
from fleetplanner.domain.tenancy.models import Principal


class _MastersAccess:
    def __init__(
        self,
        workspaces: TenantWorkspaceProvider,
        audit: AuditLogPort,
        clock: ClockPort,
        limiter: RateLimiterPort | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._audit = audit
        self._clock = clock
        self._limiter = limiter

    def _service(self, principal: Principal, action: str) -> MasterDataService:
        if not AccessPolicy.can(principal, Permission.MASTER_DATA_MANAGE):
            self._record(principal, action, AuditOutcome.DENIED)
            raise PermissionDeniedError("No tiene permiso para administrar maestros y parámetros.")
        # El espacio de trabajo se resuelve por la identidad autenticada, nunca por un parámetro.
        return self._workspaces.workspace_for(principal).masters

    def _throttle(self, principal: Principal, bucket: str, limit: int) -> None:
        if self._limiter is None:
            return
        key = f"masters:{bucket}:{principal.tenant_id}:{principal.user_id}"
        if not self._limiter.allow(key, limit, 60):
            self._record(
                principal, f"master.{bucket}", AuditOutcome.DENIED, detail={"motivo": "límite"}
            )
            raise RateLimitedError("Demasiadas operaciones seguidas; espere un momento.")

    def _record(
        self,
        principal: Principal,
        action: str,
        outcome: AuditOutcome,
        resource: str = "masters",
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
                resource=resource,
                detail=detail or {},
            )
        )


class GetMasterSchema(_MastersAccess):
    def execute(self, principal: Principal) -> SchemaView:
        return self._service(principal, "master.schema").schema()


class ListMaster(_MastersAccess):
    def execute(self, principal: Principal, entity: str) -> Listing:
        return self._service(principal, "master.list").list_rows(entity)


class CreateMaster(_MastersAccess):
    def execute(self, principal: Principal, entity: str, values: Mapping[str, object]) -> Row:
        service = self._service(principal, "master.create")
        self._throttle(principal, "write", 120)
        row = service.create(principal.username, entity, values)
        spec = service.entity(entity)
        self._record(
            principal, "master.create", AuditOutcome.SUCCESS, f"masters/{entity}/{spec.key_of(row)}"
        )
        return row


class UpdateMaster(_MastersAccess):
    def execute(
        self, principal: Principal, entity: str, key: str, values: Mapping[str, object]
    ) -> Row:
        service = self._service(principal, "master.update")
        self._throttle(principal, "write", 120)
        row = service.update(principal.username, entity, key, values)
        self._record(principal, "master.update", AuditOutcome.SUCCESS, f"masters/{entity}/{key}")
        return row


class DeleteMaster(_MastersAccess):
    def execute(self, principal: Principal, entity: str, key: str) -> None:
        service = self._service(principal, "master.delete")
        self._throttle(principal, "write", 120)
        service.delete(principal.username, entity, key)
        self._record(principal, "master.delete", AuditOutcome.SUCCESS, f"masters/{entity}/{key}")


class PreviewMasterCsv(_MastersAccess):
    def execute(self, principal: Principal, entity: str, content: str) -> CsvPreview:
        service = self._service(principal, "master.csv.preview")
        self._throttle(principal, "csv", 30)
        return service.preview_csv(entity, content)


class ApplyMasterCsv(_MastersAccess):
    def execute(self, principal: Principal, entity: str, content: str) -> CsvApplyResult:
        service = self._service(principal, "master.csv.apply")
        self._throttle(principal, "csv", 30)
        result = service.apply_csv(principal.username, entity, content)
        self._record(
            principal,
            "master.csv.apply",
            AuditOutcome.SUCCESS,
            f"masters/{entity}",
            {"creados": str(result.created), "actualizados": str(result.updated)},
        )
        return result


class ListParameters(_MastersAccess):
    def execute(self, principal: Principal) -> list[ParameterView]:
        return self._service(principal, "master.parameters").parameters()


class SetParameter(_MastersAccess):
    def execute(
        self,
        principal: Principal,
        key: str,
        value: object,
        valid_from: date | None,
        note: str = "",
    ) -> ParameterView:
        service = self._service(principal, "master.parameter.set")
        self._throttle(principal, "write", 120)
        view = service.set_parameter(principal.username, key, value, valid_from, note)
        self._record(
            principal,
            "master.parameter.set",
            AuditOutcome.SUCCESS,
            f"masters/parameter/{key}",
            {"vigencia": (valid_from or view.valid_from).isoformat()},
        )
        return view


class GetMasterHistory(_MastersAccess):
    def execute(
        self, principal: Principal, limit: int = 100, entity: str | None = None
    ) -> list[ChangeRecord]:
        return self._service(principal, "master.history").history(limit, entity)


class ExportMaster(_MastersAccess):
    def execute(
        self, principal: Principal, entity: str
    ) -> tuple[str, list[str], list[list[object]]]:
        service = self._service(principal, "master.export")
        self._throttle(principal, "csv", 30)
        header, rows = service.export_rows(entity)
        self._record(
            principal,
            "master.export",
            AuditOutcome.SUCCESS,
            f"masters/{entity}",
            {"filas": str(len(rows))},
        )
        return service.entity(entity).plural, header, rows
