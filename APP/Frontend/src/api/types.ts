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
  | 'patterns:train'
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
  ml_forecast: MlForecastOut[]
}

/** Pronóstico del siguiente día frente al percentil histórico (tablero de capacidad). */
export interface MlForecastOut {
  corridor_code: string
  corridor_name: string
  day: string
  p50_t: number
  p90_t: number
  baseline_t: number | null
  historical_p90_t: number | null
}

// ------------------------------------------------------------------ patrones de ML
export interface MetricOut {
  label: string
  value: string
  hint: string
}

export interface ModelOut {
  name: string
  title: string
  version: number
  trained_at: string
  seed: number
  library: string
  artifact_sha256: string
  dataset_description: string
  metrics: MetricOut[]
  importances: [string, number][]
  notes: string[]
}

export interface CorridorForecastOut {
  corridor_code: string
  corridor_name: string
  recent: { day: string; tons: number }[]
  forecast: { day: string; p50_t: number; p90_t: number; baseline_t: number | null }[]
  historical_p90_t: number | null
}

export interface AnomalyOut {
  customer_code: string
  customer_name: string
  kind: string
  weekday: number
  hour_from: number
  hour_to: number
  events: number
  observed_min: number
  usual_min: number
  ratio: number | null
  severity: number
  message: string
}

export interface DelayRiskOut {
  customer_code: string
  customer_name: string
  hour: number
  probability: number
  traffic_factor: number
  stops_remaining: number
  order_kg: number
}

export interface SegmentOut {
  segment_id: number
  name: string
  description: string
  customers: string[]
  mean_service_min: number
  mean_order_kg: number
  mean_window_min: number
  weekly_variation: number
}

export interface PatternsOut {
  status: string
  demo_label: string
  provenance: string
  generated_at: string
  history_from: string | null
  history_to: string | null
  models: ModelOut[]
  forecasts: CorridorForecastOut[]
  anomalies: AnomalyOut[]
  delay_risks: DelayRiskOut[]
  segments: SegmentOut[]
  limits: string[]
  warnings: string[]
}

// ------------------------------------------------------------------ ruteo dinámico
export type VehicleStatus =
  | 'not_started'
  | 'traveling'
  | 'waiting'
  | 'serving'
  | 'returning'
  | 'at_depot'
  | 'broken'
  | 'standby'

export type RouteStatus = 'active' | 'broken' | 'standby'
export type StopState = 'completed' | 'in_service' | 'pending' | 'planned'
export type EventType =
  | 'road_closure'
  | 'urgent_order'
  | 'window_change'
  | 'breakdown'
  | 'delay_risk'
export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'superseded' | 'none_needed'

export interface ClockOut {
  now: string
  minute: number
  speed: number
  paused: boolean
  simulated: boolean
}

export interface EngineOut {
  engine: string
  score: number
  assigned_orders: number
  unassigned_orders: number
  elapsed_s: number
  chosen: boolean
}

export interface PlanSummaryOut {
  version: number
  base_version: number | null
  created_at: string
  created_by: string
  reason: string
  engine: string
  score: number
  late_stops: number
  delay_min: number
  vehicles_in_use: number
  unassigned: number
  notes: string[]
  comparison: EngineOut[]
}

export interface RoutingVehicle {
  id: string
  plate: string
  vehicle_type: string
  kind: 'own' | 'reserve' | 'third_party'
  route_status: RouteStatus
  status: VehicleStatus
  lat: number
  lon: number
  load_kg: number
  capacity_kg: number
  completed_stops: number
  pending_stops: number
  next_stop_label: string | null
  next_eta_min: number | null
  return_min: number | null
  delay_min: number
  late_stops: number
  note: string
  gps_status: 'ok' | 'no_signal' | 'n/a'
  gps_age_min: number | null
  gps_signal_enabled: boolean
}

export interface RoutingStop {
  vehicle_id: string
  plate: string
  sequence: number
  key: string
  kind: 'delivery' | 'transfer' | 'reload'
  order_id: string | null
  customer_code: string | null
  label: string
  lat: number
  lon: number
  window_start_min: number | null
  window_end_min: number | null
  arrival_min: number
  service_start_min: number
  departure_min: number
  delay_min: number
  wait_min: number
  kg: number
  state: StopState
  at_risk: boolean
  confirmed_by?: 'geofence' | 'driver' | null
  confirmed_min?: number | null
}

export interface UnassignedOut {
  order_id: string
  customer_code: string
  reason: string
}

export interface AlertOut {
  level: 'critical' | 'warning' | 'info'
  code: string
  message: string
  vehicle_id: string | null
}

export interface EventOut {
  id: string
  type: EventType
  occurred_at: string
  minute: number
  created_by: string
  summary: string
  outcome: string
  proposal_ids: string[]
}

export interface ImpactOut {
  late_stops_before: number
  delay_min_before: number
  late_stops_after: number
  delay_min_after: number
  score_before: number
  score_after: number
  affected_vehicles: string[]
  activates_reserve: boolean
  reserve_vehicle: string | null
  unattended_before: number
  unattended_orders: string[]
  notes: string[]
}

export interface ProposalRouteOut {
  vehicle_id: string
  plate: string
  status: RouteStatus
  return_min: number
  stops: { label: string; kind: string; arrival_min: number; delay_min: number }[]
}

export interface ProposalOut {
  id: string
  event_id: string
  event_type: EventType
  base_version: number
  proposed_version: number | null
  created_at: string
  reason: string
  summary: string
  status: ProposalStatus
  requires_confirmation: boolean
  impact: ImpactOut
  routes: ProposalRouteOut[]
  decided_by: string | null
  decided_at: string | null
  decision_comment: string
  applied_version: number | null
}

