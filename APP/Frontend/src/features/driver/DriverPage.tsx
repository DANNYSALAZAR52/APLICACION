import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError } from '../../api/errors'
import type { DriverRouteOut, IncidentKind } from '../../api/types'
import { Badge, Card, ConfirmDialog, ErrorState, LoadingState } from '../../components/common'
import { downloadCsv, saveBlob, toCsv } from '../../domain-ui/csv'
import { formatInt } from '../../domain-ui/format'
import {
  INCIDENT_LABELS,
  STOP_KIND_LABELS,
  formatClock,
  formatMinutes,
  vehicleStatusLabel,
  windowText,
} from '../../domain-ui/routing'
import { useAuth } from '../auth/AuthProvider'

/** Cada cuánto se actualiza la hoja de ruta (el despacho puede cambiarla en cualquier momento). */
export const DRIVER_REFRESH_MS = 5000

type Stop = DriverRouteOut['stops'][number]

const KINDS = Object.keys(INCIDENT_LABELS) as IncidentKind[]

function useDriverRoute() {
  const { client } = useAuth()
  const [route, setRoute] = useState<DriverRouteOut | null>(null)
  const [error, setError] = useState<unknown>(null)
  const alive = useRef(true)

  const load = useCallback(async () => {
    try {
      const next = await client.driverRoute()
      if (alive.current) {
        setRoute(next)
        setError(null)
      }
    } catch (e) {
      if (alive.current) setError(e)
    }
  }, [client])

  useEffect(() => {
    alive.current = true
    void load()
    const timer = window.setInterval(() => {
      if (!document.hidden) void load()
    }, DRIVER_REFRESH_MS)
    return () => {
      alive.current = false
      window.clearInterval(timer)
    }
  }, [load])

  return { route, error, reload: load }
}

