"""Ensamblado de la aplicación completa (DEMO-ONLY: adaptadores en memoria)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fleetplanner.adapters.inbound.http import HttpSettings, create_app
from fleetplanner.adapters.outbound.clock import SystemClock
from fleetplanner.adapters.outbound.demo_data import (
    DEMO_A_SLUG,
    DEMO_B_SLUG,
    capacity_reader_for_slug,
    history_reader_for_slug,
    routing_reader_for_slug,
)
from fleetplanner.adapters.outbound.export import SpreadsheetExporter
from fleetplanner.adapters.outbound.ml import (
    SklearnAnomalyDetector,
    SklearnDelayRiskPredictor,
    SklearnDemandForecaster,
    SklearnPatternMiner,
)
from fleetplanner.adapters.outbound.persistence_memory import (
    InMemoryAuditLog,
    InMemoryMasterDataStore,
    InMemoryModelRegistry,
    InMemoryRateLimiter,
    InMemoryRefreshTokenStore,
    InMemoryTenantRegistry,
    InMemoryTenantWorkspaceProvider,
    InMemoryUserRepository,
)
from fleetplanner.adapters.outbound.security import Argon2PasswordHasher, JwtTokenService
from fleetplanner.adapters.outbound.solver import OrToolsFleetMixSolver, OrToolsRoutingSolver
from fleetplanner.application.dto.workspace import TenantWorkspace
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.ml import HistoryReaderPort
from fleetplanner.application.ports.outbound.routing import RoutingInputsReader, RoutingSolverPort
from fleetplanner.application.ports.outbound.tenancy import PasswordHasherPort
from fleetplanner.application.services import ApplicationServices
from fleetplanner.application.use_cases.auth import (
    AuthenticateRequest,
    Login,
    Logout,
    RefreshSession,
)
from fleetplanner.application.use_cases.exports import RecordExport
from fleetplanner.application.use_cases.get_capacity_dashboard import GetCapacityDashboard
from fleetplanner.application.use_cases.masters.access import (
    ApplyMasterCsv,
    CreateMaster,
    DeleteMaster,
    ExportMaster,
    GetMasterHistory,
    GetMasterSchema,
    ListMaster,
    ListParameters,
    PreviewMasterCsv,
    SetParameter,
    UpdateMaster,
)
from fleetplanner.application.use_cases.masters.readers import (
    StoreCapacityInputsReader,
    StoreRoutingInputsReader,
    seed_master_data,
)
from fleetplanner.application.use_cases.masters.service import MasterDataService
from fleetplanner.application.use_cases.ml.access import GetPatterns, RetrainModels
from fleetplanner.application.use_cases.ml.scheduled import ScheduledRetraining
from fleetplanner.application.use_cases.ml.service import MlService
from fleetplanner.application.use_cases.routing.access import (
    ConfirmDelivery,
    ControlSimulation,
    DecideProposal,
    GetControlTower,
    GetDriverRoute,
    GetIndicators,
    GetPlanVersion,
    InjectEvent,
    ReportIncident,
    ResetOperatingDay,
    RunTracking,
)
from fleetplanner.application.use_cases.routing.scheduled import ScheduledTracking
from fleetplanner.application.use_cases.tenant_admin import (
    ListAuditEvents,
    ListTenants,
    ProvisionTenant,
    SetTenantStatus,
)
from fleetplanner.bootstrap.container import build_capacity_container, build_routing_container
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
    routing_solver: RoutingSolverPort | None = None,
    routing_reader_factory: Callable[[str], RoutingInputsReader] | None = None,
    ml_reader_factory: Callable[[str], HistoryReaderPort | None] | None = None,
) -> Application:
    """Ensambla la aplicación. Los parámetros finales permiten sustituir ruteo y ML en pruebas.

    ``ml_reader_factory`` recibe el slug de la empresa y devuelve su lector de historia; si
    devuelve ``None`` esa empresa no tiene ML (el tablero indica que no está disponible).
    """
    clock = clock or SystemClock()
    hasher = hasher or Argon2PasswordHasher()
    tenants = InMemoryTenantRegistry()
    users = InMemoryUserRepository()
    audit = InMemoryAuditLog()
    refresh_store = InMemoryRefreshTokenStore(clock)
    limiter = InMemoryRateLimiter(clock)
    tokens = JwtTokenService(settings.jwt_signing_key, clock)
    solver = OrToolsFleetMixSolver()
    routing_solver = routing_solver or OrToolsRoutingSolver()
    routing_readers = routing_reader_factory or routing_reader_for_slug
    history_readers = ml_reader_factory or history_reader_for_slug

    def workspace_factory(tenant: Tenant) -> TenantWorkspace:
        # Cada empresa recibe su propio almacén de maestros (sembrado con datos sintéticos),
        # lectores, repositorios, reloj simulado y casos de uso. Los cálculos leen lo EDITADO.
        base_capacity = capacity_reader_for_slug(tenant.slug).load()
        base_routing = routing_readers(tenant.slug).read()
        masters = MasterDataService(
            InMemoryMasterDataStore(), clock, base_capacity.parameters, base_routing.params
        )
        seed_master_data(masters, base_capacity, base_routing)
        # Cada empresa tiene su propio lector de historia y su propio registro de modelos.
        history = history_readers(tenant.slug)
        ml = (
            MlService(
                history,
                SklearnDemandForecaster(),
                SklearnAnomalyDetector(),
                SklearnDelayRiskPredictor(),
                SklearnPatternMiner(),
                InMemoryModelRegistry(),
                clock,
            )
            if history is not None
            else None
        )
        container = build_capacity_container(
            reader=StoreCapacityInputsReader(masters, base_capacity),
            solver=solver,
            clock=clock,
            ml=ml,
        )
        routing = build_routing_container(
            reader=StoreRoutingInputsReader(masters, base_routing), solver=routing_solver
        )
        if routing.workspace.indicators is not None:
            masters.on_change(routing.workspace.indicators.invalidate)
        return TenantWorkspace(tenant.id, container.dashboard, routing.workspace, masters, ml)

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
        control_tower=GetControlTower(workspaces, audit, clock),
        run_tracking=RunTracking(workspaces, audit, clock),
        inject_event=InjectEvent(workspaces, audit, clock, limiter),
        decide_proposal=DecideProposal(workspaces, audit, clock),
        control_simulation=ControlSimulation(workspaces, audit, clock),
        reset_day=ResetOperatingDay(workspaces, audit, clock, limiter),
        plan_version=GetPlanVersion(workspaces, audit, clock),
        indicators=GetIndicators(workspaces, audit, clock),
        scheduled_tracking=ScheduledTracking(workspaces, audit, clock),
        driver_route=GetDriverRoute(workspaces, audit, clock),
        confirm_delivery=ConfirmDelivery(workspaces, audit, clock),
        report_incident=ReportIncident(workspaces, audit, clock, limiter),
        master_schema=GetMasterSchema(workspaces, audit, clock, limiter),
        master_list=ListMaster(workspaces, audit, clock, limiter),
        master_create=CreateMaster(workspaces, audit, clock, limiter),
        master_update=UpdateMaster(workspaces, audit, clock, limiter),
        master_delete=DeleteMaster(workspaces, audit, clock, limiter),
        master_csv_preview=PreviewMasterCsv(workspaces, audit, clock, limiter),
        master_csv_apply=ApplyMasterCsv(workspaces, audit, clock, limiter),
        master_export=ExportMaster(workspaces, audit, clock, limiter),
        parameters=ListParameters(workspaces, audit, clock, limiter),
        set_parameter=SetParameter(workspaces, audit, clock, limiter),
        master_history=GetMasterHistory(workspaces, audit, clock, limiter),
        spreadsheets=SpreadsheetExporter(),
        record_export=RecordExport(audit, clock),
        patterns=GetPatterns(workspaces, audit, clock),
        retrain_models=RetrainModels(workspaces, audit, clock, limiter),
        scheduled_retraining=ScheduledRetraining(workspaces, audit, clock),
    )
    return Application(services, tenants, users, audit, hasher, clock, settings)


def build_http_app(  # type: ignore[no-untyped-def]
    application: Application, **http_overrides: Any
):
    settings = application.settings
    return create_app(
        application.services,
        HttpSettings(
            allowed_origins=settings.allowed_origins,
            cookie_secure=not settings.is_local,
            docs_enabled=settings.is_local,
            hsts=not settings.is_local,
            **http_overrides,
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


def seed_demo(
    application: Application,
    demo_password: str | None = None,
    superadmin_password: str | None = None,
) -> list[SeedCredential]:
    """Crea Empresa Demo A y B con un usuario por rol y el superadministrador.

    Por defecto las contraseñas son aleatorias y se devuelven UNA sola vez a quien llama (la
    consola); no se guardan en disco ni repositorio. Para mostrar la demo a terceros se pueden
    fijar con variables de entorno (``DEMO_PASSWORD``, ``DEMO_SUPERADMIN_PASSWORD``): el valor
    llega por parámetro desde la configuración y nunca está en el código.
    """
    credentials: list[SeedCredential] = []
    now = application.clock.now()
    for slug, name in ((DEMO_A_SLUG, "Empresa Demo A"), (DEMO_B_SLUG, "Empresa Demo B")):
        tenant = Tenant(TenantId(f"t-{slug}"), slug, name, TenantStatus.ACTIVE, now)
        application.tenants.save(tenant)
        for username, display, role in _DEMO_USERS:
            password = demo_password or generate_password()
            application.users.save(
                User(
                    id=f"u-{slug}-{username}",
                    tenant_id=tenant.id,
                    username=username,
                    display_name=display,
                    role=role,
                    password_hash=application.hasher.hash(password),
                    attributes={"vehicle_id": "V-01"} if role is Role.DRIVER else {},
                )
            )
            credentials.append(SeedCredential(slug, username, role, password))
    password = superadmin_password or generate_password()
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
