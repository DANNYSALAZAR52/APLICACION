import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import type { ApiClient } from '../../api/client'
import { ApiError } from '../../api/errors'
import type { LoginRequest, UserInfo } from '../../api/types'

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthContextValue {
  status: Status
  user: UserInfo | null
  /** Mensaje cuando la sesión terminó sola (expiró/fue revocada). */
  notice: string | null
  login: (request: LoginRequest) => Promise<void>
  logout: () => Promise<void>
  client: ApiClient
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<UserInfo | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    client.onSessionEnded = () => {
      if (!active) return
      client.setAccessToken(null)
      setUser(null)
      setStatus('anonymous')
      setNotice('Su sesión terminó. Inicie sesión de nuevo para continuar.')
    }
    // Intenta restaurar la sesión con la cookie de refresh (HttpOnly). La deduplicación del
    // cliente evita rotar el token dos veces cuando React monta el efecto dos veces en desarrollo.
    client
      .refreshSession()
      .then((session) => {
        if (!active) return
        setUser(session.user)
        setStatus('authenticated')
      })
      .catch(() => {
        if (active) setStatus('anonymous')
      })
    return () => {
      active = false
      client.onSessionEnded = null
    }
  }, [client])

  const login = useCallback(
    async (request: LoginRequest) => {
      const session = await client.login(request)
      setNotice(null)
      setUser(session.user)
      setStatus('authenticated')
    },
    [client],
  )

  const logout = useCallback(async () => {
    try {
      await client.logout()
    } catch (error) {
      // Si el servidor ya no reconoce la sesión, igual se cierra localmente.
      if (!(error instanceof ApiError)) throw error
    } finally {
      client.setAccessToken(null)
      setUser(null)
      setStatus('anonymous')
      setNotice(null)
    }
  }, [client])

  const value = useMemo(
    () => ({ status, user, notice, login, logout, client }),
    [status, user, notice, login, logout, client],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth debe usarse dentro de AuthProvider')
  return context
}
