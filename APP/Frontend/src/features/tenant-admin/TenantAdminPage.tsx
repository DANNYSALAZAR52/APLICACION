import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError } from '../../api/errors'
import type { ProvisionResponse, TenantOut } from '../../api/types'
import { Badge, Card, ConfirmDialog, EmptyState, ErrorState, LoadingState } from '../../components/common'
import { formatDateTime, formatInt } from '../../domain-ui/format'
import { useApiResource } from '../../hooks/useApiResource'
import { useAuth } from '../auth/AuthProvider'

const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/

interface PendingAction {
  tenant: TenantOut
  kind: 'suspend' | 'reactivate'
}

export function TenantAdminPage() {
  const { client } = useAuth()
  const { state, reload } = useApiResource((signal) => client.tenants(signal))
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [created, setCreated] = useState<ProvisionResponse | null>(null)

  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [errors, setErrors] = useState<{ slug?: string; name?: string }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    setActionError(null)
    try {
      if (pending.kind === 'suspend') await client.suspendTenant(pending.tenant.slug)
      else await client.reactivateTenant(pending.tenant.slug)
      setPending(null)
      reload()
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : 'No se pudo completar la acción.')
      setPending(null)
    } finally {
      setBusy(false)
    }
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const found: { slug?: string; name?: string } = {}
    const cleanSlug = slug.trim().toLowerCase()
    if (!SLUG_PATTERN.test(cleanSlug) || cleanSlug.length < 2 || cleanSlug.length > 40) {
      found.slug = 'Use 2–40 caracteres: minúsculas, números y guiones (por ejemplo, empresa-c).'
    }
    if (name.trim().length < 2 || name.trim().length > 120) {
      found.name = 'El nombre debe tener entre 2 y 120 caracteres.'
    }
    setErrors(found)
    setFormError(null)
    if (Object.keys(found).length > 0) return
    setSubmitting(true)
    try {
      const result = await client.provisionTenant(cleanSlug, name.trim())
      setCreated(result)
      setSlug('')
      setName('')
      reload()
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'No se pudo crear la empresa.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page">
      <h1>Administración de empresas</h1>
      <p className="muted">
        Solo el superadministrador ve esta pantalla. No se muestran cadenas de conexión ni secretos.
      </p>

      {actionError ? (
        <div className="alert alert-error" role="alert">
          {actionError}
        </div>
      ) : null}

      <Card title="Empresas" id="tenants">
        {state.status === 'loading' ? <LoadingState label="Cargando empresas…" /> : null}
        {state.status === 'error' ? <ErrorState error={state.error} onRetry={reload} /> : null}
        {state.status === 'success' && state.data.length === 0 ? (
          <EmptyState title="Aún no hay empresas">Cree la primera con el formulario inferior.</EmptyState>
        ) : null}
        {state.status === 'success' && state.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Empresas registradas</caption>
              <thead>
                <tr>
                  <th scope="col">Identificador</th>
                  <th scope="col">Nombre</th>
                  <th scope="col">Estado</th>
                  <th scope="col" className="num">
                    Usuarios
                  </th>
                  <th scope="col">Creada</th>
                  <th scope="col">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {state.data.map((tenant) => (
                  <tr key={tenant.slug}>
                    <th scope="row">{tenant.slug}</th>
                    <td>{tenant.name}</td>
                    <td>
                      {tenant.status === 'active' ? (
                        <Badge tone="ok">Activa</Badge>
                      ) : (
                        <Badge tone="bad">Suspendida</Badge>
                      )}
                    </td>
                    <td className="num">{formatInt(tenant.user_count)}</td>
                    <td>{formatDateTime(tenant.created_at)}</td>
                    <td>
                      {tenant.status === 'active' ? (
                        <button
                          type="button"
                          className="btn btn-small"
                          aria-label={`Suspender ${tenant.name}`}
                          onClick={() => setPending({ tenant, kind: 'suspend' })}
                        >
                          Suspender
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-small"
                          aria-label={`Reactivar ${tenant.name}`}
                          onClick={() => setPending({ tenant, kind: 'reactivate' })}
                        >
                          Reactivar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      <Card title="Nueva empresa" id="new-tenant">
        {created ? (
          <div className="alert alert-ok" role="status">
            <strong>
              {created.created
                ? `Empresa «${created.tenant.name}» creada.`
                : `La empresa «${created.tenant.name}» ya existía; no se creó nada nuevo.`}
            </strong>
            {created.initial_admin_password ? (
              <>
                <p>
                  Administrador: <code>{created.admin_username}</code> · Contraseña inicial:{' '}
                  <code>{created.initial_admin_password}</code>
                </p>
                <p className="muted">
                  Esta contraseña se muestra una sola vez. Cópiela ahora: no se puede volver a ver.
                </p>
              </>
            ) : null}
            <button type="button" className="btn btn-small" onClick={() => setCreated(null)}>
              Entendido, ocultar
            </button>
          </div>
        ) : null}
        <form onSubmit={submit} noValidate aria-label="Alta de empresa" className="form-grid">
          {formError ? (
            <div className="alert alert-error" role="alert">
              {formError}
            </div>
          ) : null}
          <div className="field">
            <label htmlFor="tenant-slug">Identificador corto</label>
            <input
              id="tenant-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              aria-invalid={errors.slug ? 'true' : undefined}
              aria-describedby={errors.slug ? 'slug-error' : undefined}
              autoComplete="off"
            />
            {errors.slug ? (
              <p id="slug-error" className="field-error">
                {errors.slug}
              </p>
            ) : null}
          </div>
          <div className="field">
            <label htmlFor="tenant-name">Nombre de la empresa</label>
            <input
              id="tenant-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={errors.name ? 'true' : undefined}
              aria-describedby={errors.name ? 'name-error' : undefined}
              autoComplete="off"
            />
            {errors.name ? (
              <p id="name-error" className="field-error">
                {errors.name}
              </p>
            ) : null}
          </div>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Creando…' : 'Crear empresa'}
          </button>
        </form>
      </Card>

      {pending ? (
        <ConfirmDialog
          title={pending.kind === 'suspend' ? 'Suspender empresa' : 'Reactivar empresa'}
          confirmLabel={pending.kind === 'suspend' ? 'Suspender' : 'Reactivar'}
          busy={busy}
          onConfirm={() => void confirm()}
          onCancel={() => setPending(null)}
        >
          {pending.kind === 'suspend' ? (
            <p>
              ¿Suspender <strong>{pending.tenant.name}</strong>? Se bloquearán sus accesos nuevos y se
              cerrarán las sesiones activas de todos sus usuarios.
            </p>
          ) : (
            <p>
              ¿Reactivar <strong>{pending.tenant.name}</strong>? Sus usuarios podrán iniciar sesión
              de nuevo.
            </p>
          )}
        </ConfirmDialog>
      ) : null}
    </div>
  )
}
