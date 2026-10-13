"""Esquemas HTTP (Pydantic). No son entidades de dominio: el mapeo es explícito."""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from fleetplanner.application.dto.capacity import CapacityDashboard
from fleetplanner.application.dto.security import AuditEvent, TenantSummary
from fleetplanner.domain.tenancy.access_policy import AccessPolicy
from fleetplanner.domain.tenancy.models import Principal, Tenant

DEMO_LABEL = "DATOS DE DEMOSTRACIÓN"


class StrictModel(BaseModel):
    """Rechaza campos desconocidos: un `tenant_id` enviado por el cliente es un error."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- autenticación
class LoginRequest(StrictModel):
    tenant_slug: str | None = Field(default=None, max_length=40)
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class UserInfo(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    tenant_slug: str | None
    tenant_name: str | None
    permissions: list[str]


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - tipo de esquema OAuth, no una contraseña
    expires_at: datetime
    user: UserInfo


def user_info(principal: Principal, display_name: str) -> UserInfo:
    return UserInfo(
        id=principal.user_id,
        username=principal.username,
        display_name=display_name,
        role=principal.role.value,
        tenant_slug=principal.tenant_slug,
        tenant_name=principal.tenant_name,
        permissions=sorted(p.value for p in AccessPolicy.permissions_of(principal.role)),
    )


# -------------------------------------------------------------------- tenants
class TenantOut(BaseModel):
    slug: str
    name: str
    status: str
    created_at: datetime
    user_count: int | None = None


class ProvisionRequest(StrictModel):
    slug: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)


class ProvisionResponse(BaseModel):
    tenant: TenantOut
    created: bool
    admin_username: str | None
    initial_admin_password: str | None


def tenant_out(tenant: Tenant, user_count: int | None = None) -> TenantOut:
    return TenantOut(
        slug=tenant.slug,
        name=tenant.name,
        status=tenant.status.value,
        created_at=tenant.created_at,
        user_count=user_count,
    )


def tenant_summary_out(summary: TenantSummary) -> TenantOut:
    return tenant_out(summary.tenant, summary.user_count)


# ------------------------------------------------------------------ auditoría
class AuditOut(BaseModel):
    at: datetime
    action: str
    outcome: str
    actor_username: str | None
    tenant_id: str | None
    resource: str
    detail: dict[str, str]


def audit_out(event: AuditEvent) -> AuditOut:
    return AuditOut(
        at=event.at,
        action=event.action,
        outcome=event.outcome.value,
        actor_username=event.actor_username,
        tenant_id=event.tenant_id,
        resource=event.resource,
        detail=event.detail,
    )


# ---------------------------------------------------------- tablero de capacidad
class FleetRow(BaseModel):
    vehicle_type: str
    current: int
    balance: int
    lean: int | None
    monte_carlo_p95: int | None
    mix: int | None
    own_vs_third: int | None
    gap: int


class CorridorOut(BaseModel):
    code: str
    name: str
    vehicle_type: str
    design_t: float
    mean_t: float
    std_t: float
    valid_days: int
    cycle_h: float
    trips_per_day: float
    effective_t_per_day: float
    lean_cycle_h: float | None
    value_added_pct: float | None
    waste_pct: float | None
    takt_min: float | None


class MonteCarloOut(BaseModel):
    seed: int
    days: int
    p50_total: int
    p90_total: int
    p95_total: int
    coverage_pct: float


class AssignmentOut(BaseModel):
    corridor: str
    vehicle_type: str
    count: int


class MixOut(BaseModel):
    status: str
    optimal: bool
    total_vehicles: int
    total_cost_per_day: float | None
    message: str
    assignments: list[AssignmentOut]


class CostPointOut(BaseModel):
    own_fleet: int
    daily_cost: float


class OwnVsThirdOut(BaseModel):
    vehicle_type: str
    days_used: int
    optimal_own: int
    optimal_cost_per_day: float
    all_third_party_cost_per_day: float
    all_own_cost_per_day: float
    curve: list[CostPointOut]


class YearOut(BaseModel):
    year: int
    total_required: int
    required_by_type: dict[str, int]


class ProjectionOut(BaseModel):
    scenario: str
    first_deficit_year: int | None
    years: list[YearOut]


class KpisOut(BaseModel):
    fleet_utilization: float | None
    oee: float
    fill_pct: float
    empty_km_pct: float
    daily_cost: float
    cost_per_ton: float | None
    cost_per_ton_km: float | None
    otif: float | None


class ParametersOut(BaseModel):
    design_percentile: float
    reserve: float
    window_days: int
    days_per_month: int


class DashboardResponse(BaseModel):
    demo_label: str
    run_at: datetime
    algorithm_version: str
    base_year: int
    vehicle_types: list[str]
    parameters: ParametersOut
    fleet: list[FleetRow]
    totals: FleetRow
    corridors: list[CorridorOut]
    monte_carlo: MonteCarloOut
    mix: MixOut
    own_vs_third: list[OwnVsThirdOut]
    projections: list[ProjectionOut]
    kpis: KpisOut
    findings: list[str]
    warnings: list[str]
    ml_forecast_available: bool


def _finite(value: float | None) -> float | None:
    """JSON no admite infinito/NaN: se informa como dato no disponible."""
    if value is None or math.isinf(value) or math.isnan(value):
        return None
    return value


def dashboard_response(dashboard: CapacityDashboard) -> DashboardResponse:
    params = dashboard.parameters
    parameters = ParametersOut(
        design_percentile=params.design_percentile.fraction,
        reserve=params.reserve.fraction,
        window_days=params.window_days,
        days_per_month=params.days_per_month,
    )
    requirement = dashboard.balance.requirement
    types = sorted(set(requirement.required_by_type) | set(requirement.current_by_type))
    mc = dashboard.monte_carlo
    own = {t: r.optimal_own for t, r in dashboard.own_vs_third.by_type.items()}
    have_own = bool(own)

    fleet = [
        FleetRow(
            vehicle_type=t,
            current=requirement.current_by_type.get(t, 0),
            balance=requirement.required_by_type.get(t, 0),
            lean=dashboard.lean.required_by_type.get(t, 0),
            monte_carlo_p95=mc.percentiles_by_type.get(t, {}).get("p95", 0),
            mix=dashboard.mix.fleet_by_type.get(t, 0) if dashboard.mix.has_solution else None,
            own_vs_third=own.get(t, 0) if have_own else None,
            gap=requirement.gap_by_type.get(t, 0),
        )
        for t in types
    ]
    totals = FleetRow(
        vehicle_type="TOTAL",
        current=requirement.total_current,
        balance=requirement.total_required,
        lean=dashboard.lean.total_required,
        monte_carlo_p95=mc.p95_total,
        mix=dashboard.mix.total_vehicles if dashboard.mix.has_solution else None,
        own_vs_third=dashboard.own_vs_third.total_own if have_own else None,
        gap=requirement.total_gap,
    )
    lean_by_corridor = {c.corridor_code: c for c in dashboard.lean.by_corridor}
    corridors = []
    for code, design in dashboard.balance.design.items():
        capacity = dashboard.balance.capacities[code]
        lean = lean_by_corridor.get(code)
        corridors.append(
            CorridorOut(
                code=code,
                name=dashboard.corridor_names.get(code, code),
                vehicle_type=capacity.vehicle_type,
                design_t=design.design_t,
                mean_t=design.mean_t,
                std_t=design.std_t,
                valid_days=design.valid_days,
                cycle_h=capacity.cycle_h,
                trips_per_day=capacity.trips_per_day,
                effective_t_per_day=capacity.effective_t_per_day,
                lean_cycle_h=lean.standard_cycle_h if lean else None,
                value_added_pct=lean.value_added_pct if lean else None,
                waste_pct=lean.waste_pct if lean else None,
                takt_min=_finite(lean.takt_min) if lean else None,
            )
        )
    kpis = dashboard.balance.kpis
    mix = dashboard.mix
    return DashboardResponse(
        demo_label=DEMO_LABEL,
        run_at=dashboard.run_at,
        algorithm_version=dashboard.algorithm_version,
        base_year=dashboard.base_year,
        vehicle_types=types,
        parameters=parameters,
        fleet=fleet,
        totals=totals,
        corridors=corridors,
        monte_carlo=MonteCarloOut(
            seed=mc.seed,
            days=mc.days,
            p50_total=mc.p50_total,
            p90_total=mc.p90_total,
            p95_total=mc.p95_total,
            coverage_pct=mc.coverage_pct,
        ),
        mix=MixOut(
            status=mix.status.value,
            optimal=mix.status.value == "optimal",
            total_vehicles=mix.total_vehicles,
            total_cost_per_day=mix.total_cost_per_day,
            message=mix.message,
            assignments=[
                AssignmentOut(corridor=r, vehicle_type=t, count=n)
                for (r, t), n in sorted(mix.assignments.items())
            ],
        ),
        own_vs_third=[
            OwnVsThirdOut(
                vehicle_type=item.vehicle_type,
                days_used=item.days_used,
                optimal_own=item.optimal_own,
                optimal_cost_per_day=item.optimal_cost_per_day,
                all_third_party_cost_per_day=item.all_third_party_cost_per_day,
                all_own_cost_per_day=item.all_own_cost_per_day,
                curve=[
                    CostPointOut(own_fleet=p.own_fleet, daily_cost=p.daily_cost) for p in item.curve
                ],
            )
            for item in dashboard.own_vs_third.by_type.values()
        ],
        projections=[
            ProjectionOut(
                scenario=p.scenario,
                first_deficit_year=p.first_deficit_year,
                years=[
                    YearOut(
                        year=y.year,
                        total_required=y.requirement.total_required,
                        required_by_type=dict(y.requirement.required_by_type),
                    )
                    for y in p.years
                ],
            )
            for p in dashboard.projections
        ],
        kpis=KpisOut(
            fleet_utilization=kpis.fleet_utilization,
            oee=kpis.oee,
            fill_pct=kpis.fill_pct,
            empty_km_pct=kpis.empty_km_pct,
            daily_cost=kpis.daily_cost,
            cost_per_ton=kpis.cost_per_ton,
            cost_per_ton_km=kpis.cost_per_ton_km,
            otif=kpis.otif,
        ),
        findings=dashboard.findings,
        warnings=dashboard.warnings,
        ml_forecast_available=dashboard.ml_forecast_available,
    )
