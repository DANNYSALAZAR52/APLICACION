import { vi } from 'vitest'

import type { ApiClient } from '../api/client'
import type {
  AuditEvent,
  ChangeRecord,
  DashboardResponse,
  DriverRouteOut,
  MasterRows,
  MasterSchema,
  ParameterOut,
  PatternsOut,
  IndicatorsOut,
  KpiOut,
  Permission,
  PlanDetailOut,
  ProposalOut,
  Role,
  RoutingSnapshot,
  SessionResponse,
  TenantOut,
  UserInfo,
} from '../api/types'

const PERMISSIONS: Record<Role, Permission[]> = {
  management: [
    'capacity:read',
    'capacity:recalculate',
    'patterns:read',
    'patterns:train',
    'indicators:read',
  ],
  dispatcher: ['routing:read', 'routing:events', 'indicators:read', 'patterns:read'],
  driver: ['driver:route'],
  tenant_admin: ['capacity:read', 'master_data:manage', 'audit:read'],
  super_admin: ['tenants:manage', 'audit:read'],
}

export function makeUser(role: Role, overrides: Partial<UserInfo> = {}): UserInfo {
  return {
    id: `u-${role}`,
    username: role,
    display_name: `Usuario ${role}`,
    role,
    tenant_slug: role === 'super_admin' ? null : 'empresa-demo-a',
    tenant_name: role === 'super_admin' ? null : 'Empresa Demo A',
    permissions: PERMISSIONS[role],
    ...overrides,
  }
}

export const makeSession = (user: UserInfo): SessionResponse => ({
  access_token: 'token-de-prueba',
  token_type: 'bearer',
  expires_at: '2026-10-13T13:15:00Z',
  user,
})

export function makeDashboard(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
  const row = (t: string, current: number, balance: number) => ({
    vehicle_type: t,
    current,
    balance,
    lean: balance - 3,
    monte_carlo_p95: balance - 1,
    mix: balance - 5,
    own_vs_third: balance - 2,
    gap: current - balance,
  })
  return {
    demo_label: 'DATOS DE DEMOSTRACIÓN',
    run_at: '2026-10-13T13:00:00Z',
    algorithm_version: 'capacity-1.0.0',
    base_year: 2026,
    vehicle_types: ['sencillo', 'turbo'],
    parameters: { design_percentile: 0.9, reserve: 0.08, window_days: 60, days_per_month: 26 },
    fleet: [row('sencillo', 10, 9), row('turbo', 15, 17)],
    totals: {
      vehicle_type: 'TOTAL',
      current: 25,
      balance: 26,
      lean: 20,
      monte_carlo_p95: 24,
      mix: 21,
      own_vs_third: 23,
      gap: -1,
    },
    corridors: [
      {
        code: 'URB-N',
        name: 'Distribución urbana norte',
        vehicle_type: 'turbo',
        design_t: 38.5,
        mean_t: 30.2,
        std_t: 6.1,
        valid_days: 55,
        cycle_h: 6.15,
        trips_per_day: 1.63,
        effective_t_per_day: 4.5,
        lean_cycle_h: 4.9,
        value_added_pct: 0.2,
        waste_pct: 0.4,
        takt_min: 120.5,
      },
    ],
    monte_carlo: { seed: 7, days: 1000, p50_total: 22, p90_total: 23, p95_total: 24, coverage_pct: 38.5 },
    mix: {
      status: 'optimal',
      optimal: true,
      total_vehicles: 21,
      total_cost_per_day: 40_000_000,
      message: '',
      assignments: [{ corridor: 'URB-N', vehicle_type: 'turbo', count: 9 }],
    },
    own_vs_third: [
      {
        vehicle_type: 'turbo',
        days_used: 40,
        optimal_own: 2,
        optimal_cost_per_day: 330,
        all_third_party_cost_per_day: 375,
        all_own_cost_per_day: 425,
        curve: [
          { own_fleet: 0, daily_cost: 375 },
          { own_fleet: 1, daily_cost: 335 },
          { own_fleet: 2, daily_cost: 330 },
        ],
      },
    ],
    projections: [
      {
        scenario: 'base',
        first_deficit_year: 2027,
        years: [
          { year: 2027, total_required: 28, required_by_type: { sencillo: 10, turbo: 18 } },
          { year: 2028, total_required: 30, required_by_type: { sencillo: 11, turbo: 19 } },
        ],
      },
      {
        scenario: 'pesimista',
        first_deficit_year: null,
        years: [
          { year: 2027, total_required: 24, required_by_type: { sencillo: 9, turbo: 15 } },
          { year: 2028, total_required: 24, required_by_type: { sencillo: 9, turbo: 15 } },
        ],
      },
    ],
    kpis: {
      fleet_utilization: 1.04,
      oee: 0.727,
      fill_pct: 0.895,
      empty_km_pct: 0.353,
      daily_cost: 58_575_490,
      cost_per_ton: 109_319.3,
      cost_per_ton_km: 374.5,
      otif: null,
    },
    findings: ['Balance: se requieren 26 vehículos frente a 25 en la flota actual.'],
    warnings: ['Pronóstico de demanda con ML no disponible en esta fase; se usa el percentil histórico.'],
    ml_forecast_available: false,
    ml_forecast: [],
    ...overrides,
  }
}

