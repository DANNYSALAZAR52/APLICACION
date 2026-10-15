import { Badge } from '../../components/common'
import { SPEED_OPTIONS, formatClock } from '../../domain-ui/routing'
import { useRouting } from './RoutingProvider'

/** Reloj simulado (DEMO-ONLY): pausar, acelerar, adelantar y reiniciar el día. */
export function ClockControls() {
  const { snapshot, busy, control, resetDay } = useRouting()
  if (!snapshot) return null
  const { clock, provider_available: providerUp } = snapshot
  return (
    <section className="card clock-card" aria-labelledby="clock-title">
      <h2 id="clock-title">Reloj simulado</h2>
      <p className="clock-time" aria-live="polite">
        <span className="visually-hidden">Hora simulada: </span>
        {formatClock(clock.minute)}
      </p>
      <p className="muted small">
        {clock.paused ? (
          <Badge tone="warn">En pausa</Badge>
        ) : (
          <Badge tone="ok">Corriendo a {clock.speed}×</Badge>
        )}{' '}
        1 min real = {clock.speed} min simulados
      </p>
      <div className="actions">
        {clock.paused ? (
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void control('resume')}>
            Reanudar
          </button>
        ) : (
          <button type="button" className="btn" disabled={busy} onClick={() => void control('pause')}>
            Pausar
          </button>
        )}
        <button type="button" className="btn" disabled={busy} onClick={() => void control('advance', 15)}>
          +15 min
        </button>
        <button type="button" className="btn" disabled={busy} onClick={() => void control('advance', 60)}>
          +1 h
        </button>
      </div>
      <div className="field inline">
        <label htmlFor="sim-speed">Velocidad</label>
        <select
          id="sim-speed"
          value={clock.speed}
          disabled={busy}
          onChange={(e) => void control('speed', Number(e.target.value))}
        >
          {SPEED_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </div>
      <div className="actions">
        <button type="button" className="btn btn-small" disabled={busy} onClick={() => void resetDay()}>
          Reiniciar día
        </button>
        <button
          type="button"
          className="btn btn-small"
          disabled={busy}
          onClick={() => void control('provider', providerUp ? 0 : 1)}
        >
          {providerUp ? 'Simular falla del proveedor de tiempos' : 'Restablecer proveedor de tiempos'}
        </button>
      </div>
    </section>
  )
}
