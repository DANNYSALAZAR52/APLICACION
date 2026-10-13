"""Espacio de trabajo de un tenant: casos de uso ya ligados a los datos de SU empresa."""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.application.use_cases.build_capacity_dashboard import BuildCapacityDashboard
from fleetplanner.domain.tenancy.models import TenantId


@dataclass(frozen=True)
class TenantWorkspace:
    """Los casos de uso contenidos usan lectores/repositorios de un único tenant.

    No existe forma de pedirle datos de otra empresa: el tenant se fijó al crearlo.
    """

    tenant_id: TenantId
    capacity_dashboard: BuildCapacityDashboard