export const TENANTS: TenantOut[] = [
  { slug: 'empresa-demo-a', name: 'Empresa Demo A', status: 'active', created_at: '2026-10-13T13:00:00Z', user_count: 4 },
  { slug: 'empresa-demo-b', name: 'Empresa Demo B', status: 'suspended', created_at: '2026-10-13T13:00:00Z', user_count: 4 },
]

export const AUDIT: AuditEvent[] = [
  {
    at: '2026-10-13T13:01:00Z',
    action: 'auth.login',
    outcome: 'failure',
    actor_username: 'gerencia',
    tenant_id: 't-a',
    resource: '',
    detail: { reason: 'bad_password' },
  },
  {
    at: '2026-10-13T13:02:00Z',
    action: 'capacity.dashboard.view',
    outcome: 'success',
    actor_username: 'gerencia',
    tenant_id: 't-a',
    resource: 'capacity/dashboard',
    detail: {},
  },
]


// ------------------------------------------------------------------ ruteo dinámico
const stop = (
  vehicle: string,
  plate: string,
  sequence: number,
  key: string,
  label: string,
  arrival: number,
  state: 'completed' | 'in_service' | 'pending' | 'planned',
  extra: Partial<RoutingSnapshot['stops'][number]> = {},
): RoutingSnapshot['stops'][number] => ({
  vehicle_id: vehicle,
  plate,
  sequence,
  key,
  kind: 'delivery',
  order_id: key,
  customer_code: `C-${key}`,
  label,
  lat: 4.65 + sequence * 0.01,
  lon: -74.1,
  window_start_min: 420,
  window_end_min: 720,
  arrival_min: arrival,
  service_start_min: arrival,
  departure_min: arrival + 20,
  delay_min: 0,
  wait_min: 0,
  kg: 300,
  state,
  at_risk: false,
  ...extra,
})

export function makeProposal(overrides: Partial<ProposalOut> = {}): ProposalOut {
  return {
    id: 'PR-001',
    event_id: 'EV-001',
    event_type: 'road_closure',
    base_version: 1,
    proposed_version: 2,
    created_at: '2026-10-14T08:15:00-05:00',
    reason: 'Cierre vial: Calle 80',
    summary: 'Se re-secuencian las entregas pendientes de: T-02.',
    status: 'pending',
    requires_confirmation: false,
    impact: {
      late_stops_before: 3,
      delay_min_before: 97,
      late_stops_after: 0,
      delay_min_after: 0,
      score_before: 2400,
      score_after: 600,
      affected_vehicles: ['V-02'],
      activates_reserve: false,
      reserve_vehicle: null,
      unattended_before: 0,
      unattended_orders: [],
      notes: ['Factor ×2.5 en un radio de 2.5 km durante 255 min.'],
    },
    routes: [
      {
        vehicle_id: 'V-02',
        plate: 'T-02',
        status: 'active',
        return_min: 700,
        stops: [
          { label: 'Cliente 02 · Fontibón', kind: 'delivery', arrival_min: 560, delay_min: 0 },
          { label: 'Cliente 07 · Suba', kind: 'delivery', arrival_min: 610, delay_min: 0 },
        ],
      },
    ],
    decided_by: null,
    decided_at: null,
    decision_comment: '',
    applied_version: null,
    ...overrides,
  }
}

