// Contratos de la API (espejo de adapters/inbound/http/schemas.py). Sin `any`.

export type Role = 'management' | 'dispatcher' | 'driver' | 'tenant_admin' | 'super_admin'

export type Permission =
  | 'capacity:read'
  | 'capacity:recalculate'
  | 'routing:read'
  | 'routing:events'
  | 'driver:route'
  | 'master_data:manage'
  | 'patterns:read'
  | 'indicators:read'
  | 'audit:read'
  | 'tenants:manage'

export interface UserInfo {
  id: string
  username: string
  display_name: string
  role: Role
  tenant_slug: string | null
  tenant_name: string | null
  permissions: Permission[]
}

export interface SessionResponse {
  access_token: string
  token_type: string
  expires_at: string
  user: UserInfo
}

export interface LoginRequest {
  tenant_slug: string | null
  username: string
  password: string
}

export interface TenantOut {
  slug: string
  name: string
  status: 'active' | 'suspended'
  created_at: string
  user_count: number | null
}

export interface ProvisionResponse {
  tenant: TenantOut
  created: boolean
  admin_username: string | null
  initial_admin_password: string | null
}

export interface AuditEvent {
  at: string
  action: string
  outcome: 'success' | 'denied' | 'failure'
  actor_username: string | null
  tenant_id: string | null
  resource: string
  detail: Record<string, string>
}

export interface FleetRow {
  vehicle_type: string
  current: number
  balance: number
  lean: number | null
  monte_carlo_p95: number | null
  mix: number | null
  own_vs_third: number | null
  gap: number
}

export interface CorridorOut {
  code: string
  name: string
  vehicle_type: string
  design_t: number
  mean_t: number
  std_t: number
  valid_days: number
  cycle_h: number
  trips_per_day: number
  effective_t_per_day: number
  lean_cycle_h: number | null
  value_added_pct: number | null
  waste_pct: number | null
  takt_min: number | null
}

export interface MonteCarloOut {
  seed: number
  days: number
  p50_total: number
  p90_total: number
  p95_total: number
  coverage_pct: number
}

export interface MixOut {
  status: string
  optimal: boolean
  total_vehicles: number
  total_cost_per_day: number | null
  message: string
  assignments: { corridor: string; vehicle_type: string; count: number }[]
}

export interface OwnVsThirdOut {
  vehicle_type: string
  days_used: number
  optimal_own: number
  optimal_cost_per_day: number
  all_third_party_cost_per_day: number
  all_own_cost_per_day: number
  curve: { own_fleet: number; daily_cost: number }[]
}

export interface ProjectionOut {
  scenario: string
  first_deficit_year: number | null
  years: { year: number; total_required: number; required_by_type: Record<string, number> }[]
}

export interface KpisOut {
  fleet_utilization: number | null
  oee: number
  fill_pct: number
  empty_km_pct: number
  daily_cost: number
  cost_per_ton: number | null
  cost_per_ton_km: number | null
  otif: number | null
}

export interface DashboardResponse {
  demo_label: string
  run_at: string
  algorithm_version: string
  base_year: number
  vehicle_types: string[]
  parameters: {
    design_percentile: number
    reserve: number
    window_days: number
    days_per_month: number
  }
  fleet: FleetRow[]
  totals: FleetRow
  corridors: CorridorOut[]
  monte_carlo: MonteCarloOut
  mix: MixOut
  own_vs_third: OwnVsThirdOut[]
  projections: ProjectionOut[]
  kpis: KpisOut
  findings: string[]
  warnings: string[]
  ml_forecast_available: boolean
}
