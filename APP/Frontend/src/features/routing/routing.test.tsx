import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from '../../app/App'
import { ApiError } from '../../api/errors'
import { diffSequences } from '../../domain-ui/planDiff'
import { formatClock, parseClock } from '../../domain-ui/routing'
import { makeFakeClient, makePlanDetail, makeProposal, makeSnapshot } from '../../test/fixtures'
import { POLL_MS } from './RoutingProvider'

type Client = ReturnType<typeof makeFakeClient>

function renderApp(client: Client, route = '/torre-de-control') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App client={client} />
    </MemoryRouter>,
  )
}

const dispatcher = (overrides: Record<string, unknown> = {}) => makeFakeClient('dispatcher', overrides)

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('formatos de hora', () => {
  it('formatea minutos desde la medianoche', () => {
    expect(formatClock(375)).toBe('06:15')
    expect(formatClock(0)).toBe('00:00')
    expect(formatClock(1439.6)).toBe('00:00')
    expect(formatClock(null)).toBe('—')
  })

  it('interpreta HH:MM y rechaza lo que no es una hora', () => {
    expect(parseClock('06:15')).toBe(375)
    expect(parseClock(' 9:05 ')).toBe(545)
    for (const bad of ['25:00', '10:75', 'ab:cd', '', '1015']) expect(parseClock(bad)).toBeNull()
  })

  it('marca qué cambió entre dos secuencias', () => {
    expect(diffSequences(['A', 'B', 'C'], ['A', 'B', 'C']).every((d) => d.change === 'same')).toBe(true)
    const diff = diffSequences(['A', 'B', 'C'], ['B', 'A', 'D'])
    expect(diff.find((d) => d.item === 'D')?.change).toBe('new')
    expect(diff.find((d) => d.item === 'C')?.change).toBe('removed')
    expect(diff.filter((d) => d.change === 'moved').map((d) => d.item).sort()).toEqual(['A', 'B'])
  })
})