export function makeSnapshot(overrides: Partial<RoutingSnapshot> = {}): RoutingSnapshot {
  const plan = {
    version: 1,
    base_version: null,
    created_at: '2026-10-14T05:00:00-05:00',
    created_by: 'sistema (05:00)',
    reason: 'Plan inicial de la mañana',
    engine: 'OR-Tools (VRP con ventanas y capacidad)',
    score: 600,
    late_stops: 0,
    delay_min: 0,
    vehicles_in_use: 2,
    unassigned: 0,
    notes: [],
    comparison: [
      { engine: 'OR-Tools (VRP con ventanas y capacidad)', score: 600, assigned_orders: 4, unassigned_orders: 0, elapsed_s: 2.5, chosen: true },
      { engine: 'Heurística (arrepentimiento + 2-opt + reubicación)', score: 640, assigned_orders: 4, unassigned_orders: 0, elapsed_s: 0.8, chosen: false },
    ],
  }
  const vehicle = (
    id: string,
    plate: string,
    kind: 'own' | 'reserve' | 'third_party',
    extra: Partial<RoutingSnapshot['vehicles'][number]> = {},
  ): RoutingSnapshot['vehicles'][number] => ({
    id,
    plate,
    vehicle_type: 'turbo',
    kind,
    route_status: kind === 'own' ? 'active' : 'standby',
    status: kind === 'own' ? 'traveling' : 'standby',
    lat: 4.68,
    lon: -74.12,
    load_kg: 900,
    capacity_kg: 4050,
    completed_stops: 1,
    pending_stops: 1,
    next_stop_label: 'Cliente 02 · Fontibón',
    next_eta_min: 560,
    return_min: 700,
    delay_min: 0,
    late_stops: 0,
    note: '',
    gps_status: kind === 'own' ? 'ok' : 'n/a',
    gps_age_min: kind === 'own' ? 1 : null,
    gps_signal_enabled: true,
    ...extra,
  })
  return {
    demo_label: 'DATOS DE DEMOSTRACIÓN',
    clock: { now: '2026-10-14T08:15:00-05:00', minute: 495, speed: 30, paused: true, simulated: true },
    depot: { name: 'CEDI Funza (demostración)', lat: 4.7165, lon: -74.2125 },
    plan,
    versions: [plan],
    vehicles: [
      vehicle('V-01', 'T-01', 'own'),
      vehicle('V-02', 'T-02', 'own', { delay_min: 20, late_stops: 1 }),
      vehicle('V-03', 'T-03 (reserva)', 'reserve', { load_kg: 0, completed_stops: 0, pending_stops: 0, next_stop_label: null, next_eta_min: null, return_min: null }),
    ],
    stops: [
      stop('V-01', 'T-01', 1, 'P-001', 'Cliente 01 · Engativá', 450, 'completed'),
      stop('V-01', 'T-01', 2, 'P-002', 'Cliente 02 · Fontibón', 560, 'pending'),
      stop('V-02', 'T-02', 1, 'P-003', 'Cliente 03 · Suba', 470, 'completed'),
      stop('V-02', 'T-02', 2, 'P-004', 'Cliente 04 · Usaquén', 700, 'pending', { delay_min: 20, window_end_min: 680 }),
    ],
    unassigned: [],
    events: [],
    proposals: [],
    alerts: [],
    travel_notice: null,
    provider_available: true,
    customers: [
      ['C-001', 'Cliente 01 · Engativá'],
      ['C-002', 'Cliente 02 · Fontibón'],
    ],
    pending_orders: [
      ['P-002', 'Cliente 02 · Fontibón'],
      ['P-004', 'Cliente 04 · Usaquén'],
    ],
    reports: [],
    ...overrides,
  }
}

