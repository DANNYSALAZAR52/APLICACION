import { vi } from 'vitest'

import type { ApiClient } from '../api/client'
import type {
  AuditEvent,
  DashboardResponse,
  Permission,
  Role,
  SessionResponse,
  TenantOut,
  UserInfo,
} from '../api/types'

const PERMISSIONS: Record<Role, Permission[]> = {
  management: ['capacity:read', 'capacity:recalculate', 'patterns:read', 'indicators:read'],
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
    ...overrides,
  }
  return fake as unknown as ApiClient & typeof fake
}