describe('torre de control', () => {
  it('muestra resumen, vehículos, paradas y el mapa con su aviso de DEMO-ONLY', async () => {
    renderApp(dispatcher())
    expect(await screen.findByRole('heading', { name: 'Torre de control' })).toBeInTheDocument()
    expect(screen.getByText(/Plan versión/)).toHaveTextContent('Plan inicial de la mañana')
    const vehicles = screen.getByRole('table', { name: 'Estado de los vehículos' })
    expect(within(vehicles).getByRole('row', { name: /T-01/ })).toBeInTheDocument()
    expect(within(vehicles).getByText('Retraso proyectado')).toBeInTheDocument()
    expect(within(vehicles).getAllByText(/A tiempo/).length).toBeGreaterThan(0)
    expect(within(vehicles).getByText(/1 tarde/)).toBeInTheDocument()
    expect(within(vehicles).getByText('Disponible (sin ruta)')).toBeInTheDocument()
    const stops = screen.getByRole('table', { name: 'Paradas del plan vigente' })
    expect(within(stops).getAllByRole('row').length).toBe(5)
    expect(screen.getByRole('region', { name: /Mapa de la flota/ })).toBeInTheDocument()
    expect(screen.getByText(/línea recta entre paradas \(DEMO-ONLY/)).toBeInTheDocument()
  })

  it('el estado de la entrega se dice con texto, no solo con color', async () => {
    renderApp(dispatcher())
    const stops = await screen.findByRole('table', { name: 'Paradas del plan vigente' })
    expect(within(stops).getAllByText(/Entregada/).length).toBe(2)
    expect(within(stops).getByText(/Tarde 20 min/)).toBeInTheDocument()
  })

  it('filtra las paradas por vehículo', async () => {
    renderApp(dispatcher())
    await screen.findByRole('heading', { name: 'Torre de control' })
    await userEvent.selectOptions(screen.getByLabelText('Vehículo'), 'T-02')
    const stops = screen.getByRole('table', { name: 'Paradas del plan vigente' })
    expect(within(stops).queryByText('Cliente 01 · Engativá')).toBeNull()
    expect(within(stops).getByText('Cliente 04 · Usaquén')).toBeInTheDocument()
  })

  it('con el proveedor caído avisa "Tiempos estimados sin tráfico" y no afirma tráfico en vivo', async () => {
    const snapshot = makeSnapshot({
      travel_notice: 'Tiempos estimados sin tráfico',
      provider_available: false,
      alerts: [{ level: 'warning', code: 'degraded_times', message: 'Tiempos estimados sin tráfico', vehicle_id: null }],
    })
    renderApp(dispatcher({ tower: vi.fn(() => Promise.resolve(snapshot)) }))
    const notice = await screen.findByText(/No hay información de tráfico en vivo/)
    expect(notice.closest('[role="status"]')).toHaveTextContent('Tiempos estimados sin tráfico')
    expect(screen.getByRole('button', { name: 'Restablecer proveedor de tiempos' })).toBeInTheDocument()
  })

  it('lista las alertas con su nivel en texto', async () => {
    const snapshot = makeSnapshot({
      alerts: [
        { level: 'critical', code: 'late_deliveries', message: 'T-02: 1 entrega(s) llegarían tarde', vehicle_id: 'V-02' },
        { level: 'warning', code: 'at_risk', message: 'T-01: poca holgura', vehicle_id: 'V-01' },
      ],
    })
    renderApp(dispatcher({ tower: vi.fn(() => Promise.resolve(snapshot)) }))
    const list = await screen.findByRole('list', { name: 'Alertas del día' })
    expect(within(list).getByText(/Crítica/)).toBeInTheDocument()
    expect(within(list).getByText(/Atención/)).toBeInTheDocument()
  })

  it('sin alertas lo dice en vez de dejar el panel vacío', async () => {
    renderApp(dispatcher())
    expect(await screen.findByText(/Sin alertas/)).toBeInTheDocument()
  })

  it('los pedidos sin asignar se muestran con su motivo', async () => {
    const snapshot = makeSnapshot({
      unassigned: [{ order_id: 'P-009', customer_code: 'C-009', reason: 'El pedido pesa 9000 kg y supera la capacidad.' }],
    })
    renderApp(dispatcher({ tower: vi.fn(() => Promise.resolve(snapshot)) }))
    const reason = await screen.findByText(/supera la capacidad/)
    expect(reason.closest('[role="alert"]')).toHaveTextContent('Pedidos sin asignar')
  })

  it('un error de carga ofrece reintentar y se recupera', async () => {
    const tower = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(500, 'ERROR_INTERNO', 'Ocurrió un error interno.', 'req-3'))
      .mockResolvedValue(makeSnapshot())
    renderApp(dispatcher({ tower }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('req-3')
    await userEvent.click(within(alert).getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { name: 'Torre de control' })).toBeInTheDocument()
  })

  it('mientras prepara el plan muestra un estado de carga accesible', async () => {
    renderApp(dispatcher({ tower: vi.fn(() => new Promise<never>(() => undefined)) }))
    const status = await screen.findByText('Preparando el plan de la mañana…')
    expect(status.closest('[role="status"]')).not.toBeNull()
  })
})

describe('reloj simulado', () => {
  it('reanudar, adelantar y cambiar la velocidad llaman al backend', async () => {
    const client = dispatcher()
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Reanudar' }))
    expect(client.controlSimulation).toHaveBeenLastCalledWith('resume', undefined, undefined)
    await userEvent.click(screen.getByRole('button', { name: '+15 min' }))
    expect(client.controlSimulation).toHaveBeenLastCalledWith('advance', 15, undefined)
    await userEvent.selectOptions(screen.getByLabelText('Velocidad'), '60')
    expect(client.controlSimulation).toHaveBeenLastCalledWith('speed', 60, undefined)
  })

  it('con el reloj corriendo ofrece pausar', async () => {
    const running = makeSnapshot({ clock: { now: 'x', minute: 480, speed: 30, paused: false, simulated: true } })
    renderApp(dispatcher({ tower: vi.fn(() => Promise.resolve(running)) }))
    expect(await screen.findByRole('button', { name: 'Pausar' })).toBeInTheDocument()
    expect(screen.getByText(/Corriendo a 30×/)).toBeInTheDocument()
  })

  it('reiniciar el día y simular la falla del proveedor son acciones explícitas', async () => {
    const client = dispatcher()
    renderApp(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Reiniciar día' }))
    expect(client.resetDay).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/Día reiniciado/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Simular falla del proveedor de tiempos' }))
    expect(client.controlSimulation).toHaveBeenLastCalledWith('provider', 0, undefined)
  })

  it('si el backend rechaza una acción muestra su mensaje', async () => {
    const controlSimulation = vi.fn(() =>
      Promise.reject(new ApiError(429, 'DEMASIADOS_INTENTOS', 'Demasiadas operaciones seguidas; espere un momento.')),
    )
    renderApp(dispatcher({ controlSimulation }))
    await userEvent.click(await screen.findByRole('button', { name: 'Reanudar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Demasiadas operaciones seguidas')
  })

  it('mientras el reloj corre pide el seguimiento cada pocos segundos; en pausa no', async () => {
    vi.useFakeTimers()
    const running = makeSnapshot({ clock: { now: 'x', minute: 480, speed: 30, paused: false, simulated: true } })
    const client = dispatcher({ tower: vi.fn(() => Promise.resolve(running)), track: vi.fn(() => Promise.resolve(running)) })
    renderApp(client)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    expect(screen.getByRole('heading', { name: 'Torre de control' })).toBeInTheDocument()
    expect(client.track).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS + 50)
    })
    expect(client.track).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS)
    })
    expect(client.track).toHaveBeenCalledTimes(2)
  })

  it('en pausa no consulta el seguimiento', async () => {
    vi.useFakeTimers()
    const client = dispatcher()
    renderApp(client)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    })
    expect(client.track).not.toHaveBeenCalled()
  })
})

