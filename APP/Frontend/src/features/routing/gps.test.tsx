import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from '../../app/App'
import type { RoutingSnapshot } from '../../api/types'
import { makeFakeClient, makeSnapshot } from '../../test/fixtures'
import { POLL_MS } from './RoutingProvider'

type Client = ReturnType<typeof makeFakeClient>

const open = (client: Client) =>
  render(
    <MemoryRouter initialEntries={['/torre-de-control']}>
      <App client={client} />
    </MemoryRouter>,
  )

const withVehicle = (patch: Record<string, unknown>): RoutingSnapshot => {
  const base = makeSnapshot()
  return {
    ...base,
    vehicles: base.vehicles.map((v) => (v.id === 'V-02' ? { ...v, ...patch } : v)),
  } as RoutingSnapshot
}

afterEach(() => vi.useRealTimers())

describe('GPS en la torre de control', () => {
  it('muestra la señal de cada vehículo con la antigüedad de su última posición', async () => {
    open(makeFakeClient('dispatcher'))
    const table = await screen.findByRole('table', { name: 'Estado de los vehículos' })
    expect(within(table).getAllByText(/Señal OK · última posición hace 1 min/).length).toBe(2)
    expect(within(table).getByRole('row', { name: /T-03/ })).toHaveTextContent('—')
  })

  it('"sin señal" se dice con texto, con la edad, y aparece en las alertas', async () => {
    const snapshot = {
      ...withVehicle({ gps_status: 'no_signal', gps_age_min: 18, gps_signal_enabled: false }),
      alerts: [
        { level: 'critical', code: 'no_signal', message: 'T-02 sin señal GPS: última posición hace 18 min (08:42). Se conserva el plan vigente.', vehicle_id: 'V-02' },
      ],
    } as RoutingSnapshot
    open(makeFakeClient('dispatcher', { tower: vi.fn(() => Promise.resolve(snapshot)) }))
    const table = await screen.findByRole('table', { name: 'Estado de los vehículos' })
    expect(within(table).getByText(/Sin señal · última posición hace 18 min/)).toBeInTheDocument()
    const alerts = screen.getByRole('list', { name: 'Alertas del día' })
    expect(alerts).toHaveTextContent('Se conserva el plan vigente')
  })

  it('cortar la señal de un vehículo llama al backend con el vehículo elegido', async () => {
    const client = makeFakeClient('dispatcher')
    open(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Cortar la señal GPS de T-02' }))
    expect(client.controlSimulation).toHaveBeenLastCalledWith('gps_signal', 0, 'V-02')
  })

  it('con la señal cortada el botón pasa a restablecer', async () => {
    const snapshot = withVehicle({ gps_signal_enabled: false, gps_status: 'no_signal', gps_age_min: 20 })
    const client = makeFakeClient('dispatcher', { tower: vi.fn(() => Promise.resolve(snapshot)) })
    open(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Restablecer la señal GPS de T-02' }))
    expect(client.controlSimulation).toHaveBeenLastCalledWith('gps_signal', 1, 'V-02')
  })

  it('las entregas confirmadas indican si fue por geocerca y a qué hora', async () => {
    const base = makeSnapshot()
    const snapshot = {
      ...base,
      stops: base.stops.map((s) =>
        s.key === 'P-001' ? { ...s, confirmed_by: 'geofence', confirmed_min: 455 } : s,
      ),
    } as RoutingSnapshot
    open(makeFakeClient('dispatcher', { tower: vi.fn(() => Promise.resolve(snapshot)) }))
    const stops = await screen.findByRole('table', { name: 'Paradas del plan vigente' })
    expect(within(stops).getByText('Confirmada por geocerca a las 07:35')).toBeInTheDocument()
  })

  it('las entregas sin confirmar no muestran confirmación', async () => {
    open(makeFakeClient('dispatcher'))
    const stops = await screen.findByRole('table', { name: 'Paradas del plan vigente' })
    expect(within(stops).queryByText(/Confirmada/)).toBeNull()
  })
})

describe('tiempo real', () => {
  it('se suscribe al flujo y aplica cada estado que llega, sin consultar', async () => {
    let push: (s: RoutingSnapshot) => void = () => undefined
    const watchTower = vi.fn((onSnapshot: (s: RoutingSnapshot) => void) => {
      push = onSnapshot
      return () => undefined
    })
    const running = makeSnapshot({ clock: { now: 'x', minute: 480, speed: 30, paused: false, simulated: true } })
    const client = makeFakeClient('dispatcher', { watchTower, tower: vi.fn(() => Promise.resolve(running)) })
    open(client)
    expect(await screen.findByText('Actualizando por consulta periódica')).toBeInTheDocument()
    act(() => push({ ...running, clock: { ...running.clock, minute: 510 } }))
    expect(await screen.findByText('Tiempo real conectado')).toBeInTheDocument()
    expect(screen.getAllByText('08:30').length).toBeGreaterThan(0)
    expect(client.track).not.toHaveBeenCalled()
  })

  it('cierra la suscripción al salir de la pantalla', async () => {
    const stop = vi.fn()
    const client = makeFakeClient('dispatcher', { watchTower: vi.fn(() => stop) })
    const { unmount } = open(client)
    await screen.findByRole('heading', { name: 'Torre de control' })
    unmount()
    expect(stop).toHaveBeenCalled()
  })

  it('si el flujo no está disponible vuelve a consultar el seguimiento cada pocos segundos', async () => {
    vi.useFakeTimers()
    let fail: (e: unknown) => void = () => undefined
    const watchTower = vi.fn((_: unknown, onUnavailable: (e: unknown) => void) => {
      fail = onUnavailable
      return () => undefined
    })
    const running = makeSnapshot({ clock: { now: 'x', minute: 480, speed: 30, paused: false, simulated: true } })
    const client = makeFakeClient('dispatcher', {
      watchTower,
      tower: vi.fn(() => Promise.resolve(running)),
      track: vi.fn(() => Promise.resolve(running)),
    })
    open(client)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    act(() => fail(new Error('sin flujo')))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS + 50)
    })
    expect(client.track).toHaveBeenCalledTimes(1)
  })

  it('con el flujo conectado no hace consultas de respaldo aunque el reloj corra', async () => {
    vi.useFakeTimers()
    let push: (s: RoutingSnapshot) => void = () => undefined
    const watchTower = vi.fn((onSnapshot: (s: RoutingSnapshot) => void) => {
      push = onSnapshot
      return () => undefined
    })
    const running = makeSnapshot({ clock: { now: 'x', minute: 480, speed: 30, paused: false, simulated: true } })
    const client = makeFakeClient('dispatcher', { watchTower, tower: vi.fn(() => Promise.resolve(running)) })
    open(client)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    act(() => push(running))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS * 4)
    })
    expect(client.track).not.toHaveBeenCalled()
  })
})
