"""Aplicación FastAPI: rutas, cabeceras de seguridad, CORS y autenticación por Bearer."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from fleetplanner.adapters.inbound.http import schemas
from fleetplanner.adapters.inbound.http.errors import (
    error_response,
    new_request_id,
    register_error_handlers,
)
from fleetplanner.adapters.inbound.http.exports_http import dashboard_sheets
from fleetplanner.adapters.inbound.http.routes_masters import (
    XLSX,
    attachment,
    build_masters_router,
    safe_filename,
)
from fleetplanner.adapters.inbound.http.routes_patterns import build_patterns_router
from fleetplanner.adapters.inbound.http.routes_routing import StreamConfig, build_routing_router
from fleetplanner.application.dto.security import LoginCommand, Session
from fleetplanner.application.services import ApplicationServices
from fleetplanner.domain.shared.errors import AuthenticationError, PermissionDeniedError
from fleetplanner.domain.tenancy.models import Principal, TenantStatus

logger = logging.getLogger("fleetplanner.http")
REFRESH_COOKIE = "fp_refresh"
_API = "/api/v1"
_AUTH_PATH = f"{_API}/auth"

# La API no sirve contenido activo; la interfaz compilada sí necesita scripts propios, estilos en
# línea (Leaflet/React), imágenes de OpenStreetMap y conexión a su propio origen.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
_APP_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://tile.openstreetmap.org; font-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'none'"
)


@dataclass(frozen=True)
class HttpSettings:
    """Configuración del adaptador HTTP.

    ``docs_enabled`` y ``cookie_secure=False`` son solo para desarrollo local; en cualquier otro
    entorno la documentación de la API debe estar apagada y la cookie ser ``Secure`` (TLS).
    """

    allowed_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    cookie_secure: bool = False
    docs_enabled: bool = False
    hsts: bool = False
    refresh_max_age_seconds: int = 8 * 3600
    max_body_bytes: int = 64 * 1024
    csv_body_bytes: int = 256 * 1024  # solo las cargas CSV de maestros
    tracking_interval_s: float = 0.0  # 0 = sin tarea programada (pruebas)
    stream: StreamConfig = field(default_factory=StreamConfig)
    extra_headers: dict[str, str] = field(default_factory=dict)
    frontend_dist: str | None = None  # carpeta de la interfaz compilada (mismo origen)


async def _tracking_loop(services: ApplicationServices, interval_s: float) -> None:
    """Tarea programada de seguimiento: corre sola mientras la API está en pie."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            await run_in_threadpool(services.scheduled_tracking.execute)
            await run_in_threadpool(services.scheduled_retraining.execute)
        except Exception as error:  # noqa: BLE001 - la tarea nunca debe morir por un fallo puntual
            logger.error("Fallo en el seguimiento programado: %s", type(error).__name__)