export function makePlanDetail(version: number): PlanDetailOut {
  const base = makeSnapshot()
  const order = version === 1 ? ['P-003', 'P-004'] : ['P-004', 'P-003']
  return {
    summary: { ...base.plan, version, reason: version === 1 ? base.plan.reason : 'Cierre vial: Calle 80', score: version === 1 ? 600 : 520 },
    routes: [
      {
        vehicle_id: 'V-02',
        plate: 'T-02',
        status: 'active',
        note: '',
        stops: order.map((id, i) => stop('V-02', 'T-02', i + 1, id, `Cliente ${id}`, 500 + i * 30, 'planned')),
      },
    ],
    unassigned: [],
  }
}

const kpis = (over: Partial<KpiOut> = {}): KpiOut => ({
  committed_orders: 37,
  delivered_orders: 37,
  on_time_orders: 31,
  otif_orders: 31,
  late_orders: 6,
  unattended_orders: 0,
  incomplete_orders: 0,
  total_delay_min: 173,
  punctuality: 31 / 37,
  otif: 31 / 37,
  ...over,
})

export function makeIndicators(): IndicatorsOut {
  const scenario = (
    key: string,
    title: string,
    mode: 'static' | 'dynamic',
    k: KpiOut,
    versions: number,
    reserves: number,
    rate = 0,
  ) => ({
    key,
    title,
    description: `Descripción de ${title}`,
    mode,
    incomplete_rate: rate,
    kpis: k,
    plan_versions: versions,
    reserve_activations: reserves,
    events: ['Cierre vial', 'Avería'],
  })
  return {
    demo_label: 'DATOS DE DEMOSTRACIÓN',
    live: {
      minute: 495,
      plan_version: 1,
      projected: kpis({ committed_orders: 36, delivered_orders: 36, on_time_orders: 36, otif_orders: 36, late_orders: 0, total_delay_min: 0, punctuality: 1, otif: 1 }),
      delivered_so_far: 8,
      on_time_so_far: 8,
    },
    scenarios: [
      scenario('clean', 'Sin eventos · plan de la mañana', 'static', kpis({ committed_orders: 36, delivered_orders: 36, on_time_orders: 36, otif_orders: 36, late_orders: 0, total_delay_min: 0, punctuality: 1, otif: 1 }), 1, 0),
      scenario('static_events', 'Con eventos · plan estático', 'static', kpis({ delivered_orders: 32, on_time_orders: 29, otif_orders: 29, late_orders: 3, unattended_orders: 5, total_delay_min: 197, punctuality: 29 / 37, otif: 29 / 37 }), 1, 0),
      scenario('dynamic_events', 'Con eventos · ruteo dinámico', 'dynamic', kpis(), 5, 1),
      scenario('dynamic_incomplete', 'Con eventos · ruteo dinámico · 10 % de entregas incompletas (ejemplo)', 'dynamic', kpis({ otif_orders: 28, incomplete_orders: 3, otif: 28 / 37 }), 5, 1, 0.1),
    ],
    definitions: [
      'Puntualidad = pedidos entregados dentro de su ventana / pedidos comprometidos del día.',
      'OTIF = pedidos entregados completos y a tiempo / pedidos comprometidos del día.',
    ],
  }
}

export function makeDriverRoute(overrides: Partial<DriverRouteOut> = {}): DriverRouteOut {
  const base = makeSnapshot()
  const mine = base.stops.filter((s) => s.vehicle_id === 'V-01')
  return {
    demo_label: 'DATOS DE DEMOSTRACIÓN',
    vehicle_id: 'V-01',
    plate: 'T-01',
    vehicle_status: 'traveling',
    route_status: 'active',
    plan_version: 1,
    clock: base.clock,
    depot: base.depot,
    stops: mine.map((stop) => ({ stop, address: `Dirección de ${stop.label}` })),
    next_key: 'P-002',
    nav_links: [
      {
        label: 'Abrir la ruta en Google Maps',
        url: 'https://www.google.com/maps/dir/?api=1&destination=4.67%2C-74.1&travelmode=driving',
        stops: 1,
      },
    ],
    load_kg: 900,
    capacity_kg: 4050,
    return_min: 700,
    delay_min: 0,
    notices: [],
    reports: [],
    ...overrides,
  }
}


