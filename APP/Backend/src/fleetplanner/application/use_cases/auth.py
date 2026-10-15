"""Casos de uso de autenticación: Login, RefreshSession, Logout y AuthenticateRequest."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from fleetplanner.application.dto.security import (
    AuditEvent,
    AuditOutcome,
    LoginCommand,
    Session,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import (
    AuditLogPort,
    PasswordHasherPort,
    RateLimiterPort,
    RefreshTokenStorePort,
    TenantRegistryPort,
    TokenServicePort,
    UserRepositoryPort,
)
from fleetplanner.domain.shared.errors import (
    AuthenticationError,
    RateLimitedError,
    TenantSuspendedError,
)
from fleetplanner.domain.tenancy.credentials import LockoutPolicy
from fleetplanner.domain.tenancy.models import Principal, Tenant, User

# Mensaje único para cualquier fallo de credenciales: no revela si el usuario existe.
GENERIC_LOGIN_ERROR = "Credenciales inválidas o cuenta bloqueada temporalmente."
SESSION_ERROR = "La sesión no es válida o expiró. Inicie sesión de nuevo."


def _principal_for(user: User, tenant: Tenant | None) -> Principal:
    return Principal(
        user_id=user.id,
        username=user.username,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_slug=tenant.slug if tenant else None,
        tenant_name=tenant.name if tenant else None,
        vehicle_id=user.attributes.get("vehicle_id"),
    )


class Login:
    def __init__(
        self,
        tenants: TenantRegistryPort,
        users: UserRepositoryPort,
        hasher: PasswordHasherPort,
        tokens: TokenServicePort,
        refresh_store: RefreshTokenStorePort,
        audit: AuditLogPort,
        limiter: RateLimiterPort,
        clock: ClockPort,
        lockout: LockoutPolicy | None = None,
        login_limit: int = 10,
        ip_limit: int = 40,
        window_seconds: int = 60,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._refresh = refresh_store
        self._audit = audit
        self._limiter = limiter
        self._clock = clock
        self._lockout = lockout or LockoutPolicy()
        self._login_limit = login_limit
        self._ip_limit = ip_limit
        self._window = window_seconds

    def execute(self, command: LoginCommand) -> Session:
        now = self._clock.now()
        slug = (command.tenant_slug or "").strip().lower() or None
        username = command.username.strip()

        # Límite de tasa por cuenta (empresa+usuario) y por origen: frena la fuerza bruta.
        if not self._limiter.allow(
            f"login:{slug}:{username.lower()}", self._login_limit, self._window
        ) or not self._limiter.allow(
            f"login-ip:{command.client_key}", self._ip_limit, self._window
        ):
            self._record(now, AuditOutcome.DENIED, None, username, {"reason": "rate_limited"})
            raise RateLimitedError("Demasiados intentos. Espere un momento e intente de nuevo.")

        tenant = self._tenants.get_by_slug(slug) if slug else None
        if slug and tenant is None:
            self._hasher.verify_dummy(command.password)
            self._record(now, AuditOutcome.FAILURE, None, username, {"reason": "unknown_tenant"})
            raise AuthenticationError(GENERIC_LOGIN_ERROR)

        user = self._users.find_by_login(tenant.id if tenant else None, username)
        if user is None or not user.active:
            self._hasher.verify_dummy(command.password)
            self._record(
                now, AuditOutcome.FAILURE, tenant, username, {"reason": "unknown_or_inactive"}
            )
            raise AuthenticationError(GENERIC_LOGIN_ERROR)

        if LockoutPolicy.is_locked(user.locked_until, now):
            self._hasher.verify_dummy(command.password)
            self._record(now, AuditOutcome.DENIED, tenant, username, {"reason": "locked"}, user)
            raise AuthenticationError(GENERIC_LOGIN_ERROR)

        if not self._hasher.verify(user.password_hash, command.password):
            failed = user.failed_attempts + 1
            locked_until = self._lockout.locked_until_after_failure(failed, now)
            self._users.save(replace(user, failed_attempts=failed, locked_until=locked_until))
            self._record(
                now, AuditOutcome.FAILURE, tenant, username, {"reason": "bad_password"}, user
            )
            raise AuthenticationError(GENERIC_LOGIN_ERROR)

        # Contraseña correcta: recién ahora se informa de una empresa suspendida.
        if tenant is not None and not tenant.is_active:
            self._record(
                now, AuditOutcome.DENIED, tenant, username, {"reason": "tenant_suspended"}, user
            )
            raise TenantSuspendedError("La empresa está suspendida. Contacte al administrador.")

        self._users.save(replace(user, failed_attempts=0, locked_until=None))
        access = self._tokens.issue_access_token(
            user.id, str(user.tenant_id) if user.tenant_id else None, user.role
        )
        refresh = self._refresh.issue(user.id)
        self._record(now, AuditOutcome.SUCCESS, tenant, username, {}, user)
        return Session(_principal_for(user, tenant), user.display_name, access, refresh)

    def _record(
        self,
        at: datetime,
        outcome: AuditOutcome,
        tenant: Tenant | None,
        username: str,
        detail: dict[str, str],
        user: User | None = None,
    ) -> None:
        self._audit.record(
            AuditEvent(
                at=at,
                action="auth.login",
                outcome=outcome,
                tenant_id=str(tenant.id) if tenant else None,
                actor_user_id=user.id if user else None,
                actor_username=username[:80],
                detail=detail,
            )
        )


class AuthenticateRequest:
    """Convierte un access token en una `Principal` verificada contra los datos guardados.

    El token solo prueba que el servidor lo emitió; el rol, la pertenencia al tenant y el estado
    del usuario/empresa se vuelven a leer del almacén en cada solicitud.
    """

    def __init__(
        self,
        tenants: TenantRegistryPort,
        users: UserRepositoryPort,
        tokens: TokenServicePort,
        refresh_store: RefreshTokenStorePort,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._tokens = tokens
        self._refresh = refresh_store

    def execute(self, access_token: str) -> Principal:
        claims = self._tokens.verify_access_token(access_token)
        if self._refresh.is_access_revoked(claims.jti):
            raise AuthenticationError(SESSION_ERROR)
        user = self._users.get(claims.user_id)
        if user is None or not user.active:
            raise AuthenticationError(SESSION_ERROR)
        claim_tenant = claims.tenant_id
        user_tenant = str(user.tenant_id) if user.tenant_id else None
        if claim_tenant != user_tenant or claims.role is not user.role:
            raise AuthenticationError(SESSION_ERROR)
        tenant: Tenant | None = None
        if user.tenant_id is not None:
            tenant = self._tenants.get_by_id(user.tenant_id)
            if tenant is None:
                raise AuthenticationError(SESSION_ERROR)
            if not tenant.is_active:
                raise TenantSuspendedError("La empresa está suspendida.")
        return _principal_for(user, tenant)


class RefreshSession:
    def __init__(
        self,
        tenants: TenantRegistryPort,
        users: UserRepositoryPort,
        tokens: TokenServicePort,
        refresh_store: RefreshTokenStorePort,
        audit: AuditLogPort,
        clock: ClockPort,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._tokens = tokens
        self._refresh = refresh_store
        self._audit = audit
        self._clock = clock

    def execute(self, refresh_token: str) -> Session:
        user_id, grant = self._refresh.rotate(refresh_token)
        user = self._users.get(user_id)
        if user is None or not user.active:
            self._refresh.revoke(grant.token)
            raise AuthenticationError(SESSION_ERROR)
        tenant: Tenant | None = None
        if user.tenant_id is not None:
            tenant = self._tenants.get_by_id(user.tenant_id)
            if tenant is None or not tenant.is_active:
                self._refresh.revoke(grant.token)
                raise AuthenticationError(SESSION_ERROR)
        access = self._tokens.issue_access_token(
            user.id, str(user.tenant_id) if user.tenant_id else None, user.role
        )
        self._audit.record(
            AuditEvent(
                at=self._clock.now(),
                action="auth.refresh",
                outcome=AuditOutcome.SUCCESS,
                tenant_id=str(user.tenant_id) if user.tenant_id else None,
                actor_user_id=user.id,
                actor_username=user.username,
            )
        )
        return Session(_principal_for(user, tenant), user.display_name, access, grant)


class Logout:
    def __init__(
        self,
        authenticate: AuthenticateRequest,
        tokens: TokenServicePort,
        refresh_store: RefreshTokenStorePort,
        audit: AuditLogPort,
        clock: ClockPort,
    ) -> None:
        self._authenticate = authenticate
        self._tokens = tokens
        self._refresh = refresh_store
        self._audit = audit
        self._clock = clock

    def execute(self, access_token: str, refresh_token: str | None) -> None:
        """Revoca el access token (hasta su expiración) y el refresh token de la sesión."""
        principal = self._authenticate.execute(access_token)
        claims = self._tokens.verify_access_token(access_token)
        self._refresh.revoke_access(claims.jti, claims.expires_at)
        if refresh_token:
            self._refresh.revoke(refresh_token)
        self._audit.record(
            AuditEvent(
                at=self._clock.now(),
                action="auth.logout",
                outcome=AuditOutcome.SUCCESS,
                tenant_id=str(principal.tenant_id) if principal.tenant_id else None,
                actor_user_id=principal.user_id,
                actor_username=principal.username,
            )
        )
