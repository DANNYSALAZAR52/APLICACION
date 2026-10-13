"""Conjunto de casos de uso que consumen los adaptadores de entrada (HTTP, CLI...)."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class ApplicationServices:
    login: Login
    refresh: RefreshSession
    logout: Logout
    authenticate: AuthenticateRequest
    capacity_dashboard: GetCapacityDashboard
    list_tenants: ListTenants
    set_tenant_status: SetTenantStatus
    provision_tenant: ProvisionTenant
    list_audit: ListAuditEvents
