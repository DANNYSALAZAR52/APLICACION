import { ApiError, networkError, parseApiError } from './errors'
import type {
  AuditEvent,
  ChangeRecord,
  ConfirmationOut,
  CsvPreview,
  DashboardResponse,
  DecisionOut,
  DriverRouteOut,
  EventRequest,
  EventResultOut,
  IncidentKind,
  IndicatorsOut,
  LoginRequest,
  MasterRow,
  MasterRows,
  MasterSchema,
  ParameterOut,
  PatternsOut,
  PlanDetailOut,
  ProvisionResponse,
  ReportOut,
  RoutingSnapshot,
  SessionResponse,
  SimulationAction,
  TenantOut,
  UserInfo,
} from './types'

type FetchLike = typeof fetch

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
  /** false para login/refresh: no se envía el token ni se reintenta. */
  auth?: boolean
  accept?: string
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
    const headers: Record<string, string> = { Accept: options.accept ?? 'application/json' }
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

  // ----------------------------------------------------------------- ruteo dinámico
  tower(signal?: AbortSignal): Promise<RoutingSnapshot> {
    return this.request<RoutingSnapshot>('/routing/tower', { signal })
  }

  /** Seguimiento periódico: recalcula horarios y puede proponer re-secuenciar. */
  track(signal?: AbortSignal): Promise<RoutingSnapshot> {
    return this.request<RoutingSnapshot>('/routing/track', { method: 'POST', signal })
  }

  injectEvent(body: EventRequest): Promise<EventResultOut> {
    return this.request<EventResultOut>('/routing/events', { method: 'POST', body })
  }

  decideProposal(id: string, decision: 'approve' | 'reject', comment: string): Promise<DecisionOut> {
    return this.request<DecisionOut>(`/routing/proposals/${encodeURIComponent(id)}/decision`, {
      method: 'POST',
      body: { decision, comment },
    })
  }

  controlSimulation(
    action: SimulationAction,
    value?: number,
    target?: string,
  ): Promise<RoutingSnapshot> {
    const body: Record<string, unknown> = { action }
    if (value !== undefined) body.value = value
    if (target !== undefined) body.target = target
    return this.request<RoutingSnapshot>('/routing/simulation', { method: 'POST', body })
  }

  /**
   * Estado de la torre de control en tiempo real (Server-Sent Events con `fetch`, para poder enviar
   * el token en la cabecera). El servidor cierra el flujo cada ~55 s: aquí se reconecta solo, con
   * el token renovado si hace falta. Tras 3 fallos seguidos avisa con `onUnavailable` para que la
   * pantalla vuelva a consultar periódicamente. Devuelve la función que lo cierra.
   */
  watchTower(
    onSnapshot: (snapshot: RoutingSnapshot) => void,
    onUnavailable: (error: unknown) => void,
    retryDelayMs = 1000,
  ): () => void {
    const controller = new AbortController()
    const run = async () => {
      let failures = 0
      while (!controller.signal.aborted) {
        try {
          let response = await this.send('/routing/stream', {
            signal: controller.signal,
            accept: 'text/event-stream',
          })
          if (response.status === 401) {
            await this.refreshSession()
            response = await this.send('/routing/stream', {
              signal: controller.signal,
              accept: 'text/event-stream',
            })
          }
          if (!response.ok || !response.body) throw parseApiError(response.status, null)
          failures = 0
          await readEventStream(response.body, (event, data) => {
            if (event === 'snapshot') onSnapshot(JSON.parse(data) as RoutingSnapshot)
          })
          // El servidor cerró el flujo (renovación periódica): pausa breve y se reconecta.
          await new Promise((resolve) => setTimeout(resolve, Math.min(retryDelayMs, 250)))
        } catch (error) {
          if (controller.signal.aborted) return
          failures += 1
          if (failures >= 3) {
            onUnavailable(error)
            return
          }
          await new Promise((resolve) => setTimeout(resolve, retryDelayMs * failures))
        }
      }
    }
    void run()
    return () => controller.abort()
  }

  resetDay(): Promise<RoutingSnapshot> {
    return this.request<RoutingSnapshot>('/routing/day/reset', { method: 'POST' })
  }

  indicators(signal?: AbortSignal): Promise<IndicatorsOut> {
    return this.request<IndicatorsOut>('/routing/indicators', { signal })
  }

  // ------------------------------------------------------------ hoja del conductor
  driverRoute(signal?: AbortSignal): Promise<DriverRouteOut> {
    return this.request<DriverRouteOut>('/routing/driver/route', { signal })
  }

  confirmDelivery(orderId: string): Promise<ConfirmationOut> {
    return this.request<ConfirmationOut>(
      `/routing/driver/deliveries/${encodeURIComponent(orderId)}/confirm`,
      { method: 'POST' },
    )
  }

  reportIncident(kind: IncidentKind, detail: string, orderId: string | null): Promise<ReportOut> {
    return this.request<ReportOut>('/routing/driver/reports', {
      method: 'POST',
      body: orderId === null ? { kind, detail } : { kind, detail, order_id: orderId },
    })
  }

  // ------------------------------------------------------- maestros y parámetros
  masterSchema(signal?: AbortSignal): Promise<MasterSchema> {
    return this.request<MasterSchema>('/masters/schema', { signal })
  }

  masterRows(entity: string, signal?: AbortSignal): Promise<MasterRows> {
    return this.request<MasterRows>(`/masters/entities/${encodeURIComponent(entity)}`, { signal })
  }

  masterCreate(entity: string, values: Record<string, unknown>): Promise<MasterRow> {
    return this.request<MasterRow>(`/masters/entities/${encodeURIComponent(entity)}`, {
      method: 'POST',
      body: { values },
    })
  }

  masterUpdate(entity: string, key: string, values: Record<string, unknown>): Promise<MasterRow> {
    return this.request<MasterRow>(
      `/masters/entities/${encodeURIComponent(entity)}/${encodeURIComponent(key)}`,
      { method: 'PUT', body: { values } },
    )
  }

  masterDelete(entity: string, key: string): Promise<void> {
    return this.request<void>(
      `/masters/entities/${encodeURIComponent(entity)}/${encodeURIComponent(key)}`,
      { method: 'DELETE' },
    )
  }

  csvPreview(entity: string, content: string): Promise<CsvPreview> {
    return this.request<CsvPreview>(
      `/masters/entities/${encodeURIComponent(entity)}/csv/preview`,
      { method: 'POST', body: { content } },
    )
  }

  csvApply(entity: string, content: string): Promise<{ created: number; updated: number }> {
    return this.request<{ created: number; updated: number }>(
      `/masters/entities/${encodeURIComponent(entity)}/csv/apply`,
      { method: 'POST', body: { content } },
    )
  }

  masterParameters(signal?: AbortSignal): Promise<ParameterOut[]> {
    return this.request<ParameterOut[]>('/masters/parameters', { signal })
  }

  setParameter(
    key: string,
    value: string | number,
    validFrom?: string,
    note?: string,
  ): Promise<ParameterOut> {
    const body: Record<string, unknown> = { value }
    if (validFrom) body.valid_from = validFrom
    if (note) body.note = note
    return this.request<ParameterOut>(`/masters/parameters/${encodeURIComponent(key)}`, {
      method: 'PUT',
      body,
    })
  }

  patterns(signal?: AbortSignal): Promise<PatternsOut> {
    return this.request<PatternsOut>('/patterns', { signal })
  }

  retrainPatterns(): Promise<PatternsOut> {
    return this.request<PatternsOut>('/patterns/retrain', { method: 'POST' })
  }

  masterHistory(entity?: string, signal?: AbortSignal): Promise<ChangeRecord[]> {
    const query = entity ? `&entity=${encodeURIComponent(entity)}` : ''
    return this.request<ChangeRecord[]>(`/masters/history?limit=200${query}`, { signal })
  }

  /** Descarga un archivo (Excel/CSV) del servidor con la sesión actual; devuelve su contenido. */
  async download(path: string): Promise<{ blob: Blob; filename: string }> {
    const send = () => this.send(path, { accept: '*/*' })
    let response = await send()
    if (response.status === 401) {
      try {
        await this.refreshSession()
      } catch {
        this.onSessionEnded?.()
        throw parseApiError(401, null)
      }
      response = await send()
    }
    if (!response.ok) {
      let body: unknown = null
      try {
        body = await response.json()
      } catch {
        body = null
      }
      throw parseApiError(response.status, body)
    }
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const match = /filename="([^"]+)"/.exec(disposition)
    return { blob: await response.blob(), filename: match?.[1] ?? 'descarga' }
  }

  planVersion(version: number, signal?: AbortSignal): Promise<PlanDetailOut> {
    return this.request<PlanDetailOut>(`/routing/plans/${version}`, { signal })
  }
}

/** Lee un flujo `text/event-stream` y entrega cada evento completo (nombre y datos). */
export async function readEventStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: string, data: string) => void,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })
    let cut = buffer.indexOf('\n\n')
    while (cut !== -1) {
      const block = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      let event = 'message'
      const data: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith(':')) continue // comentario / keep-alive
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trim())
      }
      if (data.length > 0 || event === 'end') onEvent(event, data.join('\n'))
      cut = buffer.indexOf('\n\n')
    }
  }
}

export { ApiError }
