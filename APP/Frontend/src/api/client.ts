import { ApiError, networkError, parseApiError } from './errors'
import type {
  AuditEvent,
  DashboardResponse,
  LoginRequest,
  ProvisionResponse,
  SessionResponse,
  TenantOut,
  UserInfo,
} from './types'

type FetchLike = typeof fetch

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
  /** false para login/refresh: no se envía el token ni se reintenta. */
  auth?: boolean
}

/**
 * Cliente HTTP único: ningún componente arma URLs de la API.
 *
 * - El access token vive solo en memoria (no en localStorage/sessionStorage).
 * - El refresh token es una cookie HttpOnly que el navegador envía; JavaScript nunca la ve.
 * - Ante un 401 se intenta UN refresco y se repite la solicitud; si falla, se avisa que la
 *   sesión terminó.
 */
export class ApiClient {
  private accessToken: string | null = null
  private inFlightRefresh: Promise<SessionResponse> | null = null
  onSessionEnded: (() => void) | null = null

  constructor(
    private readonly baseUrl = '/api/v1',
    private readonly fetchImpl: FetchLike = (...args) => fetch(...args),
  ) {}

  setAccessToken(token: string | null): void {
    this.accessToken = token
  }

  private async send(path: string, options: RequestOptions): Promise<Response> {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (options.body !== undefined) headers['Content-Type'] = 'application/json'
    if (options.auth !== false && this.accessToken) {
      headers.Authorization = `Bearer ${this.accessToken}`
    }
    try {
      return await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: options.method ?? 'GET',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: 'include',
        signal: options.signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw error
      throw networkError()
    }
  }

  private async parse<T>(response: Response): Promise<T> {
    if (response.status === 204) return undefined as T
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    if (!response.ok) throw parseApiError(response.status, body)
    return body as T
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.send(path, options)
    if (response.status === 401 && options.auth !== false) {
      try {
        await this.refreshSession()
      } catch {
        this.onSessionEnded?.()
        throw parseApiError(401, await response.json().catch(() => null))
      }
      return this.parse<T>(await this.send(path, options))
    }
    return this.parse<T>(response)
  }

  /** Deduplica refrescos simultáneos: rotar dos veces el mismo token invalidaría la sesión. */
  refreshSession(): Promise<SessionResponse> {
    this.inFlightRefresh ??= this.request<SessionResponse>('/auth/refresh', {
      method: 'POST',
      auth: false,
    })
      .then((session) => {
        this.accessToken = session.access_token
        return session
      })
      .finally(() => {
        this.inFlightRefresh = null
      })
    return this.inFlightRefresh
  }

  async login(body: LoginRequest): Promise<SessionResponse> {
    const session = await this.request<SessionResponse>('/auth/login', {
      method: 'POST',
      body,
      auth: false,
    })
    this.accessToken = session.access_token
    return session
  }

  async logout(): Promise<void> {
    try {
      await this.request<void>('/auth/logout', { method: 'POST' })
    } finally {
      this.accessToken = null
    }
  }

  me(signal?: AbortSignal): Promise<UserInfo> {
    return this.request<UserInfo>('/me', { signal })
  }

  dashboard(signal?: AbortSignal): Promise<DashboardResponse> {
    return this.request<DashboardResponse>('/capacity/dashboard', { signal })
  }

  tenants(signal?: AbortSignal): Promise<TenantOut[]> {
    return this.request<TenantOut[]>('/tenants', { signal })
  }

  provisionTenant(slug: string, name: string): Promise<ProvisionResponse> {
    return this.request<ProvisionResponse>('/tenants', { method: 'POST', body: { slug, name } })
  }

  suspendTenant(slug: string): Promise<TenantOut> {
    return this.request<TenantOut>(`/tenants/${encodeURIComponent(slug)}/suspend`, {
      method: 'POST',
    })
  }

  reactivateTenant(slug: string): Promise<TenantOut> {
    return this.request<TenantOut>(`/tenants/${encodeURIComponent(slug)}/reactivate`, {
      method: 'POST',
    })
  }

  audit(signal?: AbortSignal): Promise<AuditEvent[]> {
    return this.request<AuditEvent[]>('/audit?limit=200', { signal })
  }
}

export { ApiError }
