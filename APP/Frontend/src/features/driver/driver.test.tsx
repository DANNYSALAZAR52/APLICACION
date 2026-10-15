import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from '../../app/App'
import { ApiError } from '../../api/errors'
import type { DriverRouteOut } from '../../api/types'
import { makeDriverRoute, makeFakeClient, makeSnapshot } from '../../test/fixtures'

const open = (overrides: Record<string, unknown> = {}) => {
  const client = makeFakeClient('driver', overrides)
  render(
    <MemoryRouter initialEntries={['/mi-ruta']}>
      <App client={client} />
    </MemoryRouter>,
  )
  return client
}

const route = (patch: Partial<DriverRouteOut> = {}) => ({
  driverRoute: vi.fn(() => Promise.resolve(makeDriverRoute(patch))),
})

afterEach(() => vi.restoreAllMocks())

describe('hoja de ruta del conductor', () => {
  it('muestra su vehículo, la siguiente parada y el enlace a Google Maps', async () => {
    open()
    expect(await screen.findByRole('heading', { name: 'Mi hoja de ruta' })).toBeInTheDocument()
    expect(screen.getByText(/Vehículo/)).toHaveTextContent('T-01')
    const next = screen.getByRole('heading', { name: 'Siguiente parada' }).closest('section') as HTMLElement
    expect(within(next).getByText('Cliente 02 · Fontibón')).toBeInTheDocument()
    const link = within(next).getByRole('link', { name: 'Abrir la ruta en Google Maps' })
    expect(link).toHaveAttribute('href', expect.stringContaining('https://www.google.com/maps/dir/?api=1'))
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(within(next).getByText(/Es solo un enlace de navegación/)).toBeInTheDocument()
  })

  it('separa las paradas pendientes de las ya atendidas', async () => {
    open()
    const pending = (await screen.findByRole('heading', { name: /Paradas pendientes \(1\)/ })).closest('section') as HTMLElement
    expect(within(pending).getByText('Cliente 02 · Fontibón')).toBeInTheDocument()
    expect(within(pending).queryByText('Cliente 01 · Engativá')).toBeNull()
    expect(screen.getByText(/Paradas ya atendidas \(1\)/)).toBeInTheDocument()
  })

  it('con varios tramos muestra un botón por tramo', async () => {
    open(
      route({
        nav_links: [
          { label: 'Tramo 1 de 2 en Google Maps (paradas 1 a 10)', url: 'https://www.google.com/maps/dir/?api=1&destination=1', stops: 10 },
          { label: 'Tramo 2 de 2 en Google Maps (paradas 11 a 12)', url: 'https://www.google.com/maps/dir/?api=1&destination=2', stops: 2 },
        ],
      }),
    )
    expect(await screen.findByRole('link', { name: /Tramo 1 de 2/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Tramo 2 de 2/ })).toBeInTheDocument()
  })

  it('muestra los avisos del despacho (por ejemplo, ruta actualizada o averiado)', async () => {
    open(route({ notices: ['La ruta fue actualizada por el despacho (plan versión 2: Cierre vial).'] }))
    expect(await screen.findByText(/plan versión 2/)).toBeInTheDocument()
  })

  it('sin paradas pendientes indica regresar al CEDI', async () => {
    const base = makeDriverRoute()
    open(route({ stops: base.stops.map((s) => ({ ...s, stop: { ...s.stop, state: 'completed' as const } })), next_key: null, nav_links: [] }))
    expect(await screen.findByText(/No tiene paradas pendientes/)).toBeInTheDocument()
  })

  it('confirmar la entrega pide confirmación, llama al backend y avisa', async () => {
    const base = makeDriverRoute()
    const arrived = {
      stops: base.stops.map((s) => (s.stop.key === 'P-002' ? { ...s, stop: { ...s.stop, state: 'in_service' as const } } : s)),
    }
    const client = open(route(arrived))
    await userEvent.click(await screen.findByRole('button', { name: 'Confirmar entrega a Cliente 02 · Fontibón' }))
    const dialog = await screen.findByRole('dialog', { name: 'Confirmar entrega' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Sí, entregué' }))
    expect(client.confirmDelivery).toHaveBeenCalledWith('P-002')
    expect(await screen.findByText('Entrega confirmada. Gracias.')).toBeInTheDocument()
  })

  it('no ofrece confirmar una parada a la que aún no llega', async () => {
    open()
    const pending = (await screen.findByRole('heading', { name: /Paradas pendientes/ })).closest('section') as HTMLElement
    expect(within(pending).queryByRole('button', { name: /Confirmar entrega a/ })).toBeNull()
    // una parada ya pasada y sin confirmar sí permite confirmarla después
    expect(screen.getByRole('button', { name: 'Confirmar entrega a Cliente 01 · Engativá' })).toBeInTheDocument()
  })

  it('si la entrega ya estaba confirmada por geocerca lo dice', async () => {
    const base = makeDriverRoute()
    const stops = base.stops.map((s) => (s.stop.key === 'P-002' ? { ...s, stop: { ...s.stop, state: 'in_service' as const } } : s))
    const client = open({
      ...route({ stops }),
      confirmDelivery: vi.fn(() => Promise.resolve({ order_id: 'P-002', source: 'geofence', minute: 500, already_confirmed: true })),
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Confirmar entrega a Cliente 02 · Fontibón' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Sí, entregué' }))
    expect(await screen.findByText(/ya estaba confirmada por geocerca/)).toBeInTheDocument()
    expect(client.confirmDelivery).toHaveBeenCalledTimes(1)
  })

  it('muestra el error del servidor al confirmar fuera de lugar', async () => {
    const base = makeDriverRoute()
    const stops = base.stops.map((s) => (s.stop.key === 'P-002' ? { ...s, stop: { ...s.stop, state: 'in_service' as const } } : s))
    open({
      ...route({ stops }),
      confirmDelivery: vi.fn(() => Promise.reject(new ApiError(409, 'CONFLICTO', 'Aún no llega a esta parada.'))),
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Confirmar entrega a Cliente 02 · Fontibón' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Sí, entregué' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Aún no llega a esta parada.')
  })

  it('las entregas confirmadas muestran por quién y a qué hora', async () => {
    const base = makeDriverRoute()
    const stops = base.stops.map((s) =>
      s.stop.key === 'P-001' ? { ...s, stop: { ...s.stop, confirmed_by: 'geofence' as const, confirmed_min: 455 } } : s,
    )
    open(route({ stops }))
    await userEvent.click(await screen.findByText(/Paradas ya atendidas/))
    expect(screen.getByText(/Entrega confirmada por geocerca a las 07:35/)).toBeInTheDocument()
  })
})

describe('reportar novedad', () => {
  const report = {
    id: 'NV-001', vehicle_id: 'V-01', plate: 'T-01', minute: 495, kind: 'customer_absent' as const,
    detail: 'Nadie abre la puerta', by: 'conductor', order_id: 'P-002',
  }

  it('valida la descripción en el navegador sin llamar a la API', async () => {
    const client = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Reportar una novedad general' }))
    await userEvent.type(screen.getByLabelText('¿Qué ocurrió?'), 'ab')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar novedad' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('3 a 300 caracteres')
    expect(client.reportIncident).not.toHaveBeenCalled()
  })

  it('envía el tipo, la descripción y el pedido de la parada elegida', async () => {
    const client = open({ reportIncident: vi.fn(() => Promise.resolve(report)) })
    await userEvent.click(await screen.findByRole('button', { name: 'Reportar novedad en Cliente 02 · Fontibón' }))
    const dialog = await screen.findByRole('dialog', { name: 'Reportar novedad' })
    expect(dialog).toHaveTextContent('Pedido P-002')
    await userEvent.selectOptions(within(dialog).getByLabelText('Tipo de novedad'), 'access_blocked')
    await userEvent.type(within(dialog).getByLabelText('¿Qué ocurrió?'), '  Calle   cerrada por obra ')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Enviar novedad' }))
    expect(client.reportIncident).toHaveBeenCalledWith('access_blocked', 'Calle cerrada por obra', 'P-002')
    expect(await screen.findByText('Novedad enviada al despachador.')).toBeInTheDocument()
  })

  it('una novedad general no lleva pedido', async () => {
    const client = open({ reportIncident: vi.fn(() => Promise.resolve({ ...report, order_id: null })) })
    await userEvent.click(await screen.findByRole('button', { name: 'Reportar una novedad general' }))
    await userEvent.type(screen.getByLabelText('¿Qué ocurrió?'), 'Se pinchó una llanta')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar novedad' }))
    expect(client.reportIncident).toHaveBeenCalledWith('customer_absent', 'Se pinchó una llanta', null)
  })

  it('muestra el error del servidor dentro del formulario y conserva lo escrito', async () => {
    open({ reportIncident: vi.fn(() => Promise.reject(new ApiError(429, 'DEMASIADOS_INTENTOS', 'Demasiadas operaciones seguidas; espere un momento.'))) })
    await userEvent.click(await screen.findByRole('button', { name: 'Reportar una novedad general' }))
    await userEvent.type(screen.getByLabelText('¿Qué ocurrió?'), 'Aviso repetido')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar novedad' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Demasiadas operaciones')
    expect(screen.getByLabelText('¿Qué ocurrió?')).toHaveValue('Aviso repetido')
  })

  it('lista las novedades ya enviadas', async () => {
    open(route({ reports: [report] }))
    const card = (await screen.findByRole('heading', { name: 'Mis novedades' })).closest('section') as HTMLElement
    expect(card).toHaveTextContent('Cliente ausente')
    expect(card).toHaveTextContent('Nadie abre la puerta')
  })
})

describe('estados y actualización', () => {
  it('mientras carga muestra un estado accesible', async () => {
    open({ driverRoute: vi.fn(() => new Promise<never>(() => undefined)) })
    const status = await screen.findByText('Cargando su hoja de ruta…')
    expect(status.closest('[role="status"]')).not.toBeNull()
  })

  it('un error de carga ofrece reintentar', async () => {
    const driverRoute = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(500, 'ERROR_INTERNO', 'Ocurrió un error interno.'))
      .mockResolvedValue(makeDriverRoute())
    open({ driverRoute })
    await userEvent.click(within(await screen.findByRole('alert')).getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { name: 'Mi hoja de ruta' })).toBeInTheDocument()
  })

  it('un conductor sin vehículo asignado ve el motivo', async () => {
    open({ driverRoute: vi.fn(() => Promise.reject(new ApiError(403, 'PERMISO_DENEGADO', 'Su usuario no tiene un vehículo asignado.'))) })
    expect(await screen.findByRole('alert')).toHaveTextContent('vehículo asignado')
  })

  it('se actualiza sola cada pocos segundos', async () => {
    vi.useFakeTimers()
    const client = makeFakeClient('driver')
    render(
      <MemoryRouter initialEntries={['/mi-ruta']}>
        <App client={client} />
      </MemoryRouter>,
    )
    const { act } = await import('@testing-library/react')
    const { DRIVER_REFRESH_MS } = await import('./DriverPage')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    const first = client.driverRoute.mock.calls.length
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DRIVER_REFRESH_MS * 2 + 50)
    })
    expect(client.driverRoute.mock.calls.length).toBeGreaterThanOrEqual(first + 2)
    vi.useRealTimers()
  })

  it('el despachador ve las novedades de los conductores en la torre de control', async () => {
    const snapshot = makeSnapshot({
      reports: [{ id: 'NV-001', vehicle_id: 'V-01', plate: 'T-01', minute: 495, kind: 'access_blocked', detail: 'Calle cerrada', by: 'conductor', order_id: 'P-002' }],
    })
    const client = makeFakeClient('dispatcher', { tower: vi.fn(() => Promise.resolve(snapshot)) })
    render(
      <MemoryRouter initialEntries={['/torre-de-control']}>
        <App client={client} />
      </MemoryRouter>,
    )
    const card = (await screen.findByRole('heading', { name: 'Novedades de los conductores' })).closest('section') as HTMLElement
    expect(card).toHaveTextContent('Acceso bloqueado')
    expect(card).toHaveTextContent('Calle cerrada')
  })
})
