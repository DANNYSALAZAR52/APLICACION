"""Endpoints de maestros y parámetros. La empresa sale de la identidad, nunca de la ruta."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response

from fleetplanner.adapters.inbound.http import schemas_masters as m
from fleetplanner.application.ports.outbound.exports import Sheet
from fleetplanner.application.services import ApplicationServices
from fleetplanner.domain.tenancy.models import Principal

_ENTITY = Path(min_length=1, max_length=30, pattern=r"^[a-z_]+$")
_KEY = Path(min_length=1, max_length=80, pattern=r"^[^/\\\x00-\x1f]+$")
_PARAM = Path(min_length=1, max_length=40, pattern=r"^[a-z_]+$")

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV = "text/csv; charset=utf-8"


def safe_filename(text: str, extension: str) -> str:
    """Nombre de archivo sin caracteres que rompan la cabecera ni salgan de la carpeta."""
    base = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-.") or "exportacion"
    return f"{base[:60]}.{extension}"


def attachment(data: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def build_masters_router(
    services: ApplicationServices, current_principal: Callable[..., Principal]
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/masters", tags=["maestros"])
    auth = Depends(current_principal)  # noqa: B008 - se comparte entre las rutas del router

    @router.get("/schema", response_model=m.MasterSchemaOut)
    def schema(principal: Principal = auth) -> m.MasterSchemaOut:
        return m.schema_out(services.master_schema.execute(principal))

    @router.get("/entities/{entity}", response_model=m.RowsOut)
    def list_rows(entity: Annotated[str, _ENTITY], principal: Principal = auth) -> m.RowsOut:
        return m.rows_out(services.master_list.execute(principal, entity))

    @router.post("/entities/{entity}", status_code=201)
    def create(
        entity: Annotated[str, _ENTITY], body: m.RowIn, principal: Principal = auth
    ) -> dict[str, object]:
        return services.master_create.execute(principal, entity, body.values)

    @router.put("/entities/{entity}/{key}")
    def update(
        entity: Annotated[str, _ENTITY],
        key: Annotated[str, _KEY],
        body: m.RowIn,
        principal: Principal = auth,
    ) -> dict[str, object]:
        return services.master_update.execute(principal, entity, key, body.values)

    @router.delete("/entities/{entity}/{key}", status_code=204)
    def delete(
        entity: Annotated[str, _ENTITY], key: Annotated[str, _KEY], principal: Principal = auth
    ) -> Response:
        services.master_delete.execute(principal, entity, key)
        return Response(status_code=204)

    @router.post("/entities/{entity}/csv/preview", response_model=m.CsvPreviewOut)
    def csv_preview(
        entity: Annotated[str, _ENTITY], body: m.CsvIn, principal: Principal = auth
    ) -> m.CsvPreviewOut:
        return m.preview_out(services.master_csv_preview.execute(principal, entity, body.content))

    @router.post("/entities/{entity}/csv/apply", response_model=m.CsvApplyOut)
    def csv_apply(
        entity: Annotated[str, _ENTITY], body: m.CsvIn, principal: Principal = auth
    ) -> m.CsvApplyOut:
        return m.apply_out(services.master_csv_apply.execute(principal, entity, body.content))

    @router.get("/entities/{entity}/export")
    def export(
        entity: Annotated[str, _ENTITY],
        fmt: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "csv",
        principal: Principal = auth,
    ) -> Response:
        title, header, rows = services.master_export.execute(principal, entity)
        sheet = Sheet(
            title,
            header,
            rows,
            notes=("DATOS DE DEMOSTRACIÓN", f"Maestro: {title}"),
        )
        name = safe_filename(f"maestro-{entity}", fmt)
        if fmt == "xlsx":
            return attachment(services.spreadsheets.to_xlsx([sheet]), XLSX, name)
        return attachment(services.spreadsheets.to_csv(sheet), CSV, name)

    @router.get("/parameters", response_model=list[m.ParameterOut])
    def parameters(principal: Principal = auth) -> list[m.ParameterOut]:
        return [m.parameter_out(p) for p in services.parameters.execute(principal)]

    @router.put("/parameters/{key}", response_model=m.ParameterOut)
    def set_parameter(
        key: Annotated[str, _PARAM], body: m.ParameterIn, principal: Principal = auth
    ) -> m.ParameterOut:
        view = services.set_parameter.execute(
            principal, key, body.value, body.valid_from, body.note
        )
        return m.parameter_out(view)

    @router.get("/history", response_model=list[m.ChangeOut])
    def history(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        entity: Annotated[str | None, Query(pattern=r"^[a-z_]+$", max_length=30)] = None,
        principal: Principal = auth,
    ) -> list[m.ChangeOut]:
        return [m.change_out(c) for c in services.master_history.execute(principal, limit, entity)]

    return router