def create_app(services: ApplicationServices, settings: HttpSettings | None = None) -> FastAPI:
    cfg = settings or HttpSettings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if cfg.tracking_interval_s > 0:
            task = asyncio.create_task(_tracking_loop(services, cfg.tracking_interval_s))
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        lifespan=lifespan,
        title="API de planeación de flota (demo)",
        version="0.2.0",
        docs_url=f"{_API}/docs" if cfg.docs_enabled else None,
        redoc_url=None,
        openapi_url=f"{_API}/openapi.json" if cfg.docs_enabled else None,
    )
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def _security_and_limits(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = new_request_id()
        declared = request.headers.get("content-length")
        is_csv_upload = request.url.path.endswith(("/csv/preview", "/csv/apply"))
        limit = cfg.csv_body_bytes if is_csv_upload else cfg.max_body_bytes
        if declared and declared.isdigit() and int(declared) > limit:
            return error_response(
                request, 413, "SOLICITUD_MUY_GRANDE", "La solicitud supera el tamaño permitido."
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if cfg.frontend_dist and request.url.path.startswith("/assets/"):
            # Los archivos compilados llevan huella en el nombre: se pueden cachear.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["X-Request-Id"] = request.state.request_id
        if not request.url.path.startswith(f"{_API}/docs"):
            is_api = request.url.path.startswith(f"{_API}/")
            response.headers["Content-Security-Policy"] = (
                _API_CSP if is_api or not cfg.frontend_dist else _APP_CSP
            )
        if cfg.hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        for name, value in cfg.extra_headers.items():
            response.headers[name] = value
        return response

    def bearer_token(request: Request) -> str:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise StarletteHTTPException(status_code=401)
        return token.strip()

    def current_principal(request: Request) -> Principal:
        return services.authenticate.execute(bearer_token(request))

    def check_origin(request: Request) -> None:
        """Defensa CSRF adicional en endpoints que usan la cookie de refresh."""
        origin = request.headers.get("origin")
        if origin is None or origin in cfg.allowed_origins:
            return
        # Con la interfaz servida por esta misma API, el mismo origen es siempre legítimo.
        own = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if cfg.frontend_dist and origin == own:
            return
        raise PermissionDeniedError("Origen no permitido.")

    def set_refresh_cookie(response: Response, session: Session) -> None:
        response.set_cookie(
            REFRESH_COOKIE,
            session.refresh.token,
            max_age=cfg.refresh_max_age_seconds,
            httponly=True,
            secure=cfg.cookie_secure,
            samesite="strict",
            path=_AUTH_PATH,
        )

    def session_body(session: Session) -> schemas.SessionResponse:
        return schemas.SessionResponse(
            access_token=session.access.token,
            expires_at=session.access.expires_at,
            user=schemas.user_info(session.principal, session.display_name),
        )

    # ---------------------------------------------------------------- salud
    health = APIRouter(prefix=_API, tags=["salud"])

    @health.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}  # sin versiones ni detalles internos

    # ------------------------------------------------------- autenticación
    auth = APIRouter(prefix=_AUTH_PATH, tags=["autenticación"])

    @auth.post("/login", response_model=schemas.SessionResponse)
    def login(
        body: schemas.LoginRequest, request: Request, response: Response
    ) -> schemas.SessionResponse:
        check_origin(request)
        session = services.login.execute(
            LoginCommand(
                tenant_slug=body.tenant_slug,
                username=body.username,
                password=body.password,
                client_key=request.client.host if request.client else "unknown",
            )
        )
        set_refresh_cookie(response, session)
        return session_body(session)

    @auth.post("/refresh", response_model=schemas.SessionResponse)
    def refresh(request: Request, response: Response) -> schemas.SessionResponse:
        check_origin(request)
        token = request.cookies.get(REFRESH_COOKIE)
        if not token:
            raise AuthenticationError("La sesión no es válida o expiró.")
        session = services.refresh.execute(token)
        set_refresh_cookie(response, session)
        return session_body(session)

    @auth.post("/logout", status_code=204)
    def logout(request: Request) -> Response:
        check_origin(request)
        services.logout.execute(bearer_token(request), request.cookies.get(REFRESH_COOKIE))
        reply = Response(status_code=204)
        reply.delete_cookie(REFRESH_COOKIE, path=_AUTH_PATH)
        return reply

    # ------------------------------------------------------------- recursos
    api = APIRouter(prefix=_API)

    @api.get("/me", response_model=schemas.UserInfo, tags=["sesión"])
    def me(principal: Principal = Depends(current_principal)) -> schemas.UserInfo:  # noqa: B008
        return schemas.user_info(principal, principal.username)

    @api.get("/capacity/dashboard", response_model=schemas.DashboardResponse, tags=["capacidad"])
    def capacity_dashboard(
        principal: Principal = Depends(current_principal),  # noqa: B008
    ) -> schemas.DashboardResponse:
        # Sin parámetros de tenant: la empresa sale de la identidad autenticada.
        return schemas.dashboard_response(services.capacity_dashboard.execute(principal))

    @api.get("/capacity/export.xlsx", tags=["capacidad"])
    def capacity_export(
        principal: Principal = Depends(current_principal),  # noqa: B008
    ) -> Response:
        """Tablero de capacidad en Excel (generado en el servidor, con fórmulas neutralizadas)."""
        dashboard = services.capacity_dashboard.execute(principal)  # RBAC + auditoría de consulta
        data = services.spreadsheets.to_xlsx(
            dashboard_sheets(schemas.dashboard_response(dashboard))
        )
        services.record_export.execute(principal, "capacity/dashboard", "xlsx")
        stamp = dashboard.run_at.strftime("%Y-%m-%d")
        return attachment(data, XLSX, safe_filename(f"capacidad-flota-{stamp}", "xlsx"))

    @api.get("/tenants", response_model=list[schemas.TenantOut], tags=["empresas"])
    def list_tenants(
        principal: Principal = Depends(current_principal),  # noqa: B008
    ) -> list[schemas.TenantOut]:
        return [schemas.tenant_summary_out(s) for s in services.list_tenants.execute(principal)]

    @api.post(
        "/tenants", response_model=schemas.ProvisionResponse, status_code=201, tags=["empresas"]
    )
    def provision_tenant(
        body: schemas.ProvisionRequest,
        response: Response,
        principal: Principal = Depends(current_principal),  # noqa: B008
    ) -> schemas.ProvisionResponse:
        result = services.provision_tenant.execute(principal, body.slug, body.name)
        if not result.created:
            response.status_code = 200
        return schemas.ProvisionResponse(
            tenant=schemas.tenant_out(result.tenant),
            created=result.created,
            admin_username=result.admin_username,
            initial_admin_password=result.initial_admin_password,
        )

    def _set_status(slug: str, status: TenantStatus, principal: Principal) -> schemas.TenantOut:
        return schemas.tenant_out(services.set_tenant_status.execute(principal, slug, status))

    @api.post("/tenants/{slug}/suspend", response_model=schemas.TenantOut, tags=["empresas"])
    def suspend_tenant(
        slug: str,
        principal: Principal = Depends(current_principal),  # noqa: B008
    ) -> schemas.TenantOut:
        return _set_status(slug, TenantStatus.SUSPENDED, principal)

    @api.post("/tenants/{slug}/reactivate", response_model=schemas.TenantOut, tags=["empresas"])
    def reactivate_tenant(
        slug: str,
        principal: Principal = Depends(current_principal),  # noqa: B008
    ) -> schemas.TenantOut:
        return _set_status(slug, TenantStatus.ACTIVE, principal)

    @api.get("/audit", response_model=list[schemas.AuditOut], tags=["auditoría"])
    def audit(
        limit: int = 100,
        principal: Principal = Depends(current_principal),  # noqa: B008
    ) -> list[schemas.AuditOut]:
        return [schemas.audit_out(e) for e in services.list_audit.execute(principal, limit)]

    routing = build_routing_router(services, current_principal, cfg.stream)
    masters = build_masters_router(services, current_principal)
    patterns = build_patterns_router(services, current_principal)
    for router in (health, auth, api, routing, masters, patterns):
        app.include_router(router)
    if cfg.frontend_dist:
        _mount_frontend(app, Path(cfg.frontend_dist))
    return app


def _mount_frontend(app: FastAPI, root: Path) -> None:
    """Sirve la interfaz compilada (SPA) desde el mismo origen que la API.

    Registrado al final: nunca tapa rutas de ``/api``. Cualquier ruta del navegador devuelve
    ``index.html``; no se puede salir de la carpeta (se resuelve y se verifica la ruta).
    """
    base = root.resolve()
    index = base / "index.html"
    assets = base / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith("api/") or path == "api":
            raise StarletteHTTPException(status_code=404)
        candidate = (base / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(base):
            return FileResponse(candidate)
        return FileResponse(index)
