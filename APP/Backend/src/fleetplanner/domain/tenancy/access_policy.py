"""RBAC: permisos por rol, denegación por defecto."""

from __future__ import annotations

from enum import StrEnum

from fleetplanner.domain.shared.errors import PermissionDeniedError
from fleetplanner.domain.tenancy.models import Principal, Role


class Permission(StrEnum):
    CAPACITY_READ = "capacity:read"
    CAPACITY_RECALCULATE = "capacity:recalculate"
    ROUTING_READ = "routing:read"
    ROUTING_EVENTS = "routing:events"
    DRIVER_ROUTE = "driver:route"
    MASTER_DATA_MANAGE = "master_data:manage"
    PATTERNS_READ = "patterns:read"
    INDICATORS_READ = "indicators:read"
    AUDIT_READ = "audit:read"
    TENANTS_MANAGE = "tenants:manage"


_GRANTS: dict[Role, frozenset[Permission]] = {
    Role.MANAGEMENT: frozenset(
        {
            Permission.CAPACITY_READ,
            Permission.CAPACITY_RECALCULATE,
            Permission.PATTERNS_READ,
            Permission.INDICATORS_READ,
        }
    ),
    Role.DISPATCHER: frozenset(
        {
            Permission.ROUTING_READ,
            Permission.ROUTING_EVENTS,
            Permission.INDICATORS_READ,
            Permission.PATTERNS_READ,
        }
    ),
    Role.DRIVER: frozenset({Permission.DRIVER_ROUTE}),
    Role.TENANT_ADMIN: frozenset(
        {
            Permission.CAPACITY_READ,
            Permission.MASTER_DATA_MANAGE,
            Permission.AUDIT_READ,
        }
    ),
    Role.SUPER_ADMIN: frozenset({Permission.TENANTS_MANAGE, Permission.AUDIT_READ}),
}


class AccessPolicy:
    """Decide si una identidad tiene un permiso. Todo lo no concedido está denegado."""

    @staticmethod
    def permissions_of(role: Role) -> frozenset[Permission]:
        return _GRANTS.get(role, frozenset())

    @classmethod
    def can(cls, principal: Principal, permission: Permission) -> bool:
        return permission in cls.permissions_of(principal.role)

    @classmethod
    def require(cls, principal: Principal, permission: Permission) -> None:
        if not cls.can(principal, permission):
            raise PermissionDeniedError("No tiene permiso para realizar esta operación.")
