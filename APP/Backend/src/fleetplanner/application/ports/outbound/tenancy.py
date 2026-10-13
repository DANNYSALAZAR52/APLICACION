"""Puertos de tenancy, usuarios, seguridad, auditoría y límites de tasa."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from fleetplanner.application.dto.security import (
    AccessToken,
    AuditEvent,
    RefreshGrant,
    TokenClaims,
)
from fleetplanner.application.dto.workspace import TenantWorkspace
from fleetplanner.domain.tenancy.models import Principal, Role, Tenant, TenantId, User


class TenantRegistryPort(Protocol):
    """Registro central de tenants (plano de control)."""

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None: ...

    def get_by_slug(self, slug: str) -> Tenant | None: ...

    def list_all(self) -> list[Tenant]: ...

    def save(self, tenant: Tenant) -> None: ...


class UserRepositoryPort(Protocol):
    def find_by_login(self, tenant_id: TenantId | None, username: str) -> User | None: ...

    def get(self, user_id: str) -> User | None: ...

    def save(self, user: User) -> None: ...

    def list_for_tenant(self, tenant_id: TenantId) -> list[User]: ...


class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...

    def verify_dummy(self, password: str) -> None:
        """Gasta el mismo tiempo que una verificación real (evita enumerar usuarios)."""
        ...


class TokenServicePort(Protocol):
    def issue_access_token(
        self, user_id: str, tenant_id: str | None, role: Role
    ) -> AccessToken: ...

    def verify_access_token(self, token: str) -> TokenClaims:
        """Valida firma y expiración. Lanza `AuthenticationError` si algo falla."""
        ...


class RefreshTokenStorePort(Protocol):
    def issue(self, user_id: str) -> RefreshGrant: ...

    def rotate(self, token: str) -> tuple[str, RefreshGrant]:
        """Consume un refresh token y entrega otro nuevo. Devuelve (user_id, nuevo).

        Reutilizar un token ya rotado revoca toda la familia y lanza `AuthenticationError`.
        """
        ...

    def revoke(self, token: str) -> None: ...

    def revoke_all_for_user(self, user_id: str) -> None: ...

    def revoke_access(self, jti: str, expires_at: datetime) -> None: ...

    def is_access_revoked(self, jti: str) -> bool: ...


class AuditLogPort(Protocol):
    def record(self, event: AuditEvent) -> None: ...

    def list_events(self, tenant_id: str | None, limit: int = 100) -> list[AuditEvent]:
        """``tenant_id=None`` devuelve todos los eventos (solo para superadministrador)."""
        ...


class RateLimiterPort(Protocol):
    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        """Registra un intento y dice si sigue dentro del límite."""
        ...


class TenantWorkspaceProvider(Protocol):
    """Entrega los datos/casos de uso del tenant de la identidad autenticada."""

    def workspace_for(self, principal: Principal) -> TenantWorkspace: ...
