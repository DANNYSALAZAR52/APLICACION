"""Endpoints del ruteo dinámico. La empresa sale de la identidad autenticada, nunca de la ruta."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fleetplanner.adapters.inbound.http import schemas_routing as s
from fleetplanner.adapters.inbound.http.exports_http import driver_sheet
from fleetplanner.adapters.inbound.http.routes_masters import CSV, XLSX, attachment, safe_filename
from fleetplanner.application.dto.routing import OperationsSnapshot
from fleetplanner.application.services import ApplicationServices
from fleetplanner.domain.routing.delivery import IncidentKind
from fleetplanner.domain.shared.errors import DomainError, RateLimitedError
from fleetplanner.domain.tenancy.models import Principal

_ID = Path(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
_VERSION = Path(ge=1, le=10_000)


@dataclass(frozen=True)
class StreamConfig:
    """Parámetros del flujo en tiempo real (SSE)."""

    max_seconds: float = 55.0  # el cliente reconecta; así se reautentica con frecuencia
    tick_seconds: float = 1.0
    ping_seconds: float = 15.0
    max_per_user: int = 4


def _sse(event: str, data: dict[str, str]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def build_routing_router(
    services: ApplicationServices,
    current_principal: Callable[..., Principal],
    stream: StreamConfig | None = None,
) -> APIRouter:
    cfg = stream or StreamConfig()
    opened: dict[str, list[float]] = {}
    opened_lock = threading.Lock()

    def acquire(key: str) -> None:
        """Máximo de conexiones simultáneas por usuario; las vencidas no cuentan."""
        now = time.monotonic()
        with opened_lock:
            live = [t for t in opened.get(key, []) if now - t < cfg.max_seconds + 10]
            if len(live) >= cfg.max_per_user:
                opened[key] = live
                raise RateLimitedError("Demasiadas conexiones en tiempo real abiertas.")
            live.append(now)
            opened[key] = live

    def release(key: str) -> None:
        with opened_lock:
            if opened.get(key):
                opened[key].pop(0)

    router = APIRouter(prefix="/api/v1/routing", tags=["ruteo"])
    auth = Depends(current_principal)  # noqa: B008 - se comparte entre las rutas del router

    @router.get("/tower", response_model=s.SnapshotOut)
    def tower(principal: Principal = auth) -> s.SnapshotOut:
        return s.snapshot_out(services.control_tower.execute(principal))

    @router.post("/track", response_model=s.SnapshotOut)
    def track(principal: Principal = auth) -> s.SnapshotOut:
        return s.snapshot_out(services.run_tracking.execute(principal))

    @router.post("/events", response_model=s.EventResultOut, status_code=201)
    def inject_event(body: s.EventIn, principal: Principal = auth) -> s.EventResultOut:
        result = services.inject_event.execute(principal, s.event_command(body))
        return s.event_result_out(result)

    @router.post("/proposals/{proposal_id}/decision", response_model=s.DecisionOut)
    def decide(
        proposal_id: Annotated[str, _ID], body: s.DecisionIn, principal: Principal = auth
    ) -> s.DecisionOut:
        result = services.decide_proposal.execute(
            principal, proposal_id, body.decision == "approve", body.comment
        )
        return s.decision_out(result)

    @router.post("/simulation", response_model=s.SnapshotOut)
    def simulation(body: s.SimulationIn, principal: Principal = auth) -> s.SnapshotOut:
        return s.snapshot_out(services.control_simulation.execute(principal, s.sim_control(body)))

    @router.post("/day/reset", response_model=s.SnapshotOut)
    def reset_day(principal: Principal = auth) -> s.SnapshotOut:
        return s.snapshot_out(services.reset_day.execute(principal))

    @router.get("/driver/route", response_model=s.DriverRouteOut)
    def driver_route(principal: Principal = auth) -> s.DriverRouteOut:
        return s.driver_route_out(services.driver_route.execute(principal))

    @router.get("/driver/route/export")
    def driver_route_export(
        fmt: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "xlsx",
        principal: Principal = auth,
    ) -> Response:
        """Hoja de ruta del conductor en Excel o CSV (solo la de su vehículo)."""
        route = s.driver_route_out(services.driver_route.execute(principal))
        sheet = driver_sheet(route)
        services.record_export.execute(principal, f"routing/driver/{route.vehicle_id}", fmt)
        name = safe_filename(f"hoja-de-ruta-{route.plate}", fmt)
        if fmt == "xlsx":
            return attachment(services.spreadsheets.to_xlsx([sheet]), XLSX, name)
        return attachment(services.spreadsheets.to_csv(sheet), CSV, name)

    @router.post("/driver/deliveries/{order_id}/confirm", response_model=s.ConfirmationOut)
    def confirm_delivery(
        order_id: Annotated[str, _ID], principal: Principal = auth
    ) -> s.ConfirmationOut:
        return s.confirmation_out(services.confirm_delivery.execute(principal, order_id))

    @router.post("/driver/reports", response_model=s.ReportOut, status_code=201)
    def report_incident(body: s.ReportIn, principal: Principal = auth) -> s.ReportOut:
        report = services.report_incident.execute(
            principal, IncidentKind(body.kind), body.detail, body.order_id
        )
        return s.report_out(report)

    @router.get("/stream")
    async def stream_tower(request: Request, principal: Principal = auth) -> StreamingResponse:
        """Estado de la torre de control en tiempo real (Server-Sent Events).

        La identidad y la empresa se revalidan en CADA evento (token, rol, empresa activa) y solo
        se envía el estado de la empresa del usuario. La conexión se cierra sola cada
        ``max_seconds``.
        """
        key = f"{principal.tenant_id}:{principal.user_id}"
        acquire(key)
        try:
            # Se autoriza ANTES de abrir el flujo: sin permiso la respuesta es 403, no un 200 vacío.
            first = await run_in_threadpool(services.control_tower.execute, principal)
        except BaseException:
            release(key)
            raise

        async def events() -> AsyncIterator[str]:
            started = last_sent = time.monotonic()
            previous: str | None = None
            pending_first: OperationsSnapshot | None = first
            try:
                while time.monotonic() - started < cfg.max_seconds:
                    if await request.is_disconnected():
                        return
                    try:
                        if pending_first is not None:
                            snapshot, pending_first = pending_first, None
                        else:
                            who = await run_in_threadpool(current_principal, request)
                            snapshot = await run_in_threadpool(services.control_tower.execute, who)
                    except (DomainError, StarletteHTTPException):
                        yield _sse("end", {"reason": "session"})
                        return
                    payload = s.snapshot_out(snapshot).model_dump_json()
                    now = time.monotonic()
                    if payload != previous:
                        previous, last_sent = payload, now
                        yield f"event: snapshot\ndata: {payload}\n\n"
                    elif now - last_sent >= cfg.ping_seconds:
                        last_sent = now
                        yield ": ping\n\n"
                    await asyncio.sleep(cfg.tick_seconds)
                yield _sse("end", {"reason": "renew"})
            finally:
                release(key)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/indicators", response_model=s.IndicatorsOut)
    def indicators(principal: Principal = auth) -> s.IndicatorsOut:
        return s.indicators_out(services.indicators.execute(principal))

    @router.get("/plans/{version}", response_model=s.PlanDetailOut)
    def plan_version(
        version: Annotated[int, _VERSION], principal: Principal = auth
    ) -> s.PlanDetailOut:
        return s.plan_detail_out(services.plan_version.execute(principal, version))

    return router
