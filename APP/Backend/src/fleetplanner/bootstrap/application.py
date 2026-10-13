"""Ensamblado de la aplicación completa (DEMO-ONLY: adaptadores en memoria)."""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.adapters.inbound.http import HttpSettings, create_app
from fleetplanner.adapters.outbound.clock import SystemClock
from fleetplanner.adapters.outbound.demo_data import (
    DEMO_A_SLUG,
    DEMO_B_SLUG,
    capacity_reader_for_slug,
)
from fleetplanner.adapters.outbound.persistence_memory import (
    InMemoryAuditLog,
    InMemoryRateLimiter,
    InMemoryRefreshTokenStore,
    InMemoryTenantRegistry,
    InMemoryTenantWorkspaceProvider,
    InMemoryUserRepository,
)
from fleetplanner.adapters.outbound.security import Argon2PasswordHasher, JwtTokenService
from fleetplanner.adapters.outbound.solver import OrToolsFleetMixSolver
from fleetplanner.application.dto.workspace import TenantWorkspace
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import PasswordHasherPort
from fleetplanner.application.services import ApplicationServices
from fleetplanner.application.use_cases.auth import (
    AuthenticateRequest,
    Login,
    Logout,
    RefreshSession,
)
from fleetplanner.application.use_cases.get_capacity_dashboard import GetCapacityDashboard
from fleetplanner.application.use_cases.tenant_admin import (
    ListAuditEvents,
    ListTenants,
    ProvisionTenant,
    SetTenantStatus,
)
from fleetplanner.bootstrap.container import build_capacity_container
from fleetplanner.bootstrap.settings import Settings
from fleetplanner.domain.tenancy.credentials import generate_password
from fleetplanner.domain.tenancy.models import Role, Tenant, TenantId, TenantStatus, User


@dataclass(frozen=True)
class Application:
    services: ApplicationServices
    tenants: InMemoryTenantRegistry
    users: InMemoryUserRepository
    audit: InMemoryAuditLog
    hasher: PasswordHasherPort
    clock: ClockPort
    settings: Settings


def build_application(
    settings: Settings,
    clock: ClockPort | None = None,
    hasher: PasswordHasherPort | None = None,
) -> Application:
    clock = clock or SystemClock()
    hasher = hasher or Argon2PasswordHasher()
    tenants = InMemoryTenantRegistry()
    users = InMemoryUserRepository()
    audit = InMemoryAuditLog()
    refresh_store = InMemoryRefreshTokenStore(clock)
    limiter = InMemoryRateLimiter(clock)
    tokens = JwtTokenService(settings.jwt_signing_key, clock)
    solver = OrToolsFleetMixSolver()

    def workspace_factory(tenant: Tenant) -> TenantWorkspace:
        # Cada empresa recibe su propio lector, repositorio de resultados y casos de uso.
        container = build_capacity_container(
            reader=capacity_reader_for_slug(tenant.slug), solver=solver, clock=clock
        )
        return TenantWorkspace(tenant.id, container.dashboard)

    workspaces = InMemoryTenantWorkspaceProvider(tenants, workspace_factory)
    authenticate = AuthenticateRequest(tenants, users, tokens, refresh_store)
    services = ApplicationServices(
        login=Login(tenants, users, hasher, tokens, refresh_store, audit, limiter, clock),
        refresh=RefreshSession(tenants, users, tokens, refresh_store, audit, clock),
        logout=Logout(authenticate, tokens, refresh_store, audit, clock),
        authenticate=authenticate,
        capacity_dashboard=GetCapacityDashboard(workspaces, audit, clock),
        list_tenants=ListTenants(tenants, users, audit, clock),
        set_tenant_status=SetTenantStatus(tenants, users, refresh_store, audit, clock),
        provision_tenant=ProvisionTenant(tenants, users, hasher, audit, clock),
        list_audit=ListAuditEvents(audit),
    )
    return Application(services, tenants, users, audit, hasher, clock, settings)


def build_http_app(application: Application):  # type: ignore[no-untyped-def]
    settings = application.settings
    return create_app(
        application.services,
        HttpSettings(
            allowed_origins=settings.allowed_origins,
            cookie_secure=not settings.is_local,
            docs_enabled=settings.is_local,
            hsts=not settings.is_local,
        ),
    )


@dataclass(frozen=True)
class SeedCredential:
    tenant: str
    username: str
    role: Role
    password: str


_DEMO_USERS: list[tuple[str, str, Role]] = [
    ("gerencia", "Gerencia de operaciones", Role.MANAGEMENT),
    ("despachador", "Despachador torre de control", Role.DISPATCHER),
    ("conductor", "Conductor de ruta", Role.DRIVER),
    ("admin", "Administrador de la empresa", Role.TENANT_ADMIN),
]


def seed_demo(application: Application) -> list[SeedCredential]:
    """Crea Empresa Demo A y B con un usuario por rol y el superadministrador.

    Las contraseñas son aleatorias y se devuelven UNA sola vez a quien llama (la consola); no se
    guardan en disco, repositorio ni logs.
    """
    credentials: list[SeedCredential] = []
    now = application.clock.now()
    for slug, name in ((DEMO_A_SLUG, "Empresa Demo A"), (DEMO_B_SLUG, "Empresa Demo B")):
        tenant = Tenant(TenantId(f"t-{slug}"), slug, name, TenantStatus.ACTIVE, now)
        application.tenants.save(tenant)
        for username, display, role in _DEMO_USERS:
            password = generate_password()
            application.users.save(
                User(
                    id=f"u-{slug}-{username}",
                    tenant_id=tenant.id,
                    username=username,
                    display_name=display,
                    role=role,
                    password_hash=application.hasher.hash(password),
                )
            )
            credentials.append(SeedCredential(slug, username, role, password))
    password = generate_password()
    application.users.save(
        User(
            id="u-superadmin",
            tenant_id=None,
            username="superadmin",
            display_name="Superadministrador",
            role=Role.SUPER_ADMIN,
            password_hash=application.hasher.hash(password),
        )
    )
    credentials.append(SeedCredential("(sin empresa)", "superadmin", Role.SUPER_ADMIN, password))
    return credentials
