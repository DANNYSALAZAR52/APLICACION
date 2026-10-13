import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

import { ApiError } from '../api/errors'

export const DEMO_LABEL = 'DATOS DE DEMOSTRACIÓN'

/** Etiqueta persistente: nunca se presentan datos sintéticos como reales. */
export function DemoBanner() {
  return (
    <div className="demo-banner" role="note" aria-label="Aviso de datos de demostración">
      <span aria-hidden="true">⚠</span> {DEMO_LABEL} · Información sintética, no corresponde a
      ninguna operación real
    </div>
  )
}

export function LoadingState({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state-empty">
      <strong>{title}</strong>
      {children ? <p>{children}</p> : null}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const api = error instanceof ApiError ? error : null
  const denied = api?.status === 403
  return (
    <div className="alert alert-error" role="alert">
      <strong>{denied ? 'Acceso restringido' : 'No se pudo cargar la información'}</strong>
      <p>{api ? api.message : 'Ocurrió un error inesperado. Intente de nuevo.'}</p>
      {api?.requestId ? <p className="muted">Código de seguimiento: {api.requestId}</p> : null}
      {onRetry && !denied ? (
        <button type="button" className="btn" onClick={onRetry}>
          Reintentar
        </button>
      ) : null}
    </div>
  )
}

type Tone = 'ok' | 'warn' | 'bad' | 'neutral'
const ICONS: Record<Tone, string> = { ok: '✔', warn: '⚠', bad: '✖', neutral: '•' }

/** El estado se comunica con icono y texto, no solo con color. */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`badge badge-${tone}`}>
      <span aria-hidden="true">{ICONS[tone]}</span> {children}
    </span>
  )
}

interface ConfirmDialogProps {
  title: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
  busy?: boolean
  children: ReactNode
}

export function ConfirmDialog({
  title,
  confirmLabel,
  onConfirm,
  onCancel,
  busy = false,
  children,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    cancelRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <div className="dialog-backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <h2 id="dialog-title">{title}</h2>
        <div>{children}</div>
        <div className="dialog-actions">
          <button type="button" className="btn" ref={cancelRef} onClick={onCancel} disabled={busy}>
            Cancelar
          </button>
          <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? 'Procesando…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function Card({
  title,
  children,
  id,
}: {
  title?: string
  children: ReactNode
  id?: string
}) {
  const headingId = id ? `${id}-title` : undefined
  return (
    <section className="card" aria-labelledby={headingId}>
      {title ? <h2 id={headingId}>{title}</h2> : null}
      {children}
    </section>
  )
}
