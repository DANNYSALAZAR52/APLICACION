import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/errors'
import type { Role } from '../api/types'
import { AUDIT, makeDashboard, makeFakeClient, makeSession, makeUser } from '../test/fixtures'
import { App } from './App'

type Client = ReturnType<typeof makeFakeClient>

function renderApp(client: Client, route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App client={client} />
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('sesión y navegación', () => {
  it('sin sesión lleva al inicio de sesión y muestra la etiqueta de demostración', async () => {
    renderApp(makeFakeClient(null))
    expect(await screen.findByRole('heading', { name: 'Planeación de flota' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ingresar' })).toBeInTheDocument()
    expect(screen.getByRole('note', { name: /datos de demostración/i })).toHaveTextContent(
      'DATOS DE DEMOSTRACIÓN',
    )
  })

  it('gerencia aterriza en capacidad y ve solo sus opciones', async () => {
    renderApp(makeFakeClient('management'))
    expect(await screen.findByRole('heading', { name: 'Capacidad de flota' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Navegación principal' })
    expect(within(nav).getByRole('link', { name: 'Capacidad de flota' })).toBeInTheDocument()
    expect(within(nav).queryByRole('link', { name: /Administración de empresas/ })).toBeNull()
    expect(within(nav).queryByRole('link', { name: 'Auditoría' })).toBeNull()
    expect(screen.getByRole('note', { name: /datos de demostración/i })).toBeInTheDocument()
  })

  it('las pantallas futuras aparecen deshabilitadas y explicadas, no como enlaces vacíos', async () => {
    renderApp(makeFakeClient('management'))
    await screen.findByRole('heading', { name: 'Capacidad de flota' })
    const nav = screen.getByRole('navigation', { name: 'Navegación principal' })
    const pending = within(nav).getByText(/Patrones de ML/)
    expect(pending.closest('[aria-disabled="true"]')).not.toBeNull()
    expect(within(nav).queryByRole('link', { name: /Patrones de ML/ })).toBeNull()
    expect(nav).toHaveTextContent('no disponible: se construye en una fase posterior')
  })

  it('el superadministrador aterriza en empresas', async () => {
    renderApp(makeFakeClient('super_admin'))
    expect(await screen.findByRole('heading', { name: 'Administración de empresas' })).toBeInTheDocument()
  })

  it.each<Role>(['dispatcher', 'driver'])('%s no tiene pantallas aún: ve "Pantallas en construcción"', async (role) => {
    renderApp(makeFakeClient(role))
    expect(await screen.findByRole('heading', { name: 'Pantallas en construcción' })).toBeInTheDocument()
  })

  it.each<[Role, string]>([
    ['dispatcher', '/capacidad'],
    ['driver', '/capacidad'],
    ['management', '/empresas'],
    ['tenant_admin', '/empresas'],
    ['management', '/auditoria'],
  ])('%s abriendo %s ve "Permisos insuficientes" sin llamar a la API', async (role, route) => {
    const client = makeFakeClient(role)
    renderApp(client, route)
    expect(await screen.findByText('Permisos insuficientes')).toBeInTheDocument()
    expect(client.dashboard).not.toHaveBeenCalled()
    expect(client.tenants).not.toHaveBeenCalled()
    expect(client.audit).not.toHaveBeenCalled()
  })

  it('cerrar sesión llama al servidor y vuelve al login', async () => {
    const client = makeFakeClient('management')
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    expect(client.logout).toHaveBeenCalledTimes(1)
    expect(await screen.findByRole('button', { name: 'Ingresar' })).toBeInTheDocument()
  })

  it('si la sesión termina sola se informa en la pantalla de login', async () => {
    const client = makeFakeClient('management')
    renderApp(client)
    await screen.findByRole('heading', { name: 'Capacidad de flota' })
    client.onSessionEnded?.()
    expect(await screen.findByText(/Su sesión terminó/)).toBeInTheDocument()
    expect(client.setAccessToken).toHaveBeenCalledWith(null)
  })

  it('una ruta inexistente muestra un aviso con salida', async () => {
    renderApp(makeFakeClient('management'), '/no-existe')
    expect(await screen.findByText('Página no encontrada')).toBeInTheDocument()
  })
})

describe('inicio de sesión', () => {
  it('valida campos vacíos sin llamar a la API', async () => {
    const client = makeFakeClient(null)
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Ingresar' }))
    expect(await screen.findByText('Escriba su usuario.')).toBeInTheDocument()
    expect(screen.getByText('Escriba su contraseña.')).toBeInTheDocument()
    expect(screen.getByLabelText('Usuario')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Usuario')).toHaveAccessibleDescription('Escriba su usuario.')
    expect(client.login).not.toHaveBeenCalled()
  })

  it('envía la empresa elegida y entra', async () => {
    const client = makeFakeClient(null, {
      login: vi.fn(() => Promise.resolve(makeSession(makeUser('management')))),
    })
    renderApp(client)
    await userEvent.selectOptions(await screen.findByLabelText('Empresa'), 'Empresa Demo B')
    await userEvent.type(screen.getByLabelText('Usuario'), ' gerencia ')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'ClaveSegura2026')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(client.login).toHaveBeenCalledWith({
      tenant_slug: 'empresa-demo-b',
      username: 'gerencia',
      password: 'ClaveSegura2026',
    })
    expect(await screen.findByRole('heading', { name: 'Capacidad de flota' })).toBeInTheDocument()
  })

  it('el superadministrador entra sin empresa (tenant_slug nulo)', async () => {
    const client = makeFakeClient(null, {
      login: vi.fn(() => Promise.resolve(makeSession(makeUser('super_admin')))),
    })
    renderApp(client)
    await userEvent.selectOptions(await screen.findByLabelText('Empresa'), 'Superadministrador (sin empresa)')
    await userEvent.type(screen.getByLabelText('Usuario'), 'superadmin')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'ClaveSegura2026')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(client.login).toHaveBeenCalledWith(expect.objectContaining({ tenant_slug: null }))
  })

  it('"otra empresa" exige escribir el identificador', async () => {
    const client = makeFakeClient(null)
    renderApp(client)
    await userEvent.selectOptions(await screen.findByLabelText('Empresa'), 'Otra empresa (escribir identificador)')
    await userEvent.type(screen.getByLabelText('Usuario'), 'a')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'b')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(await screen.findByText('Escriba el identificador de la empresa.')).toBeInTheDocument()
    expect(client.login).not.toHaveBeenCalled()
  })

  it('muestra el error del servidor y vacía la contraseña', async () => {
    const client = makeFakeClient(null, {
      login: vi.fn(() =>
        Promise.reject(new ApiError(401, 'AUTENTICACION_INVALIDA', 'Credenciales inválidas o cuenta bloqueada temporalmente.')),
      ),
    })
    renderApp(client)
    await userEvent.type(await screen.findByLabelText('Usuario'), 'gerencia')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'mala-clave')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Credenciales inválidas')
    expect(screen.getByLabelText('Contraseña')).toHaveValue('')
  })

  it('un fallo de red también se explica', async () => {
    const client = makeFakeClient(null, {
      login: vi.fn(() => Promise.reject(new Error('boom'))),
    })
    renderApp(client)
    await userEvent.type(await screen.findByLabelText('Usuario'), 'g')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'p')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo iniciar sesión')
  })
})

describe('tablero de capacidad', () => {
  it('muestra los resultados con unidades, brecha en texto y OTIF no disponible', async () => {
    renderApp(makeFakeClient('management'))
    await screen.findByRole('heading', { name: 'Capacidad de flota' })
    // aparece en la tarjeta principal y en la fila de totales de la tabla
    expect(screen.getAllByText('Déficit de 1')).toHaveLength(2)
    expect(screen.getByText(/Calculado:.*hora de Bogotá/)).toBeInTheDocument()
    expect(screen.getByText(/OTIF/).closest('div')).toHaveTextContent('No disponible (requiere ruteo)')
    expect(screen.getByText(/Pronóstico de demanda con ML:/).closest('p')).toHaveTextContent('No disponible en esta fase')
    const fleet = screen.getByRole('table', { name: /Flota requerida por método/ })
    expect(within(fleet).getByRole('row', { name: /Total/ })).toBeInTheDocument()
    expect(screen.getByText('La flota actual deja de alcanzar en 2027')).toBeInTheDocument()
    expect(screen.getByText('La flota actual alcanza en todo el horizonte')).toBeInTheDocument()
  })

  it('un mix que no es óptimo se rotula como tal y nunca como óptimo', async () => {
    const dashboard = makeDashboard({
      mix: {
        status: 'feasible',
        optimal: false,
        total_vehicles: 21,
        total_cost_per_day: 1,
        message: 'Solución factible sin prueba de optimalidad.',
        assignments: [{ corridor: 'URB-N', vehicle_type: 'turbo', count: 3 }],
      },
    })
    renderApp(makeFakeClient('management', { dashboard: vi.fn(() => Promise.resolve(dashboard)) }))
    await screen.findByRole('heading', { name: 'Capacidad de flota' })
    expect(screen.getAllByText('Factible (sin prueba de optimalidad)').length).toBeGreaterThan(0)
    expect(screen.queryByText('Óptima')).toBeNull()
  })

  it('sin solución del optimizador muestra su estado real en vez de un resultado vacío', async () => {
    const dashboard = makeDashboard({
      mix: { status: 'infeasible', optimal: false, total_vehicles: 0, total_cost_per_day: null, message: 'Sin tipo compatible.', assignments: [] },
      totals: { ...makeDashboard().totals, mix: null },
    })
    renderApp(makeFakeClient('management', { dashboard: vi.fn(() => Promise.resolve(dashboard)) }))
    expect(await screen.findByText('Sin solución utilizable')).toBeInTheDocument()
    expect(screen.getAllByText('Inviable').length).toBeGreaterThan(0)
  })

  it('sin historial completo no inventa la comparación propio vs. tercero', async () => {
    const dashboard = makeDashboard({ own_vs_third: [] })
    renderApp(makeFakeClient('management', { dashboard: vi.fn(() => Promise.resolve(dashboard)) }))
    expect(await screen.findByText('Sin datos suficientes')).toBeInTheDocument()
  })

  it('mientras carga muestra un estado de carga accesible', async () => {
    const pending = new Promise<never>(() => undefined)
    renderApp(makeFakeClient('management', { dashboard: vi.fn(() => pending) }))
    expect(await screen.findByText('Calculando la capacidad de flota…')).toBeInTheDocument()
    expect(screen.getByText('Calculando la capacidad de flota…').closest('[role="status"]')).not.toBeNull()
  })

  it('ante un error ofrece reintentar y se recupera', async () => {
    const dashboard = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(500, 'ERROR_INTERNO', 'Ocurrió un error interno.', 'req-9'))
      .mockResolvedValue(makeDashboard())
    renderApp(makeFakeClient('management', { dashboard }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Ocurrió un error interno.')
    expect(alert).toHaveTextContent('req-9')
    await userEvent.click(within(alert).getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { name: 'Capacidad de flota' })).toBeInTheDocument()
    expect(dashboard).toHaveBeenCalledTimes(2)
  })

  it('un 403 se presenta como acceso restringido y no ofrece reintentar', async () => {
    const dashboard = vi.fn(() =>
      Promise.reject(new ApiError(403, 'EMPRESA_SUSPENDIDA', 'La empresa está suspendida.')),
    )
    renderApp(makeFakeClient('management', { dashboard }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Acceso restringido')
    expect(within(alert).queryByRole('button', { name: 'Reintentar' })).toBeNull()
  })

  it('"Recalcular" solo aparece con permiso y vuelve a pedir los datos', async () => {
    const client = makeFakeClient('management')
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Recalcular' }))
    await waitFor(() => expect(client.dashboard).toHaveBeenCalledTimes(2))
  })

  it('el administrador de empresa ve el tablero pero no puede recalcular', async () => {
    renderApp(makeFakeClient('tenant_admin'))
    await screen.findByRole('heading', { name: 'Capacidad de flota' })
    expect(screen.queryByRole('button', { name: 'Recalcular' })).toBeNull()
  })

  it('exporta el CSV con la etiqueta de demostración', async () => {
    const createObjectURL = vi.fn(() => 'blob:prueba')
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    renderApp(makeFakeClient('management'))
    await userEvent.click(await screen.findByRole('button', { name: 'Exportar CSV' }))
    expect(click).toHaveBeenCalled()
    const blob = (createObjectURL.mock.calls[0] as unknown as [Blob])[0]
    expect(await blob.text()).toContain('DATOS DE DEMOSTRACIÓN')
  })

  it('cambiar el escenario cambia la tabla de detalle', async () => {
    renderApp(makeFakeClient('management'))
    await screen.findByRole('heading', { name: 'Capacidad de flota' })
    expect(screen.getByRole('table', { name: /escenario Base/ })).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Escenario del detalle'), 'Pesimista')
    expect(screen.getByRole('table', { name: /escenario Pesimista/ })).toBeInTheDocument()
  })
})

describe('administración de empresas', () => {
  it('lista empresas con estado en texto y sin secretos', async () => {
    renderApp(makeFakeClient('super_admin'))
    const table = await screen.findByRole('table', { name: 'Empresas registradas' })
    expect(within(table).getByText('Activa')).toBeInTheDocument()
    expect(within(table).getByText('Suspendida')).toBeInTheDocument()
    expect(table).not.toHaveTextContent(/contraseña|conexión|password/i)
  })

  it('suspender pide confirmación y cancelar no llama a la API', async () => {
    const client = makeFakeClient('super_admin')
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: /Suspender Empresa Demo A/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Suspender empresa' })
    expect(dialog).toHaveTextContent('cerrarán las sesiones activas')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(client.suspendTenant).not.toHaveBeenCalled()
  })

  it('confirmar suspende la empresa y recarga la lista', async () => {
    const client = makeFakeClient('super_admin')
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: /Suspender Empresa Demo A/ }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Suspender' }))
    await waitFor(() => expect(client.suspendTenant).toHaveBeenCalledWith('empresa-demo-a'))
    await waitFor(() => expect(client.tenants).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('reactivar también pide confirmación', async () => {
    const client = makeFakeClient('super_admin')
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: /Reactivar Empresa Demo B/ }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Reactivar' }))
    await waitFor(() => expect(client.reactivateTenant).toHaveBeenCalledWith('empresa-demo-b'))
  })

  it('Escape cierra el diálogo', async () => {
    renderApp(makeFakeClient('super_admin'))
    await userEvent.click(await screen.findByRole('button', { name: /Suspender Empresa Demo A/ }))
    await screen.findByRole('dialog')
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('si la acción falla se muestra el mensaje del servidor', async () => {
    const client = makeFakeClient('super_admin', {
      suspendTenant: vi.fn(() => Promise.reject(new ApiError(404, 'NO_ENCONTRADO', 'La empresa indicada no existe.'))),
    })
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: /Suspender Empresa Demo A/ }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Suspender' }))
    expect(await screen.findByText('La empresa indicada no existe.')).toBeInTheDocument()
  })

  it('valida el alta en el navegador (el backend vuelve a validar)', async () => {
    const client = makeFakeClient('super_admin')
    renderApp(client)
    await userEvent.type(await screen.findByLabelText('Identificador corto'), 'Mala Empresa!')
    await userEvent.type(screen.getByLabelText('Nombre de la empresa'), 'X')
    await userEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText(/Use 2–40 caracteres/)).toBeInTheDocument()
    expect(screen.getByText(/entre 2 y 120/)).toBeInTheDocument()
    expect(client.provisionTenant).not.toHaveBeenCalled()
  })

  it('al crear muestra la contraseña inicial una sola vez', async () => {
    const provisionTenant = vi.fn(() =>
      Promise.resolve({
        tenant: { slug: 'empresa-c', name: 'Empresa C', status: 'active' as const, created_at: '2026-10-13T13:00:00Z', user_count: 1 },
        created: true,
        admin_username: 'admin',
        initial_admin_password: 'Clave-Inicial-9x',
      }),
    )
    renderApp(makeFakeClient('super_admin', { provisionTenant }))
    await userEvent.type(await screen.findByLabelText('Identificador corto'), 'empresa-c')
    await userEvent.type(screen.getByLabelText('Nombre de la empresa'), 'Empresa C')
    await userEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText('Clave-Inicial-9x')).toBeInTheDocument()
    expect(screen.getByText(/se muestra una sola vez/)).toBeInTheDocument()
    expect(provisionTenant).toHaveBeenCalledWith('empresa-c', 'Empresa C')
    await userEvent.click(screen.getByRole('button', { name: 'Entendido, ocultar' }))
    expect(screen.queryByText('Clave-Inicial-9x')).toBeNull()
  })

  it('crear una empresa que ya existía no muestra contraseña', async () => {
    const provisionTenant = vi.fn(() =>
      Promise.resolve({
        tenant: { slug: 'empresa-c', name: 'Empresa C', status: 'active' as const, created_at: '2026-10-13T13:00:00Z', user_count: 1 },
        created: false,
        admin_username: null,
        initial_admin_password: null,
      }),
    )
    renderApp(makeFakeClient('super_admin', { provisionTenant }))
    await userEvent.type(await screen.findByLabelText('Identificador corto'), 'empresa-c')
    await userEvent.type(screen.getByLabelText('Nombre de la empresa'), 'Empresa C')
    await userEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText(/ya existía/)).toBeInTheDocument()
    expect(screen.queryByText(/Contraseña inicial/)).toBeNull()
  })

  it('un conflicto del servidor se muestra en el formulario', async () => {
    const provisionTenant = vi.fn(() =>
      Promise.reject(new ApiError(409, 'CONFLICTO', 'Ya existe una empresa con ese identificador y otro nombre.')),
    )
    renderApp(makeFakeClient('super_admin', { provisionTenant }))
    await userEvent.type(await screen.findByLabelText('Identificador corto'), 'empresa-c')
    await userEvent.type(screen.getByLabelText('Nombre de la empresa'), 'Otro')
    await userEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('otro nombre')
  })
})

describe('auditoría', () => {
  it('traduce acciones y resultados y no depende solo del color', async () => {
    renderApp(makeFakeClient('tenant_admin'), '/auditoria')
    const table = await screen.findByRole('table', { name: 'Eventos de auditoría' })
    expect(within(table).getByText('Inicio de sesión')).toBeInTheDocument()
    expect(within(table).getByText('Consulta del tablero de capacidad')).toBeInTheDocument()
    expect(within(table).getByText(/Fallido/)).toBeInTheDocument()
    expect(within(table).getByText(/Correcto/)).toBeInTheDocument()
    expect(table).toHaveTextContent('reason: bad_password')
  })

  it('sin eventos muestra un estado vacío', async () => {
    renderApp(makeFakeClient('tenant_admin', { audit: vi.fn(() => Promise.resolve([])) }), '/auditoria')
    expect(await screen.findByText('Sin eventos registrados')).toBeInTheDocument()
  })

  it('el texto del alcance depende del rol', async () => {
    renderApp(makeFakeClient('super_admin'), '/auditoria')
    expect(await screen.findByText(/de todas las empresas/)).toBeInTheDocument()
    expect(AUDIT.length).toBeGreaterThan(0)
  })
})
