"""Administración de tenants (solo superadministrador) y consulta de auditoría."""

from __future__ import annotations

import uuid

from fleetplanner.application.dto.security import (
    AuditEvent,
    AuditOutcome,
    ProvisionResult,
    TenantSummary,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import (
    AuditLogPort,
    PasswordHasherPort,
    RefreshTokenStorePort,
    TenantRegistryPort,
    UserRepositoryPort,
)
from fleetplanner.domain.shared.errors import ConflictError, NotFoundError
from fleetplanner.domain.tenancy.access_policy import AccessPolicy, Permission
from fleetplanner.domain.tenancy.credentials import generate_password
from fleetplanner.domain.tenancy.models import (
    Principal,
    Role,
    Tenant,
    TenantId,
    TenantStatus,
    User,
)


def _audit(
    audit: AuditLogPort,
    clock: ClockPort,
    principal: Principal,
    action: str,
    resource: str,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    detail: dict[str, str] | None = None,
) -> None:
    audit.record(
        AuditEvent(
            at=clock.now(),
            action=action,
            outcome=outcome,
            tenant_id=str(principal.tenant_id) if principal.tenant_id else None,
            actor_user_id=principal.user_id,
            actor_username=principal.username,
            resource=resource,
            detail=detail or {},
        )
    )


class ListTenants:
    def __init__(
        self,
        tenants: TenantRegistryPort,
        users: UserRepositoryPort,
        audit: AuditLogPort,
        clock: ClockPort,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._audit = audit
        self._clock = clock

    def execute(self, principal: Principal) -> list[TenantSummary]:
        AccessPolicy.require(principal, Permission.TENANTS_MANAGE)
        summaries = [
            TenantSummary(t, len(self._users.list_for_tenant(t.id)))
            for t in sorted(self._tenants.list_all(), key=lambda t: t.slug)
        ]
        _audit(self._audit, self._clock, principal, "tenant.list", "tenants")
        return summaries


class SetTenantStatus:
    """Suspende o reactiva una empresa. Al suspender se revocan las sesiones de sus usuarios."""

    def __init__(
        self,
        tenants: TenantRegistryPort,
        users: UserRepositoryPort,
        refresh_store: RefreshTokenStorePort,
        audit: AuditLogPort,
        clock: ClockPort,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._refresh = refresh_store
        self._audit = audit
        self._clock = clock

    def execute(self, principal: Principal, slug: str, status: TenantStatus) -> Tenant:
        AccessPolicy.require(principal, Permission.TENANTS_MANAGE)
        tenant = self._tenants.get_by_slug(slug)
        if tenant is None:
            raise NotFoundError("La empresa indicada no existe.")
        updated = tenant.suspended() if status is TenantStatus.SUSPENDED else tenant.reactivated()
        self._tenants.save(updated)
        if status is TenantStatus.SUSPENDED:
            for user in self._users.list_for_tenant(tenant.id):
                self._refresh.revoke_all_for_user(user.id)
        _audit(
            self._audit,
            self._clock,
            principal,
            "tenant.suspend" if status is TenantStatus.SUSPENDED else "tenant.reactivate",
            tenant.slug,
        )
        return updated


class ProvisionTenant:
    """Crea una empresa y su administrador. Idempotente por ``slug``.

    Repetir la misma solicitud (mismo slug y nombre) devuelve la empresa existente sin crear nada
    nuevo; el mismo slug con otro nombre es un conflicto. No hay fallos parciales visibles: la
    empresa se guarda solo después de crear el administrador y, si algo falla antes, no queda
    ningún registro (compensación implícita por orden de operaciones).
    """

    def __init__(
        self,
        tenants: TenantRegistryPort,
        users: UserRepositoryPort,
        hasher: PasswordHasherPort,
        audit: AuditLogPort,
        clock: ClockPort,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._hasher = hasher
        self._audit = audit
        self._clock = clock

    def execute(self, principal: Principal, slug: str, name: str) -> ProvisionResult:
        AccessPolicy.require(principal, Permission.TENANTS_MANAGE)
        slug = slug.strip().lower()
        name = name.strip()
        existing = self._tenants.get_by_slug(slug)
        if existing is not None:
            if existing.name != name:
                raise ConflictError("Ya existe una empresa con ese identificador y otro nombre.")
            return ProvisionResult(existing, created=False, admin_username=None)

        tenant = Tenant(
            id=TenantId(f"t-{uuid.uuid4().hex[:12]}"),
            slug=slug,
            name=name,
            status=TenantStatus.ACTIVE,
            created_at=self._clock.now(),
        )  # valida slug y nombre antes de persistir nada
        password = generate_password()
        admin = User(
            id=uuid.uuid4().hex,
            tenant_id=tenant.id,
            username="admin",
            display_name=f"Administrador de {name}",
            role=Role.TENANT_ADMIN,
            password_hash=self._hasher.hash(password),
        )
        self._users.save(admin)
        self._tenants.save(tenant)
        _audit(self._audit, self._clock, principal, "tenant.provision", slug)
        return ProvisionResult(tenant, True, admin.username, password)


class ListAuditEvents:
    """Administrador de empresa: solo su empresa. Superadministrador: todas."""

    def __init__(self, audit: AuditLogPort) -> None:
        self._audit = audit

    def execute(self, principal: Principal, limit: int = 100) -> list[AuditEvent]:
        AccessPolicy.require(principal, Permission.AUDIT_READ)
        bounded = max(1, min(limit, 500))
        if principal.role is Role.SUPER_ADMIN:
            return self._audit.list_events(None, bounded)
        if principal.tenant_id is None:
            return []
        return self._audit.list_events(str(principal.tenant_id), bounded)
