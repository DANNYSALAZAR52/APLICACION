import { useState } from 'react'

import type { ProposalOut } from '../../api/types'
import { Badge, ConfirmDialog } from '../../components/common'
import { formatDateTime, formatInt } from '../../domain-ui/format'
import {
  EVENT_LABELS,
  PROPOSAL_LABELS,
  PROPOSAL_TONES,
  formatClock,
  formatMinutes,
} from '../../domain-ui/routing'
import { useRouting } from './RoutingProvider'

function Change({ before, after, unit = '' }: { before: number; after: number; unit?: string }) {
  const better = after < before
  const same = after === before
  return (
    <>
      {formatInt(before)}
      {unit} → <strong>{formatInt(after)}</strong>
      {unit}{' '}
      <span className={same ? 'muted' : better ? 'gap-surplus' : 'gap-deficit'}>
        {same ? '(sin cambio)' : better ? '(mejora)' : '(empeora)'}
      </span>
    </>
  )
}

export function ProposalCard({ proposal }: { proposal: ProposalOut }) {
  const { decide, busy } = useRouting()
  const [asking, setAsking] = useState<'approve' | 'reject' | null>(null)
  const [comment, setComment] = useState('')
  const impact = proposal.impact
  const isPending = proposal.status === 'pending'
  const titleId = `proposal-${proposal.id}`

  const confirm = async () => {
    if (!asking) return
    await decide(proposal.id, asking, comment)
    setAsking(null)
    setComment('')
  }

  return (
    <article className={`proposal proposal-${proposal.status}`} aria-labelledby={titleId}>
      <header>
        <h3 id={titleId}>{proposal.reason}</h3>
        <div className="proposal-badges">
          <Badge tone={PROPOSAL_TONES[proposal.status]}>{PROPOSAL_LABELS[proposal.status]}</Badge>
          <Badge tone="neutral">{EVENT_LABELS[proposal.event_type]}</Badge>
          {isPending && proposal.requires_confirmation ? (
            <Badge tone="warn">Su confirmación es obligatoria</Badge>
          ) : null}
        </div>
      </header>
      <p>{proposal.summary}</p>
      <p className="muted small">
        Calculada sobre el plan versión {proposal.base_version}
        {proposal.proposed_version ? ` · generaría la versión ${proposal.proposed_version}` : ''} ·{' '}
        {formatDateTime(proposal.created_at)}
      </p>

      <dl className="impact">
        <div>
          <dt>Entregas tarde</dt>
          <dd>
            <Change before={impact.late_stops_before} after={impact.late_stops_after} />
          </dd>
        </div>
        <div>
          <dt>Retraso total</dt>
          <dd>
            <Change before={Math.round(impact.delay_min_before)} after={Math.round(impact.delay_min_after)} unit=" min" />
          </dd>
        </div>
        <div>
          <dt>Puntaje del plan (menor es mejor)</dt>
          <dd>
            <Change before={Math.round(impact.score_before)} after={Math.round(impact.score_after)} />
          </dd>
        </div>
        {impact.unattended_before > 0 ? (
          <div>
            <dt>Entregas sin vehículo si no se actúa</dt>
            <dd>{formatInt(impact.unattended_before)}</dd>
          </div>
        ) : null}
        <div>
          <dt>Vehículos afectados</dt>
          <dd>{impact.affected_vehicles.length > 0 ? impact.affected_vehicles.join(', ') : 'Ninguno'}</dd>
        </div>
        {impact.activates_reserve ? (
          <div>
            <dt>Activa reserva o tercero</dt>
            <dd>Sí{impact.reserve_vehicle ? ` (${impact.reserve_vehicle})` : ''}</dd>
          </div>
        ) : null}
      </dl>

      {impact.unattended_orders.length > 0 ? (
        <div className="alert alert-error" role="alert">
          <strong>Pedidos que quedan sin atender hoy:</strong> {impact.unattended_orders.join(', ')}
        </div>
      ) : null}
      {impact.notes.length > 0 ? (
        <ul className="plain small">
          {impact.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}

      {proposal.routes.length > 0 ? (
        <details>
          <summary>Rutas propuestas ({proposal.routes.length})</summary>
          {proposal.routes.map((r) => (
            <div key={r.vehicle_id} className="proposal-route">
              <strong>{r.plate}</strong>
              {r.status === 'broken' ? ' · averiado, queda detenido' : ` · regreso ${formatClock(r.return_min)}`}
              <ol>
                {r.stops.map((s, i) => (
                  <li key={`${s.label}-${i}`}>
                    {s.label} — {formatClock(s.arrival_min)}
                    {s.delay_min > 0 ? ` (tarde ${formatMinutes(s.delay_min)})` : ''}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </details>
      ) : null}

      {proposal.decided_by ? (
        <p className="muted small">
          Decisión de {proposal.decided_by} · {formatDateTime(proposal.decided_at)}
          {proposal.decision_comment ? ` · «${proposal.decision_comment}»` : ''}
          {proposal.applied_version ? ` · plan versión ${proposal.applied_version}` : ''}
        </p>
      ) : null}

      {isPending ? (
        <div className="actions">
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => setAsking('approve')}>
            Aprobar
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => setAsking('reject')}>
            Rechazar
          </button>
        </div>
      ) : null}

      {asking ? (
        <ConfirmDialog
          title={asking === 'approve' ? 'Aprobar propuesta' : 'Rechazar propuesta'}
          confirmLabel={asking === 'approve' ? 'Aprobar y crear nueva versión' : 'Rechazar'}
          tone={asking === 'approve' ? 'primary' : 'danger'}
          busy={busy}
          onConfirm={() => void confirm()}
          onCancel={() => setAsking(null)}
        >
          <p>
            {asking === 'approve'
              ? `Se creará una versión nueva del plan (la versión ${proposal.base_version} se conserva intacta).`
              : 'El plan vigente no cambia. La decisión queda registrada.'}
          </p>
          <div className="field">
            <label htmlFor={`${titleId}-comment`}>Comentario (opcional)</label>
            <input
              id={`${titleId}-comment`}
              value={comment}
              maxLength={500}
              onChange={(e) => setComment(e.target.value)}
            />
          </div>
        </ConfirmDialog>
      ) : null}
    </article>
  )
}