describe('línea de tiempo', () => {
  it('dibuja una fila por vehículo en operación y ofrece la tabla equivalente', async () => {
    renderApp(dispatcher(), '/linea-de-tiempo')
    expect(await screen.findByRole('heading', { name: 'Línea de tiempo por vehículo' })).toBeInTheDocument()
    const svg = screen.getByRole('img', { name: /Línea de tiempo de paradas por vehículo/ })
    expect(svg.querySelectorAll('rect').length).toBeGreaterThan(0)
    expect(within(svg as unknown as HTMLElement).getByText('T-01')).toBeInTheDocument()
    expect(within(svg as unknown as HTMLElement).queryByText(/reserva/)).toBeNull()
    expect(screen.getByRole('table', { name: 'Paradas de T-02', hidden: true })).toBeInTheDocument()
    expect(screen.getByText(/Ahora 08:15/)).toBeInTheDocument()
  })
})

describe('eventos y re-ruteo', () => {
  const open = (client: Client) => renderApp(client, '/eventos')

  it('solo el despachador (con routing:events) puede abrir la pantalla', async () => {
    const client = makeFakeClient('management')
    renderApp(client, '/eventos')
    expect(await screen.findByText('Permisos insuficientes')).toBeInTheDocument()
    expect(client.tower).not.toHaveBeenCalled()
  })

  it('inyecta un cierre vial con números convertidos y avisa que el sistema solo propone', async () => {
    const proposal = makeProposal()
    const injectEvent = vi.fn(() =>
      Promise.resolve({
        event: { id: 'EV-001', type: 'road_closure' as const, occurred_at: 'x', minute: 495, created_by: 'despachador', summary: 'Cierre vial «Calle 80»', outcome: '', proposal_ids: ['PR-001'] },
        proposal,
      }),
    )
    const client = dispatcher({ injectEvent })
    open(client)
    expect(await screen.findByText(/nada cambia hasta que usted apruebe/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Inyectar evento' }))
    expect(injectEvent).toHaveBeenCalledWith({
      type: 'road_closure',
      label: 'Calle 80',
      lat: 4.722,
      lon: -74.1,
      radius_km: 2.5,
      factor: 2.5,
      duration_min: 255,
    })
    expect(await screen.findByText(/Evento registrado/)).toBeInTheDocument()
  })

  it('valida lo evidente en el navegador sin llamar a la API', async () => {
    const client = dispatcher()
    open(client)
    await userEvent.click(await screen.findByLabelText('Pedido urgente'))
    const start = screen.getByLabelText('Ventana desde (HH:MM)')
    const end = screen.getByLabelText('Ventana hasta (HH:MM)')
    await userEvent.clear(start)
    await userEvent.type(start, '14:00')
    await userEvent.clear(end)
    await userEvent.type(end, '10:00')
    await userEvent.click(screen.getByRole('button', { name: 'Inyectar evento' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('La ventana 14:00–10:00 no es válida')
    expect(alert).toHaveTextContent('posterior a la inicial')
    expect(client.injectEvent).not.toHaveBeenCalled()
  })

  it('exige elegir el vehículo averiado y solo ofrece vehículos con entregas pendientes', async () => {
    const client = dispatcher()
    open(client)
    await userEvent.click(await screen.findByLabelText('Avería'))
    const select = screen.getByLabelText('Vehículo averiado')
    expect(within(select).queryByText(/reserva/)).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Inyectar evento' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Elija el vehículo averiado')
    expect(client.injectEvent).not.toHaveBeenCalled()
  })

  it('muestra el error del servidor, por ejemplo una latitud fuera de Colombia', async () => {
    const injectEvent = vi.fn(() =>
      Promise.reject(new ApiError(422, 'DATO_INVALIDO', 'La latitud 40 está fuera de Colombia (debe estar entre -4,3 y 13,5).')),
    )
    open(dispatcher({ injectEvent }))
    const lat = await screen.findByLabelText('Latitud del centro')
    await userEvent.clear(lat)
    await userEvent.type(lat, '40')
    await userEvent.click(screen.getByRole('button', { name: 'Inyectar evento' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('fuera de Colombia')
  })

  it('la propuesta pendiente muestra motivo, impacto antes/después y pide confirmar', async () => {
    const snapshot = makeSnapshot({
      proposals: [makeProposal({ requires_confirmation: true })],
      events: [{ id: 'EV-001', type: 'road_closure', occurred_at: 'x', minute: 495, created_by: 'despachador', summary: 'Cierre vial «Calle 80»', outcome: 'Se re-secuencian…', proposal_ids: ['PR-001'] }],
    })
    open(dispatcher({ tower: vi.fn(() => Promise.resolve(snapshot)) }))
    const card = await screen.findByRole('article', { name: 'Cierre vial: Calle 80' })
    expect(card).toHaveTextContent('Pendiente de decisión')
    expect(card).toHaveTextContent('Su confirmación es obligatoria')
    expect(card).toHaveTextContent('3 → 0')
    expect(card).toHaveTextContent('97 min → 0 min')
    expect(card).toHaveTextContent('(mejora)')
    expect(card).toHaveTextContent('Calculada sobre el plan versión 1')
    expect(screen.getByRole('table', { name: 'Eventos operativos del día' })).toBeInTheDocument()
  })

  it('aprobar pide confirmación, envía el comentario y avisa la versión creada', async () => {
    const proposal = makeProposal()
    const snapshot = makeSnapshot({ proposals: [proposal] })
    const decideProposal = vi.fn(() =>
      Promise.resolve({
        proposal: { ...proposal, status: 'approved' as const },
        replacement: null,
        plan_version: 2,
        message: 'Plan actualizado a la versión 2.',
      }),
    )
    const client = dispatcher({ tower: vi.fn(() => Promise.resolve(snapshot)), decideProposal })
    open(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Aprobar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Aprobar propuesta' })
    expect(dialog).toHaveTextContent('la versión 1 se conserva intacta')
    await userEvent.type(within(dialog).getByLabelText('Comentario (opcional)'), 'adelante')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Aprobar y crear nueva versión' }))
    await waitFor(() => expect(decideProposal).toHaveBeenCalledWith('PR-001', 'approve', 'adelante'))
    expect(await screen.findByText('Plan actualizado a la versión 2.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('cancelar el diálogo no decide nada', async () => {
    const client = dispatcher({ tower: vi.fn(() => Promise.resolve(makeSnapshot({ proposals: [makeProposal()] }))) })
    open(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Rechazar' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }))
    expect(client.decideProposal).not.toHaveBeenCalled()
  })

  it('rechazar deja el plan vigente y se registra', async () => {
    const proposal = makeProposal()
    const decideProposal = vi.fn(() =>
      Promise.resolve({
        proposal: { ...proposal, status: 'rejected' as const },
        replacement: null,
        plan_version: null,
        message: 'Propuesta rechazada; el plan vigente no cambió.',
      }),
    )
    open(dispatcher({ tower: vi.fn(() => Promise.resolve(makeSnapshot({ proposals: [proposal] }))), decideProposal }))
    await userEvent.click(await screen.findByRole('button', { name: 'Rechazar' }))
    const dialog = await screen.findByRole('dialog', { name: 'Rechazar propuesta' })
    expect(dialog).toHaveTextContent('El plan vigente no cambia')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Rechazar' }))
    await waitFor(() => expect(decideProposal).toHaveBeenCalledWith('PR-001', 'reject', ''))
    expect(await screen.findByText(/el plan vigente no cambió/)).toBeInTheDocument()
  })

  it('una propuesta que quedó obsoleta se explica y no se aplica a ciegas', async () => {
    const proposal = makeProposal()
    const fresh = makeProposal({ id: 'PR-002' })
    const decideProposal = vi.fn(() =>
      Promise.resolve({
        proposal: { ...proposal, status: 'superseded' as const },
        replacement: fresh,
        plan_version: null,
        message: 'La situación cambió desde que se generó la propuesta: se recalculó. Revise la propuesta nueva y confirme de nuevo.',
      }),
    )
    open(dispatcher({ tower: vi.fn(() => Promise.resolve(makeSnapshot({ proposals: [proposal] }))), decideProposal }))
    await userEvent.click(await screen.findByRole('button', { name: 'Aprobar' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Aprobar y crear nueva versión' }))
    expect(await screen.findByText(/se recalculó/)).toBeInTheDocument()
  })

  it('las propuestas resueltas muestran quién decidió y las que no requieren cambios lo dicen', async () => {
    const snapshot = makeSnapshot({
      proposals: [
        makeProposal({ id: 'PR-003', status: 'approved', decided_by: 'despachador', decided_at: '2026-10-14T08:20:00-05:00', decision_comment: 'ok', applied_version: 2 }),
        makeProposal({ id: 'PR-004', status: 'none_needed', reason: 'Cierre vial: lejos', routes: [] }),
      ],
    })
    open(dispatcher({ tower: vi.fn(() => Promise.resolve(snapshot)) }))
    expect(await screen.findByText(/Decisión de despachador/)).toHaveTextContent('plan versión 2')
    expect(screen.getByText('Sin cambios necesarios')).toBeInTheDocument()
    expect(screen.getByText('No hay propuestas pendientes')).toBeInTheDocument()
  })

  it('compara dos versiones: métricas y secuencias que cambiaron', async () => {
    const v1 = makeSnapshot().plan
    const v2 = { ...v1, version: 2, base_version: 1, reason: 'Cierre vial: Calle 80', score: 520, created_by: 'despachador', comparison: [] }
    const client = dispatcher({ tower: vi.fn(() => Promise.resolve(makeSnapshot({ plan: v2, versions: [v1, v2] }))) })
    open(client)
    await userEvent.click(await screen.findByRole('button', { name: 'Comparar' }))
    const table = await screen.findByRole('table', { name: 'Comparación de dos versiones del plan' })
    expect(table).toHaveTextContent('Versión 1')
    expect(table).toHaveTextContent('Versión 2')
    expect(client.planVersion).toHaveBeenCalledWith(1)
    expect(client.planVersion).toHaveBeenCalledWith(2)
    expect(screen.getByText('Cambió')).toBeInTheDocument()
    expect(screen.getAllByText(/cambió de lugar/).length).toBeGreaterThan(0)
    expect(makePlanDetail(1).routes[0]?.stops.length).toBe(2)
  })

  it('con una sola versión explica cuándo habrá algo que comparar', async () => {
    open(dispatcher())
    expect(await screen.findByText(/Todavía hay una sola versión del plan/)).toBeInTheDocument()
  })

  it('muestra los dos motores del plan inicial y cuál se eligió', async () => {
    open(dispatcher())
    const table = await screen.findByRole('table', { name: 'Comparación de motores de ruteo' })
    expect(within(table).getByRole('row', { name: /OR-Tools/ })).toHaveTextContent('Elegido')
    expect(within(table).getByRole('row', { name: /Heurística/ })).toHaveTextContent('No')
  })
})
