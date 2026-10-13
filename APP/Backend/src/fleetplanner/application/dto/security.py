"""DTO de identidad, sesiones y auditoría."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from fleetplanner.domain.tenancy.models import Principal, Role, Tenant


@dataclass(frozen=True)
class TokenClaims:
    """Claims de un access token ya validado (firma, expiración). Aún NO es una identidad:
    la identidad se confirma contra el usuario y el tenant guardados."""

    user_id: str
    tenant_id: str | None
    role: Role
    jti: str
    expires_at: datetime


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class RefreshGrant:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class LoginCommand:
    tenant_slug: str | None
    username: str
    password: str = field(repr=False)  # nunca se imprime en logs/trazas
    client_key: str = "unknown"


@dataclass(frozen=True)
class Session:
    principal: Principal
    display_name: str
    access: AccessToken
    refresh: RefreshGrant


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILURE = "failure"


@dataclass(frozen=True)
class AuditEvent:
    """Registro de auditoría: quién, qué, cuándo, tenant y resultado. Sin secretos."""

    at: datetime
    action: str
    outcome: AuditOutcome
    tenant_id: str | None
    actor_user_id: str | None
    actor_username: str | None
    resource: str = ""
    detail: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TenantSummary:
    tenant: Tenant
    user_count: int


@dataclass(frozen=True)
class ProvisionResult:
    tenant: Tenant
    created: bool
    admin_username: str | None
    initial_admin_password: str | None = field(default=None, repr=False)