// ------------------------------------------------------------------ maestros
const field = (
  name: string,
  label: string,
  type: MasterSchema['entities'][number]['fields'][number]['type'],
  extra: Partial<MasterSchema['entities'][number]['fields'][number]> = {},
): MasterSchema['entities'][number]['fields'][number] => ({
  name,
  label,
  type,
  required: true,
  min: null,
  max: null,
  exclusive_min: false,
  max_length: 120,
  options: [],
  options_from: null,
  help: '',
  unit: '',
  ...extra,
})

export function makeMasterSchema(): MasterSchema {
  const entity = (
    name: string,
    label: string,
    plural: string,
    keyFields: string[],
    fields: ReturnType<typeof field>[],
    csv = true,
  ) => ({ name, label, plural, description: `Descripción de ${plural}`, key_fields: keyFields, csv, fields })
  return {
    demo_label: 'DATOS DE DEMOSTRACIÓN',
    entities: [
      entity('vehicle_type', 'Tipo de vehículo', 'Tipos de vehículo', ['name'], [
        field('name', 'Nombre', 'text'),
        field('capacity_t', 'Capacidad (t)', 'number', { min: 0, exclusive_min: true, unit: 't' }),
        field('pallets', 'Pallets', 'int', { min: 0 }),
      ]),
      entity('corridor', 'Corredor', 'Corredores', ['code'], [
        field('code', 'Código', 'text'),
        field('assigned_vehicle_type', 'Tipo de vehículo asignado', 'select', { options_from: 'vehicle_types' }),
        field('fill', 'Llenado', 'percent', { min: 0, max: 100, unit: '%' }),
      ]),
      entity('customer', 'Cliente', 'Clientes', ['code'], [
        field('code', 'Código', 'text'),
        field('name', 'Nombre', 'text'),
        field('address', 'Dirección', 'text', { required: false }),
        field('window_start', 'Ventana desde', 'time', { help: 'Formato HH:MM' }),
        field('window_end', 'Ventana hasta', 'time'),
      ]),
      entity('vehicle', 'Vehículo', 'Vehículos', ['id'], [
        field('id', 'Identificador', 'text'),
        field('kind', 'Condición', 'select', { options: [['own', 'Propio'], ['reserve', 'Reserva']] }),
      ]),
    ],
    parameters: [],
    lookups: {
      vehicle_types: ['turbo', 'sencillo'],
      corridors: [['URB-N', 'Urbana norte']],
      customers: [['C-001', 'Cliente 01']],
    },
  }
}

export const MASTER_ROWS: Record<string, MasterRows> = {
  vehicle_type: {
    entity: 'vehicle_type',
    total: 2,
    truncated: false,
    rows: [
      { name: 'sencillo', capacity_t: 8, pallets: 14 },
      { name: 'turbo', capacity_t: 4.5, pallets: 8 },
    ],
  },
  corridor: {
    entity: 'corridor',
    total: 1,
    truncated: false,
    rows: [{ code: 'URB-N', assigned_vehicle_type: 'turbo', fill: 85 }],
  },
  customer: {
    entity: 'customer',
    total: 1,
    truncated: false,
    rows: [{ code: 'C-001', name: 'Cliente 01', address: 'Calle 1', window_start: '08:00', window_end: '12:00' }],
  },
  vehicle: {
    entity: 'vehicle',
    total: 1,
    truncated: true,
    rows: [{ id: 'V-01', kind: 'own' }],
  },
}

export function makeParameters(): ParameterOut[] {
  const param = (
    key: string,
    area: 'capacidad' | 'ruteo',
    label: string,
    type: 'percent' | 'int' | 'time',
    value: string | number,
    unit = '',
  ): ParameterOut => ({
    key,
    area,
    label,
    help: key === 'reserve' ? 'Reserva de flota sobre la requerida.' : '',
    field: field(key, label, type, { min: 0, max: 100, unit }),
    value,
    valid_from: '2000-01-01',
    versions: [
      { value, valid_from: '2000-01-01', set_by: 'sistema', set_at: '2026-10-14T08:00:00-05:00', note: 'Valor inicial de la demo', in_force: true, scheduled: false },
    ],
  })
  return [
    param('reserve', 'capacidad', 'Reserva de flota', 'percent', 8, '%'),
    param('days_per_month', 'capacidad', 'Días operativos por mes', 'int', 26, 'días'),
    param('departure', 'ruteo', 'Hora de salida', 'time', '06:00'),
  ]
}

