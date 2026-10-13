"""Traducción de errores a respuestas con código estable y mensaje en español.

Nunca se devuelven trazas, rutas internas ni el valor que envió el cliente.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fleetplanner.domain.shared.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    InsufficientDataError,
    InvalidValueError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    TenantSuspendedError,
)

logger = logging.getLogger("fleetplanner.http")

# (clase de error, estado HTTP, código estable). El orden importa: lo más específico primero.
_MAPPING: list[tuple[type[DomainError], int, str]] = [
    (AuthenticationError, 401, "AUTENTICACION_INVALIDA"),
    (TenantSuspendedError, 403, "EMPRESA_SUSPENDIDA"),
    (PermissionDeniedError, 403, "PERMISO_DENEGADO"),
    (NotFoundError, 404, "NO_ENCONTRADO"),
    (ConflictError, 409, "CONFLICTO"),
    (RateLimitedError, 429, "DEMASIADOS_INTENTOS"),
    (InsufficientDataError, 422, "DATOS_INSUFICIENTES"),
    (InvalidValueError, 422, "DATO_INVALIDO"),
]

_HTTP_MESSAGES = {
    401: ("AUTENTICACION_REQUERIDA", "Debe iniciar sesión para continuar."),
    403: ("PERMISO_DENEGADO", "No tiene permiso para realizar esta operación."),
    404: ("NO_ENCONTRADO", "El recurso solicitado no existe."),
    405: ("METODO_NO_PERMITIDO", "Método no permitido para este recurso."),
    413: ("SOLICITUD_MUY_GRANDE", "La solicitud supera el tamaño permitido."),
}


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "-"))


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    fields: list[dict[str, str]] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {
        "error": {"codigo": code, "mensaje": message, "id_solicitud": request_id(request)}
    }
    if fields:
        body["error"]["campos"] = fields  # type: ignore[index]
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(body, status_code=status, headers=headers)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def _validation_message(error_type: str) -> str:
    if error_type == "missing":
        return "Campo obligatorio."
    if error_type == "extra_forbidden":
        return "Campo no permitido."
    if "too_short" in error_type or "too_long" in error_type:
        return "La longitud no es válida."
    return "Valor no válido."


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, error: DomainError) -> JSONResponse:
        for cls, status, code in _MAPPING:
            if isinstance(error, cls):
                return error_response(request, status, code, str(error))
        return error_response(request, 400, "SOLICITUD_INVALIDA", str(error))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, error: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "campo": ".".join(str(p) for p in item["loc"] if p != "body"),
                "mensaje": _validation_message(str(item["type"])),
            }
            for item in error.errors()
        ]
        return error_response(
            request, 422, "SOLICITUD_INVALIDA", "La solicitud contiene datos no válidos.", fields
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_MESSAGES.get(
            error.status_code, ("ERROR_SOLICITUD", "No se pudo procesar la solicitud.")
        )
        return error_response(request, error.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, error: Exception) -> JSONResponse:
        # El detalle va solo al log del servidor (con el id de solicitud), nunca al cliente.
        logger.error(
            "Error no controlado [%s] %s", request_id(request), type(error).__name__, exc_info=error
        )
        return error_response(
            request, 500, "ERROR_INTERNO", "Ocurrió un error interno. Intente más tarde."
        )
