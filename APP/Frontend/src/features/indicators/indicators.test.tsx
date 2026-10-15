import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { App } from '../../app/App'
import { ApiError } from '../../api/errors'
import type { Role } from '../../api/types'
import { makeFakeClient } from '../../test/fixtures'

const open = (role: Role, overrides: Record<string, unknown> = {}) => {
  const client = makeFakeClient(role, overrides)
  render(
    <MemoryRouter initialEntries={['/indicadores']}>
      <App client={client} />
    </MemoryRouter>,
  )
  return client
}

describe('indicadores diarios', () => {
  it.each<Role>(['management', 'dispatcher'])('%s ve los indicadores', async (role) => {
    open(role)
    expect(await screen.findByRole('heading', { name: 'Indicadores diarios' })).toBeInTheDocument()
  })

  it.each<Role>(['driver', 'tenant_admin', 'super_admin'])('%s no tiene acceso y no se llama a la API', async (role) => {
    const client = open(role)
    expect(await screen.findByText('Permisos insuficientes')).toBeInTheDocument()
    expect(client.indicators).not.toHaveBeenCalled()
  })

  it('muestra puntualidad y OTIF como métricas separadas con su denominador', async () => {
    open('management')
    const live = (await screen.findByRole('heading', { name: /Hoy: proyección/ })).closest('section')
    expect(live).not.toBeNull()
    const card = within(live as HTMLElement)
    expect(card.getByText('Puntualidad')).toBeInTheDocument()
    expect(card.getByText('OTIF')).toBeInTheDocument()
    expect(card.getByText(/de 36 pedidos a tiempo/)).toBeInTheDocument()
    expect(screen.getByText(/comparten el mismo denominador/)).toBeInTheDocument()
  })

  it('rotula los escenarios como simulación con datos sintéticos', async () => {
    open('management')
    expect(await screen.findByText('Simulación')).toBeInTheDocument()
    expect(screen.getByText(/No son mediciones reales/)).toBeInTheDocument()
  })

  it('compara estático y dinámico con el mismo denominador y explica las tardías', async () => {
    open('management')
    const note = await screen.findByText(/Con los mismos eventos y el mismo denominador \(37 pedidos\)/)
    const box = note.closest('[role="status"]') as HTMLElement
    expect(box).toHaveTextContent('37 pedidos frente a 32 del plan estático (5 más)')
    expect(box).toHaveTextContent('Entregas tarde: 6 frente a 3')
    expect(box).toHaveTextContent('Hay más porque se entregan pedidos que el plan estático nunca atendió')
    expect(box).toHaveTextContent('5 versiones del plan y 1 reserva')
  })

  it('la tabla trae los cuatro escenarios y el gráfico tiene leyenda y equivalente en texto', async () => {
    open('dispatcher')
    const table = await screen.findByRole('table', { name: 'Indicadores por escenario' })
    expect(within(table).getAllByRole('row')).toHaveLength(5)
    expect(within(table).getByRole('row', { name: /ruteo dinámico · 10 %/ })).toHaveTextContent('3')
    const chart = screen.getByRole('img', { name: /Puntualidad y OTIF por escenario/ })
    expect(within(chart).getByRole('list', { name: 'Leyenda' })).toHaveTextContent('Puntualidad')
    expect(chart).toHaveTextContent('OTIF')
  })

  it('el OTIF con entregas incompletas queda por debajo de la puntualidad', async () => {
    open('management')
    const table = await screen.findByRole('table', { name: 'Indicadores por escenario' })
    const row = within(table).getByRole('row', { name: /10 % de entregas incompletas/ })
    const cells = within(row).getAllByRole('cell')
    expect(cells[cells.length - 4]).toHaveTextContent('83,8 %')
    expect(cells[cells.length - 3]).toHaveTextContent('75,7 %')
  })

  it('muestra las definiciones', async () => {
    open('management')
    expect(await screen.findByText(/Puntualidad = pedidos entregados dentro de su ventana/)).toBeInTheDocument()
  })

  it('mientras calcula avisa que la primera vez tarda', async () => {
    open('management', { indicators: vi.fn(() => new Promise<never>(() => undefined)) })
    const status = await screen.findByText(/la primera vez toma unos segundos/)
    expect(status.closest('[role="status"]')).not.toBeNull()
  })

  it('ante un error ofrece reintentar y se recupera', async () => {
    const indicators = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(500, 'ERROR_INTERNO', 'Ocurrió un error interno.'))
      .mockResolvedValue((await import('../../test/fixtures')).makeIndicators())
    open('management', { indicators })
    await userEvent.click(within(await screen.findByRole('alert')).getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { name: /Escenarios de ejemplo/ })).toBeInTheDocument()
  })
})