export interface RoutingSnapshot {
  demo_label: string
  clock: ClockOut
  depot: { name: string; lat: number; lon: number }
  plan: PlanSummaryOut
  versions: PlanSummaryOut[]
  vehicles: RoutingVehicle[]
  stops: RoutingStop[]
  unassigned: UnassignedOut[]
  events: EventOut[]
  proposals: ProposalOut[]
  alerts: AlertOut[]
  travel_notice: string | null
  provider_available: boolean
  customers: [string, string][]
  pending_orders: [string, string][]
  reports: ReportOut[]
}

export type EventRequest =
  | {
      type: 'road_closure'
      label: string
      lat: number
      lon: number
      radius_km: number
      factor: number
      duration_min: number
    }
  | {
      type: 'urgent_order'
      customer_code: string
      kg: number
      m3: number
      window_start: string
      window_end: string
    }
  | { type: 'window_change'; order_id: string; window_start: string; window_end: string }
  | { type: 'breakdown'; vehicle_id: string }

export interface EventResultOut {
  event: EventOut
  proposal: ProposalOut
}

export interface DecisionOut {
  proposal: ProposalOut
  replacement: ProposalOut | null
  plan_version: number | null
  message: string
}

export type SimulationAction =
  | 'pause'
  | 'resume'
  | 'speed'
  | 'advance'
  | 'provider'
  | 'gps_signal'

export interface PlanDetailOut {
  summary: PlanSummaryOut
  routes: { vehicle_id: string; plate: string; status: RouteStatus; note: string; stops: RoutingStop[] }[]
  unassigned: UnassignedOut[]
}

export interface KpiOut {
  committed_orders: number
  delivered_orders: number
  on_time_orders: number
  otif_orders: number
  late_orders: number
  unattended_orders: number
  incomplete_orders: number
  total_delay_min: number
  punctuality: number | null
  otif: number | null
}

export interface ScenarioOut {
  key: string
  title: string
  description: string
  mode: 'static' | 'dynamic'
  incomplete_rate: number
  kpis: KpiOut
  plan_versions: number
  reserve_activations: number
  events: string[]
}

export interface IndicatorsOut {
  demo_label: string
  live: {
    minute: number
    plan_version: number
    projected: KpiOut
    delivered_so_far: number
    on_time_so_far: number
  }
  scenarios: ScenarioOut[]
  definitions: string[]
}

export type IncidentKind =
  | 'customer_absent'
  | 'access_blocked'
  | 'damaged_goods'
  | 'vehicle_issue'
  | 'other'

export interface ReportOut {
  id: string
  vehicle_id: string
  plate: string
  minute: number
  kind: IncidentKind
  detail: string
  by: string
  order_id: string | null
}

export interface DriverRouteOut {
  demo_label: string
  vehicle_id: string
  plate: string
  vehicle_status: VehicleStatus
  route_status: RouteStatus
  plan_version: number
  clock: ClockOut
  depot: { name: string; lat: number; lon: number }
  stops: { stop: RoutingStop; address: string }[]
  next_key: string | null
  nav_links: { label: string; url: string; stops: number }[]
  load_kg: number
  capacity_kg: number
  return_min: number | null
  delay_min: number
  notices: string[]
  reports: ReportOut[]
}

export interface ConfirmationOut {
  order_id: string
  source: 'driver' | 'geofence'
  minute: number
  already_confirmed: boolean
}

// ------------------------------------------------------------------ maestros y parámetros
export type FieldType = 'text' | 'int' | 'number' | 'percent' | 'time' | 'date' | 'select' | 'bool'

export interface FieldSpec {
  name: string
  label: string
  type: FieldType
  required: boolean
  min: number | null
  max: number | null
  exclusive_min: boolean
  max_length: number
  options: [string, string][]
  options_from: 'vehicle_types' | 'corridors' | 'customers' | null
  help: string
  unit: string
}

export interface EntitySpec {
  name: string
  label: string
  plural: string
  description: string
  key_fields: string[]
  csv: boolean
  fields: FieldSpec[]
}

export interface ParameterSpec {
  key: string
  area: 'capacidad' | 'ruteo'
  label: string
  help: string
  field: FieldSpec
}

export interface MasterSchema {
  demo_label: string
  entities: EntitySpec[]
  parameters: ParameterSpec[]
  lookups: {
    vehicle_types: string[]
    corridors: [string, string][]
    customers: [string, string][]
  }
}

export type MasterRow = Record<string, string | number | boolean | null>

export interface MasterRows {
  entity: string
  total: number
  rows: MasterRow[]
  truncated: boolean
}

export interface CsvPreview {
  entity: string
  rows_total: number
  rows_valid: number
  to_create: number
  to_update: number
  errors: { row: number; column: string; message: string }[]
  errors_truncated: boolean
  sample: MasterRow[]
  can_apply: boolean
}

export interface ParameterVersion {
  value: string | number
  valid_from: string
  set_by: string
  set_at: string
  note: string
  in_force: boolean
  scheduled: boolean
}

export interface ParameterOut extends ParameterSpec {
  value: string | number
  valid_from: string
  versions: ParameterVersion[]
}

export interface ChangeRecord {
  id: string
  at: string
  actor: string
  entity: string
  key: string
  action: 'create' | 'update' | 'delete' | 'csv' | 'parameter'
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  valid_from: string | null
  note: string
}
