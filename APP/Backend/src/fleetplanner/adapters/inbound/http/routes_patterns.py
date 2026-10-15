"""Endpoints de patrones de ML. La empresa sale de la identidad, nunca de la ruta."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends

from fleetplanner.adapters.inbound.http import schemas_patterns as s
from fleetplanner.application.services import ApplicationServices
from fleetplanner.domain.tenancy.models import Principal


def build_patterns_router(
    services: ApplicationServices, current_principal: Callable[..., Principal]
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/patterns", tags=["patrones"])
    auth = Depends(current_principal)  # noqa: B008 - se comparte entre las rutas del router

    @router.get("", response_model=s.PatternsOut)
    def patterns(principal: Principal = auth) -> s.PatternsOut:
        return s.patterns_out(services.patterns.execute(principal))

    @router.post("/retrain", response_model=s.PatternsOut)
    def retrain(principal: Principal = auth) -> s.PatternsOut:
        return s.patterns_out(services.retrain_models.execute(principal))

    return router
