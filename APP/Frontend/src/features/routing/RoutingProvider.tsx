import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError } from '../../api/errors'
import type {
  DecisionOut,
  EventRequest,
  EventResultOut,
  RoutingSnapshot,
  SimulationAction,
} from '../../api/types'
import { useAuth } from '../auth/AuthProvider'

/** Cada cuánto se pide el seguimiento mientras el reloj simulado corre. */
export const POLL_MS = 2500

export interface RoutingFeed {
  snapshot: RoutingSnapshot | null
  error: unknown
  loading: boolean
  busy: boolean
  /** Último mensaje de una acción (por ejemplo, "Plan actualizado a la versión 3"). */
  notice: string | null
  actionError: string | null
  /** El estado llega por el flujo en tiempo real (si es falso, se consulta cada pocos segundos). */
  live: boolean
  refresh: () => void
  control: (action: SimulationAction, value?: number, target?: string) => Promise<void>
  resetDay: () => Promise<void>
  injectEvent: (body: EventRequest) => Promise<EventResultOut | null>
  decide: (id: string, decision: 'approve' | 'reject', comment: string) => Promise<DecisionOut | null>
  clearNotice: () => void
}

const RoutingContext = createContext<RoutingFeed | null>(null)

const messageOf = (error: unknown): string =>
  error instanceof ApiError ? error.message : 'No se pudo completar la acción. Intente de nuevo.'

/**
 * Mantiene UNA copia del estado del día para las pantallas de despacho y la refresca con el
 * seguimiento del backend mientras el reloj corre. La autorización la decide el backend en cada
 * llamada; aquí solo se evita pedir lo mismo desde tres pantallas.
 */
export function RoutingProvider({ children }: { children: ReactNode }) {
  const { client } = useAuth()
  const [snapshot, setSnapshot] = useState<RoutingSnapshot | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [live, setLive] = useState(false)
  const inFlight = useRef(false)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const load = useCallback(async () => {
    if (inFlight.current) return
    inFlight.current = true
    try {
      const next = await client.tower()
      if (!mounted.current) return
      setSnapshot(next)
      setError(null)
    } catch (e) {
      if (mounted.current) setError(e)
    } finally {
      inFlight.current = false
      if (mounted.current) setLoading(false)
    }
  }, [client])

  useEffect(() => {
    void load()
  }, [load])

  // Tiempo real: el servidor empuja el estado; si el flujo no está disponible se consulta.
  useEffect(() => {
    return client.watchTower(
      (next) => {
        if (!mounted.current) return
        setSnapshot(next)
        setError(null)
        setLoading(false)
        setLive(true)
      },
      () => {
        if (mounted.current) setLive(false)
      },
    )
  }, [client])

  const running = snapshot !== null && !snapshot.clock.paused
  useEffect(() => {
    if (!running || live) return
    const timer = window.setInterval(() => {
      if (inFlight.current || document.hidden) return
      inFlight.current = true
      client
        .track()
        .then((next) => {
          if (mounted.current) {
            setSnapshot(next)
            setError(null)
          }
        })
        .catch((e: unknown) => {
          if (mounted.current) setError(e)
        })
        .finally(() => {
          inFlight.current = false
        })
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [client, running, live])

  const guarded = useCallback(async <T,>(work: () => Promise<T>): Promise<T | null> => {
    setBusy(true)
    setActionError(null)
    try {
      return await work()
    } catch (e) {
      if (mounted.current) setActionError(messageOf(e))
      return null
    } finally {
      if (mounted.current) setBusy(false)
    }
  }, [])

  const feed = useMemo<RoutingFeed>(
    () => ({
      snapshot,
      error,
      loading,
      busy,
      notice,
      actionError,
      live,
      refresh: () => void load(),
      clearNotice: () => {
        setNotice(null)
        setActionError(null)
      },
      control: async (action, value, target) => {
        const next = await guarded(() => client.controlSimulation(action, value, target))
        if (next && mounted.current) setSnapshot(next)
      },
      resetDay: async () => {
        const next = await guarded(() => client.resetDay())
        if (next && mounted.current) {
          setSnapshot(next)
          setNotice('Día reiniciado: reloj a las 05:00 en pausa y plan de la mañana (versión 1).')
        }
      },
      injectEvent: async (body) => {
        const result = await guarded(() => client.injectEvent(body))
        if (result) {
          setNotice(`Evento registrado: ${result.event.summary}.`)
          await load()
        }
        return result
      },
      decide: async (id, decision, comment) => {
        const result = await guarded(() => client.decideProposal(id, decision, comment))
        if (result) {
          setNotice(result.message)
          await load()
        }
        return result
      },
    }),
    [snapshot, error, loading, busy, notice, actionError, live, client, guarded, load],
  )

  return <RoutingContext.Provider value={feed}>{children}</RoutingContext.Provider>
}

export function useRouting(): RoutingFeed {
  const value = useContext(RoutingContext)
  if (!value) throw new Error('useRouting debe usarse dentro de RoutingProvider')
  return value
}
