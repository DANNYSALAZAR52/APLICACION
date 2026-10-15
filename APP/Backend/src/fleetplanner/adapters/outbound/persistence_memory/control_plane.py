"""DEMO-ONLY: registro de tenants, usuarios, sesiones, auditoría y límite de tasa en memoria."""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta

from fleetplanner.application.dto.security import AuditEvent, RefreshGrant
from fleetplanner.application.dto.workspace import TenantWorkspace
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import TenantRegistryPort
from fleetplanner.domain.shared.errors import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    TenantSuspendedError,
)
from fleetplanner.domain.tenancy.models import Principal, Tenant, TenantId, User


class InMemoryTenantRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, Tenant] = {}
        self._lock = threading.Lock()

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        with self._lock:
            return self._by_id.get(tenant_id.value)

    def get_by_slug(self, slug: str) -> Tenant | None:
        with self._lock:
            return next((t for t in self._by_id.values() if t.slug == slug), None)

    def list_all(self) -> list[Tenant]:
        with self._lock:
            return list(self._by_id.values())

    def save(self, tenant: Tenant) -> None:
        with self._lock:
            self._by_id[tenant.id.value] = tenant


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}
        self._lock = threading.Lock()

    def find_by_login(self, tenant_id: TenantId | None, username: str) -> User | None:
        wanted = username.strip().lower()
        with self._lock:
            return next(
                (
                    u
                    for u in self._by_id.values()
                    if u.tenant_id == tenant_id and u.username.lower() == wanted
                ),
                None,
            )

    def get(self, user_id: str) -> User | None:
        with self._lock:
            return self._by_id.get(user_id)

    def save(self, user: User) -> None:
        with self._lock:
            self._by_id[user.id] = user

    def list_for_tenant(self, tenant_id: TenantId) -> list[User]:
        with self._lock:
            return [u for u in self._by_id.values() if u.tenant_id == tenant_id]


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InMemoryRefreshTokenStore:
    """Refresh tokens opacos con rotación y detección de reutilización.

    Solo se guarda el hash SHA-256 del token. Si se presenta un token ya rotado se asume robo
    y se revoca toda su familia.
    """

    def __init__(self, clock: ClockPort, ttl: timedelta = timedelta(hours=8)) -> None:
        self._clock = clock
        self._ttl = ttl
        self._records: dict[str, dict[str, object]] = {}
        self._revoked_access: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def _new(self, user_id: str, family: str) -> RefreshGrant:
        raw = secrets.token_urlsafe(48)
        expires = self._clock.now() + self._ttl
        self._records[_digest(raw)] = {
            "user_id": user_id,
            "family": family,
            "expires_at": expires,
            "used": False,
        }
        return RefreshGrant(raw, expires)

    def issue(self, user_id: str) -> RefreshGrant:
        with self._lock:
            return self._new(user_id, secrets.token_hex(8))

    def rotate(self, token: str) -> tuple[str, RefreshGrant]:
        with self._lock:
            record = self._records.get(_digest(token))
            if record is None:
                raise AuthenticationError("La sesión no es válida.")
            family = str(record["family"])
            if record["used"]:
                self._revoke_family(family)
                raise AuthenticationError("La sesión no es válida.")
            expires_at = record["expires_at"]
            if not isinstance(expires_at, datetime) or expires_at <= self._clock.now():
                raise AuthenticationError("La sesión expiró.")
            record["used"] = True
            user_id = str(record["user_id"])
            return user_id, self._new(user_id, family)

    def _revoke_family(self, family: str) -> None:
        for key in [k for k, r in self._records.items() if r["family"] == family]:
            del self._records[key]

    def revoke(self, token: str) -> None:
        with self._lock:
            record = self._records.get(_digest(token))
            if record is not None:
                self._revoke_family(str(record["family"]))

    def revoke_all_for_user(self, user_id: str) -> None:
        with self._lock:
            for key in [k for k, r in self._records.items() if r["user_id"] == user_id]:
                del self._records[key]

    def revoke_access(self, jti: str, expires_at: datetime) -> None:
        with self._lock:
            self._revoked_access[jti] = expires_at

    def is_access_revoked(self, jti: str) -> bool:
        with self._lock:
            now = self._clock.now()
            for key in [k for k, exp in self._revoked_access.items() if exp <= now]:
                del self._revoked_access[key]  # ya expiró por sí solo
            return jti in self._revoked_access


class InMemoryAuditLog:
    """Auditoría acotada en memoria (los últimos eventos)."""

    def __init__(self, capacity: int = 5000) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def record(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def list_events(self, tenant_id: str | None, limit: int = 100) -> list[AuditEvent]:
        with self._lock:
            events = [e for e in self._events if tenant_id is None or e.tenant_id == tenant_id]
        return list(reversed(events))[:limit]


class InMemoryRateLimiter:
    """Ventana deslizante por clave."""

    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock
        self._hits: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = self._clock.now()
        floor = now - timedelta(seconds=window_seconds)
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= floor:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


class InMemoryTenantWorkspaceProvider:
    """Crea (una vez) y entrega el espacio de trabajo del tenant de la identidad.

    La clave de caché es el tenant de la `Principal` autenticada; no hay parámetro libre.
    """

    def __init__(
        self, registry: TenantRegistryPort, factory: Callable[[Tenant], TenantWorkspace]
    ) -> None:
        self._registry = registry
        self._factory = factory
        self._cache: dict[str, TenantWorkspace] = {}
        self._lock = threading.Lock()

    def active_workspaces(self) -> list[tuple[Tenant, TenantWorkspace]]:
        with self._lock:
            cached = list(self._cache.items())
        result: list[tuple[Tenant, TenantWorkspace]] = []
        for tenant_id, workspace in cached:
            tenant = self._registry.get_by_id(TenantId(tenant_id))
            if tenant is not None and tenant.is_active:
                result.append((tenant, workspace))
        return result

    def workspace_for(self, principal: Principal) -> TenantWorkspace:
        if principal.tenant_id is None:
            raise PermissionDeniedError("La identidad no pertenece a ninguna empresa.")
        tenant = self._registry.get_by_id(principal.tenant_id)
        if tenant is None:
            raise NotFoundError("La empresa no existe.")
        if not tenant.is_active:
            raise TenantSuspendedError("La empresa está suspendida.")
        with self._lock:
            workspace = self._cache.get(tenant.id.value)
            if workspace is None:
                workspace = self._factory(tenant)
                self._cache[tenant.id.value] = workspace
            return workspace