export const HISTORY: ChangeRecord[] = [
  { id: 'CH-00003', at: '2026-10-14T09:10:00-05:00', actor: 'admin', entity: 'vehicle_type', key: 'turbo', action: 'update', before: { pallets: 8 }, after: { pallets: 9 }, valid_from: null, note: '' },
  { id: 'CH-00002', at: '2026-10-14T09:05:00-05:00', actor: 'admin', entity: 'parameter', key: 'reserve', action: 'parameter', before: { value: 8 }, after: { value: 12 }, valid_from: '2026-11-01', note: 'Temporada alta' },
  { id: 'CH-00001', at: '2026-10-14T09:00:00-05:00', actor: 'admin', entity: 'customer', key: 'C-9', action: 'create', before: null, after: { code: 'C-9' }, valid_from: null, note: '' },
]

export function makePatterns(overrides: Partial<PatternsOut> = {}): PatternsOut {
  const days = ['2026-10-10', '2026-10-11', '2026-10-12']
  return {
    status: 'ok',
    demo_label: 'DATOS DE DEMOSTRACIÓN',
    provenance:
      'DATOS SINTÉTICOS de demostración, semilla 20261001: 90 días, 8 corredores y 36 clientes.',
    generated_at: '2026-10-14T09:00:00-05:00',
    history_from: '2026-07-12',
    history_to: '2026-10-09',
    models: [
      {
        name: 'pronostico_demanda',
        title: 'Pronóstico de demanda por corredor',
        version: 1,
        trained_at: '2026-10-14T09:00:00-05:00',
        seed: 20261001,
        library: 'scikit-learn 1.9.1',
        artifact_sha256: 'a'.repeat(64),
        dataset_description: 'sintético',
        metrics: [
          { label: 'Error medio absoluto (MAE)', value: '2,73 t', hint: 'Menor es mejor.' },
          { label: 'MAE de la línea base ingenua', value: '5,20 t', hint: '' },
        ],
        importances: [
          ['día de la semana', 0.84],
          ['quincena', 0.11],
        ],
        notes: ['Horizonte máximo de 7 días.'],
      },
      {
        name: 'riesgo_retraso',
        title: 'Riesgo de retraso',
        version: 1,
        trained_at: '2026-10-14T09:00:00-05:00',
        seed: 20261001,
        library: 'scikit-learn 1.9.1',
        artifact_sha256: 'b'.repeat(64),
        dataset_description: 'sintético',
        metrics: [{ label: 'AUC', value: '0,680', hint: '0,5 equivale a azar.' }],
        importances: [],
        notes: [],
      },
    ],
    forecasts: [
      {
        corridor_code: 'URB-N',
        corridor_name: 'Distribución urbana norte',
        recent: [
          { day: '2026-10-08', tons: 31.2 },
          { day: '2026-10-09', tons: 29.4 },
        ],
        forecast: days.map((day, i) => ({
          day,
          p50_t: 28 + i,
          p90_t: 33 + i,
          baseline_t: 30 + i,
        })),
        historical_p90_t: 35.5,
      },
      {
        corridor_code: 'TRK-MED',
        corridor_name: 'Bogotá–Medellín',
        recent: [{ day: '2026-10-09', tons: 90 }],
        forecast: days.map((day) => ({ day, p50_t: 88, p90_t: 99, baseline_t: null })),
        historical_p90_t: null,
      },
    ],
    anomalies: [
      {
        customer_code: 'C-022',
        customer_name: 'Cliente 22 · Puente Aranda',
        kind: 'espera',
        weekday: 4,
        hour_from: 10,
        hour_to: 12,
        events: 12,
        observed_min: 23,
        usual_min: 8,
        ratio: 2.9,
        severity: 6.4,
        message:
          'Cliente 22 · Puente Aranda tuvo esperas de 23 min en promedio los viernes entre las 10:00 y las 12:00, 2,9 veces su patrón habitual (8 min), en 12 visitas. Es una asociación estadística: no demuestra la causa.',
      },
    ],
    delay_risks: [
      {
        customer_code: 'C-014',
        customer_name: 'Cliente 14 · Kennedy',
        hour: 8,
        probability: 0.749,
        traffic_factor: 1.51,
        stops_remaining: 7,
        order_kg: 199,
      },
    ],
    segments: [
      {
        segment_id: 1,
        name: 'Ventana estrecha',
        description: '28 clientes; servicio medio 20 min, pedido medio 387 kg, ventana media 120 min.',
        customers: ['C-001', 'C-002'],
        mean_service_min: 20,
        mean_order_kg: 387,
        mean_window_min: 120,
        weekly_variation: 0.12,
      },
    ],
    limits: ['Los modelos se entrenaron con DATOS SINTÉTICOS de demostración.'],
    warnings: [],
    ...overrides,
  }
}

