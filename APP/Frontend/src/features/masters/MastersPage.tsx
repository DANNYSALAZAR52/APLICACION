import { useState } from 'react'

import { ErrorState, LoadingState } from '../../components/common'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'
import { EntityPanel } from './EntityPanel'
import { HistoryPanel } from './HistoryPanel'
import { ParametersPanel } from './ParametersPanel'

const GROUPS: { title: string; entities: string[] }[] = [
  { title: 'Capacidad de flota', entities: ['vehicle_type', 'corridor', 'compatibility', 'fleet', 'daily_demand'] },
  { title: 'Ruteo diario', entities: ['customer', 'vehicle', 'order'] },
]

/** Maestros y parámetros de la empresa (pantalla 6): CRUD, carga CSV e historial. */
export function MastersPage() {
  const { client } = useAuth()
  const [tab, setTab] = useState('vehicle_type')
  const [version, setVersion] = useState(0)
  const { state, reload } = useApiResource((signal) => client.masterSchema(signal))

  if (state.status === 'loading') return <LoadingState label="Cargando maestros…" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={reload} />
  const schema = state.data
  const changed = () => {
    setVersion((v) => v + 1)
    reload() // refresca las listas de selección (tipos, rutas, clientes)
  }
  const entity = schema.entities.find((e) => e.name === tab)

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Maestros y parámetros</h1>
          <p className="muted">
            Solo el administrador de la empresa ve esta pantalla. Todo cambio se valida, queda en el
            historial con su valor anterior y se audita. Los datos son de demostración.
          </p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Maestros">
        {GROUPS.map((g) => (
          <div key={g.title} className="tab-group">
            <span className="tab-group-title">{g.title}</span>
            {g.entities.map((name) => {
              const e = schema.entities.find((x) => x.name === name)
              return e ? (
                <button
                  key={name}
                  type="button"
                  role="tab"
                  aria-selected={tab === name}
                  className={`tab${tab === name ? ' tab-active' : ''}`}
                  onClick={() => setTab(name)}
                >
                  {e.plural}
                </button>
              ) : null
            })}
          </div>
        ))}
        <div className="tab-group">
          <span className="tab-group-title">Control</span>
          {(
            [
              ['parameters', 'Parámetros'],
              ['history', 'Historial'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              className={`tab${tab === key ? ' tab-active' : ''}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div role="tabpanel">
        {entity ? <EntityPanel key={entity.name} entity={entity} schema={schema} onChanged={changed} /> : null}
        {tab === 'parameters' ? <ParametersPanel onChanged={changed} /> : null}
        {tab === 'history' ? <HistoryPanel schema={schema} refreshKey={version} /> : null}
      </div>
    </div>
  )
}
