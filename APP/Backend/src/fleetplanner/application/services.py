"""Conjunto de casos de uso que consumen los adaptadores de entrada (HTTP, CLI...)."""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.application.ports.outbound.exports import SpreadsheetExporterPort
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
from fleetplanner.application.use_cases.ml.access import GetPatterns, RetrainModels
from fleetplanner.application.use_cases.ml.scheduled import ScheduledRetraining
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
    control_tower: GetControlTower
    run_tracking: RunTracking
    inject_event: InjectEvent
    decide_proposal: DecideProposal
    control_simulation: ControlSimulation
    reset_day: ResetOperatingDay
    plan_version: GetPlanVersion
    indicators: GetIndicators
    scheduled_tracking: ScheduledTracking
    driver_route: GetDriverRoute
    confirm_delivery: ConfirmDelivery
    report_incident: ReportIncident
    master_schema: GetMasterSchema
    master_list: ListMaster
    master_create: CreateMaster
    master_update: UpdateMaster
    master_delete: DeleteMaster
    master_csv_preview: PreviewMasterCsv
    master_csv_apply: ApplyMasterCsv
    master_export: ExportMaster
    parameters: ListParameters
    set_parameter: SetParameter
    master_history: GetMasterHistory
    spreadsheets: SpreadsheetExporterPort
    record_export: RecordExport
    patterns: GetPatterns
    retrain_models: RetrainModels
    scheduled_retraining: ScheduledRetraining