/** Cliente falso: sesión restaurada para el rol dado y respuestas de ejemplo. */
export function makeFakeClient(role: Role | null, overrides: Record<string, unknown> = {}) {
  const user = role ? makeUser(role) : null
  const fake = {
    onSessionEnded: null as (() => void) | null,
    setAccessToken: vi.fn(),
    refreshSession: vi.fn(() =>
      user ? Promise.resolve(makeSession(user)) : Promise.reject(new Error('sin sesión')),
    ),
    login: vi.fn(),
    logout: vi.fn(() => Promise.resolve()),
    me: vi.fn(),
    dashboard: vi.fn(() => Promise.resolve(makeDashboard())),
    tenants: vi.fn(() => Promise.resolve(TENANTS)),
    provisionTenant: vi.fn(),
    suspendTenant: vi.fn(() => Promise.resolve(TENANTS[0])),
    reactivateTenant: vi.fn(() => Promise.resolve(TENANTS[1])),
    audit: vi.fn(() => Promise.resolve(AUDIT)),
    tower: vi.fn(() => Promise.resolve(makeSnapshot())),
    track: vi.fn(() => Promise.resolve(makeSnapshot())),
    injectEvent: vi.fn(() => Promise.reject(new Error('sin respuesta preparada'))),
    decideProposal: vi.fn(() => Promise.reject(new Error('sin respuesta preparada'))),
    controlSimulation: vi.fn(() => Promise.resolve(makeSnapshot())),
    resetDay: vi.fn(() => Promise.resolve(makeSnapshot())),
    indicators: vi.fn(() => Promise.resolve(makeIndicators())),
    driverRoute: vi.fn(() => Promise.resolve(makeDriverRoute())),
    confirmDelivery: vi.fn(() => Promise.resolve({ order_id: 'P-002', source: 'driver', minute: 495, already_confirmed: false })),
    reportIncident: vi.fn(() => Promise.reject(new Error('sin respuesta preparada'))),
    watchTower: vi.fn(() => () => undefined),
    masterSchema: vi.fn(() => Promise.resolve(makeMasterSchema())),
    masterRows: vi.fn((entity: string) => Promise.resolve(MASTER_ROWS[entity] ?? { entity, total: 0, rows: [], truncated: false })),
    masterCreate: vi.fn((_: string, values: Record<string, unknown>) => Promise.resolve(values)),
    masterUpdate: vi.fn((_: string, __: string, values: Record<string, unknown>) => Promise.resolve(values)),
    masterDelete: vi.fn(() => Promise.resolve()),
    csvPreview: vi.fn(),
    csvApply: vi.fn(),
    masterParameters: vi.fn(() => Promise.resolve(makeParameters())),
    setParameter: vi.fn(() => Promise.resolve(makeParameters()[0])),
    masterHistory: vi.fn(() => Promise.resolve(HISTORY)),
    patterns: vi.fn(() => Promise.resolve(makePatterns())),
    retrainPatterns: vi.fn(() => Promise.resolve(makePatterns({ generated_at: '2026-10-14T10:00:00-05:00' }))),
    download: vi.fn(() => Promise.resolve({ blob: new Blob(['x']), filename: 'archivo.xlsx' })),
    planVersion: vi.fn((version: number) => Promise.resolve(makePlanDetail(version))),
    ...overrides,
  }
  return fake as unknown as ApiClient & typeof fake
}
