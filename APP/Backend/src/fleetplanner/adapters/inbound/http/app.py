"""Aplicación FastAPI: rutas, cabeceras de seguridad, CORS y autenticación por Bearer."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from fleetplanner.adapters.inbound.http import schemas
from fleetplanner.adapters.inbound.http.errors import (
    error_response,
    new_request_id,
    register_error_handlers,
)
from fleetplanner.application.dto.security import LoginCommand, Session
from fleetplanner.application.services import ApplicationServices
from fleetplanner.domain.shared.errors import AuthenticationError, PermissionDeniedError
from fleetplanner.domain.tenancy.models import Principal, TenantStatus

REFRESH_COOKIE = "fp_refresh"
_API = "/api/v1"
_AUTH_PATH = f"{_API}/auth"


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
    extra_headers: dict[str, str] = field(default_factory=dict)


def create_app(services: ApplicationServices, settings: HttpSettings | None = None) -> FastAPI:
    cfg = settings or HttpSettings()
    app = FastAPI(
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
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def _security_and_limits(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = new_request_id()
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cfg.max_body_bytes:
            return error_response(
                request, 413, "SOLICITUD_MUY_GRANDE", "La solicitud supera el tamaño permitido."
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["X-Request-Id"] = request.state.request_id
        if not request.url.path.startswith(f"{_API}/docs"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
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
        if origin is not None and origin not in cfg.allowed_origins:
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

    for router in (health, auth, api):
        app.include_router(router)
    return app
