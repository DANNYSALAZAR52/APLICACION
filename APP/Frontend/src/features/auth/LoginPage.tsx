import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { DemoBanner, LoadingState } from '../../components/common'
import { useAuth } from './AuthProvider'

const SUPER_ADMIN = '__none__'
const OTHER = '__other__'

const COMPANY_OPTIONS = [
  { value: 'empresa-demo-a', label: 'Empresa Demo A' },
  { value: 'empresa-demo-b', label: 'Empresa Demo B' },
  { value: SUPER_ADMIN, label: 'Superadministrador (sin empresa)' },
  { value: OTHER, label: 'Otra empresa (escribir identificador)' },
]

interface FieldErrors {
  company?: string
  username?: string
  password?: string
}

export function LoginPage() {
  const { status, login, notice } = useAuth()
  const [company, setCompany] = useState(COMPANY_OPTIONS[0]?.value ?? '')
  const [customSlug, setCustomSlug] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'loading') return <LoadingState label="Verificando sesión…" />
  if (status === 'authenticated') return <Navigate to="/" replace />

  const validate = (): FieldErrors => {
    const found: FieldErrors = {}
    if (company === OTHER && !customSlug.trim()) {
      found.company = 'Escriba el identificador de la empresa.'
    }
    if (!username.trim()) found.username = 'Escriba su usuario.'
    if (!password) found.password = 'Escriba su contraseña.'
    return found
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    const found = validate()
    setErrors(found)
    if (Object.keys(found).length > 0) return
    setSubmitting(true)
    try {
      const slug = company === SUPER_ADMIN ? null : company === OTHER ? customSlug.trim() : company
      await login({ tenant_slug: slug, username: username.trim(), password })
    } catch (error) {
      setPassword('')
      setFormError(
        error instanceof ApiError ? error.message : 'No se pudo iniciar sesión. Intente de nuevo.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <DemoBanner />
      <form className="card login-card" onSubmit={onSubmit} noValidate aria-labelledby="login-title">
        <h1 id="login-title">Planeación de flota</h1>
        <p className="muted">Inicie sesión para ver el demo.</p>

        {notice ? (
          <div className="alert alert-warn" role="status">
            {notice}
          </div>
        ) : null}
        {formError ? (
          <div className="alert alert-error" role="alert">
            {formError}
          </div>
        ) : null}

        <div className="field">
          <label htmlFor="company">Empresa</label>
          <select id="company" value={company} onChange={(e) => setCompany(e.target.value)}>
            {COMPANY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {company === OTHER ? (
          <div className="field">
            <label htmlFor="custom-slug">Identificador de la empresa</label>
            <input
              id="custom-slug"
              value={customSlug}
              onChange={(e) => setCustomSlug(e.target.value)}
              aria-invalid={errors.company ? 'true' : undefined}
              aria-describedby={errors.company ? 'company-error' : undefined}
              autoComplete="off"
            />
            {errors.company ? (
              <p id="company-error" className="field-error">
                {errors.company}
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="field">
          <label htmlFor="username">Usuario</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            aria-invalid={errors.username ? 'true' : undefined}
            aria-describedby={errors.username ? 'username-error' : undefined}
          />
          {errors.username ? (
            <p id="username-error" className="field-error">
              {errors.username}
            </p>
          ) : null}
        </div>

        <div className="field">
          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            aria-invalid={errors.password ? 'true' : undefined}
            aria-describedby={errors.password ? 'password-error' : 'password-help'}
          />
          {errors.password ? (
            <p id="password-error" className="field-error">
              {errors.password}
            </p>
          ) : (
            <p id="password-help" className="muted small">
              Las contraseñas del demo son aleatorias y se muestran una sola vez en la consola donde
              se inició el servidor.
            </p>
          )}
        </div>

        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? 'Ingresando…' : 'Ingresar'}
        </button>
      </form>
    </main>
  )
}