function StopCard({
  item,
  highlight,
  busy,
  onConfirm,
  onReport,
}: {
  item: Stop
  highlight: boolean
  busy: boolean
  onConfirm: (orderId: string) => void
  onReport: (orderId: string | null) => void
}) {
  const s = item.stop
  const arrived = s.state === 'in_service' || s.state === 'completed'
  return (
    <li className={`driver-stop${highlight ? ' driver-stop-next' : ''}`} aria-current={highlight ? 'step' : undefined}>
      <div className="driver-stop-head">
        <span className="driver-seq" aria-hidden="true">
          {s.sequence}
        </span>
        <div>
          <strong>{s.label}</strong>
          <div className="muted small">{item.address}</div>
        </div>
      </div>
      <dl className="driver-facts">
        <div>
          <dt>Ventana</dt>
          <dd>{windowText(s)}</dd>
        </div>
        <div>
          <dt>Llegada estimada</dt>
          <dd>{formatClock(s.arrival_min)}</dd>
        </div>
        {s.kind === 'delivery' ? (
          <div>
            <dt>Carga a entregar</dt>
            <dd>{formatInt(s.kg)} kg</dd>
          </div>
        ) : (
          <div>
            <dt>Tipo</dt>
            <dd>{STOP_KIND_LABELS[s.kind]}</dd>
          </div>
        )}
      </dl>
      <div className="driver-badges">
        {s.confirmed_by ? (
          <Badge tone="ok">
            Entrega confirmada {s.confirmed_by === 'geofence' ? 'por geocerca' : 'por usted'} a las{' '}
            {formatClock(s.confirmed_min ?? null)}
          </Badge>
        ) : s.state === 'completed' ? (
          <Badge tone="neutral">Pasó por la parada (sin confirmar)</Badge>
        ) : s.state === 'in_service' ? (
          <Badge tone="warn">Atendiendo ahora</Badge>
        ) : s.delay_min > 0 ? (
          <Badge tone="bad">Llegaría {formatMinutes(s.delay_min)} tarde</Badge>
        ) : s.at_risk ? (
          <Badge tone="warn">Poca holgura</Badge>
        ) : (
          <Badge tone="neutral">Pendiente</Badge>
        )}
      </div>
      {s.kind === 'delivery' && s.order_id ? (
        <div className="driver-actions">
          {arrived && !s.confirmed_by ? (
            <button
              type="button"
              className="btn btn-primary btn-big"
              disabled={busy}
              onClick={() => onConfirm(s.order_id ?? '')}
              aria-label={`Confirmar entrega a ${s.label}`}
            >
              Confirmar entrega
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn-big"
            disabled={busy}
            onClick={() => onReport(s.order_id)}
            aria-label={`Reportar novedad en ${s.label}`}
          >
            Reportar novedad
          </button>
        </div>
      ) : null}
    </li>
  )
}

/** Hoja de ruta del conductor (pantalla 4): pensada para el celular. */
export function DriverPage() {
  const { client } = useAuth()
  const { route, error, reload } = useDriverRoute()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [reporting, setReporting] = useState<{ orderId: string | null } | null>(null)

  const [kind, setKind] = useState<IncidentKind>('customer_absent')
  const [detail, setDetail] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  if (!route) {
    return error ? <ErrorState error={error} onRetry={() => void reload()} /> : <LoadingState label="Cargando su hoja de ruta…" />
  }

  const remaining = route.stops.filter((s) => s.stop.state !== 'completed')
  const done = route.stops.filter((s) => s.stop.state === 'completed')
  const next = remaining[0]
  const failure = (e: unknown) =>
    setMessage({ tone: 'error', text: e instanceof ApiError ? e.message : 'No se pudo completar la acción. Intente de nuevo.' })

  const confirm = async () => {
    if (!confirming) return
    setBusy(true)
    try {
      const result = await client.confirmDelivery(confirming)
      setMessage({
        tone: 'ok',
        text: result.already_confirmed
          ? `La entrega ya estaba confirmada ${result.source === 'geofence' ? 'por geocerca' : 'por usted'}.`
          : 'Entrega confirmada. Gracias.',
      })
      setConfirming(null)
      await reload()
    } catch (e) {
      failure(e)
      setConfirming(null)
    } finally {
      setBusy(false)
    }
  }

  const sendReport = async (event: FormEvent) => {
    event.preventDefault()
    const text = detail.trim().replace(/\s+/g, ' ')
    if (text.length < 3 || text.length > 300) {
      setFormError('Describa la novedad en 3 a 300 caracteres.')
      return
    }
    setBusy(true)
    setFormError(null)
    try {
      await client.reportIncident(kind, text, reporting?.orderId ?? null)
      setMessage({ tone: 'ok', text: 'Novedad enviada al despachador.' })
      setReporting(null)
      setDetail('')
      await reload()
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : 'No se pudo enviar la novedad.')
    } finally {
      setBusy(false)
    }
  }

  const exportExcel = async () => {
    try {
      const file = await client.download('/routing/driver/route/export?format=xlsx')
      saveBlob(file.filename, file.blob)
    } catch (e) {
      failure(e)
    }
  }

  const exportCsv = () =>
    downloadCsv(
      `hoja-de-ruta-${route.plate.replace(/[^A-Za-z0-9-]/g, '')}.csv`,
      toCsv([
        [route.demo_label],
        ['Vehículo', route.plate, 'Plan versión', route.plan_version],
        [],
        ['#', 'Parada', 'Dirección', 'Ventana', 'Llegada estimada', 'Salida estimada', 'Carga (kg)', 'Estado'],
        ...route.stops.map(({ stop, address }) => [
          stop.sequence,
          stop.label,
          address,
          windowText(stop),
          formatClock(stop.arrival_min),
          formatClock(stop.departure_min),
          stop.kg,
          stop.state === 'completed' ? 'Entregada' : stop.state === 'in_service' ? 'En servicio' : 'Pendiente',
        ]),
      ]),
    )

  return (
    <div className="page driver-page">
      <div className="page-head">
        <div>
          <h1>Mi hoja de ruta</h1>
          <p className="muted">
            Vehículo <strong>{route.plate}</strong> · {vehicleStatusLabel(route.vehicle_status)} · hora simulada{' '}
            <strong>{formatClock(route.clock.minute)}</strong> · plan versión {route.plan_version}
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn" onClick={() => void exportExcel()} disabled={route.stops.length === 0}>
            Descargar Excel
          </button>
          <button type="button" className="btn" onClick={exportCsv} disabled={route.stops.length === 0}>
            Descargar CSV
          </button>
        </div>
      </div>

      {message ? (
        <div className={`alert ${message.tone === 'ok' ? 'alert-ok' : 'alert-error'}`} role={message.tone === 'ok' ? 'status' : 'alert'}>
          {message.text}{' '}
          <button type="button" className="btn btn-small" onClick={() => setMessage(null)}>
            Cerrar
          </button>
        </div>
      ) : null}
      {route.notices.map((n) => (
        <div key={n} className="alert alert-warn" role="status">
          {n}
        </div>
      ))}

      <div className="stats">
        <div className="stat">
          <div className="stat-label">Por entregar</div>
          <div className="stat-value">{formatInt(remaining.filter((s) => s.stop.kind === 'delivery').length)}</div>
          <div className="stat-note muted">{formatInt(done.length)} ya atendidas</div>
        </div>
        <div className="stat">
          <div className="stat-label">Carga a bordo</div>
          <div className="stat-value">{formatInt(route.load_kg)} kg</div>
          <div className="stat-note muted">de {formatInt(route.capacity_kg)} kg</div>
        </div>
        <div className="stat">
          <div className="stat-label">Regreso al CEDI</div>
          <div className="stat-value">{formatClock(route.return_min)}</div>
          <div className="stat-note muted">{route.delay_min > 0 ? `${formatMinutes(route.delay_min)} de retraso` : 'A tiempo'}</div>
        </div>
      </div>

      {next ? (
        <Card title="Siguiente parada" id="next">
          <p className="driver-next-title">{next.stop.label}</p>
          <p className="muted">{next.address}</p>
          <div className="driver-navs">
            {route.nav_links.map((link) => (
              <a
                key={link.url}
                className="btn btn-primary btn-big"
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {link.label}
              </a>
            ))}
          </div>
          <p className="muted small">
            Abre la aplicación de mapas de su teléfono con las paradas pendientes en este orden. Es solo
            un enlace de navegación.
          </p>
        </Card>
      ) : (
        <Card title="Ruta terminada" id="finished">
          <p>No tiene paradas pendientes. Regrese al CEDI y espere instrucciones.</p>
        </Card>
      )}

      <Card title={`Paradas pendientes (${remaining.length})`} id="pending-stops">
        {remaining.length === 0 ? (
          <p className="muted">No hay paradas pendientes.</p>
        ) : (
          <ol className="driver-stops">
            {remaining.map((item) => (
              <StopCard
                key={`${item.stop.key}-${item.stop.sequence}`}
                item={item}
                highlight={item.stop.key === next?.stop.key}
                busy={busy}
                onConfirm={setConfirming}
                onReport={(orderId) => setReporting({ orderId })}
              />
            ))}
          </ol>
        )}
        <button type="button" className="btn btn-big" onClick={() => setReporting({ orderId: null })}>
          Reportar una novedad general
        </button>
      </Card>

      {done.length > 0 ? (
        <details className="card">
          <summary>
            <strong>Paradas ya atendidas ({done.length})</strong>
          </summary>
          <ol className="driver-stops">
            {done.map((item) => (
              <StopCard
                key={`${item.stop.key}-${item.stop.sequence}`}
                item={item}
                highlight={false}
                busy={busy}
                onConfirm={setConfirming}
                onReport={(orderId) => setReporting({ orderId })}
              />
            ))}
          </ol>
        </details>
      ) : null}

      {route.reports.length > 0 ? (
        <Card title="Mis novedades" id="reports">
          <ul className="plain">
            {route.reports.map((r) => (
              <li key={r.id}>
                <strong>{formatClock(r.minute)}</strong> · {INCIDENT_LABELS[r.kind]}
                {r.order_id ? ` (${r.order_id})` : ''}: {r.detail}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {confirming ? (
        <ConfirmDialog
          title="Confirmar entrega"
          confirmLabel="Sí, entregué"
          tone="primary"
          busy={busy}
          onConfirm={() => void confirm()}
          onCancel={() => setConfirming(null)}
        >
          <p>
            ¿Confirma que entregó el pedido <strong>{confirming}</strong>? Queda registrado a su nombre y con la hora.
          </p>
        </ConfirmDialog>
      ) : null}

      {reporting ? (
        <div className="dialog-backdrop">
          <form
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-title"
            onSubmit={(e) => void sendReport(e)}
            noValidate
          >
            <h2 id="report-title">Reportar novedad</h2>
            {reporting.orderId ? <p className="muted">Pedido {reporting.orderId}</p> : null}
            {formError ? (
              <div className="alert alert-error" role="alert">
                {formError}
              </div>
            ) : null}
            <div className="field">
              <label htmlFor="report-kind">Tipo de novedad</label>
              <select id="report-kind" value={kind} onChange={(e) => setKind(e.target.value as IncidentKind)}>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {INCIDENT_LABELS[k]}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="report-detail">¿Qué ocurrió?</label>
              <textarea
                id="report-detail"
                rows={4}
                maxLength={300}
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
              />
              <span className="muted small">{detail.length}/300 · El despachador lo verá de inmediato.</span>
            </div>
            <div className="dialog-actions">
              <button type="button" className="btn" disabled={busy} onClick={() => setReporting(null)}>
                Cancelar
              </button>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? 'Enviando…' : 'Enviar novedad'}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  )
}
