import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { App } from '../../app/App'
import { ApiError } from '../../api/errors'
import type { Role } from '../../api/types'
import { makeDashboard, makeFakeClient, makePatterns } from '../../test/fixtures'

const open = (role: Role, path = '/patrones', overrides: Record<string, unknown> = {}) => {
  const client = makeFakeClient(role, overrides)
  render(
    <MemoryRouter initialEntries={[path]}>
      <App client={client} />
    </MemoryRouter>,
  )
  return client
}

describe('acceso', () => {
  it.each<Role>(['management', 'dispatcher'])('%s ve la pantalla', async (role) => {
    open(role)
    expect(await screen.findByRole('heading', { name: 'Patrones detectados' })).toBeInTheDocument()
  })

  it.each<Role>(['driver', 'tenant_admin', 'super_admin'])(
    '%s no la ve y abrirla no consulta la API',
    async (role) => {
      const client = open(role)
      expect(await screen.findByText('Permisos insuficientes')).toBeInTheDocument()
      expect(client.patterns).not.toHaveBeenCalled()
    },
  )

  it('solo gerencia ve el botón de reentrenar', async () => {
    open('dispatcher')
    await screen.findByRole('heading', { name: 'Anomalías por cliente' })
    expect(screen.queryByRole('button', { name: 'Reentrenar modelos' })).toBeNull()
  })
})

describe('contenido', () => {
  it('declara que son datos sintéticos y muestra la procedencia de cada modelo', async () => {
    open('management')
    await screen.findByRole('heading', { name: 'Anomalías por cliente' })
    const note = document.querySelector('.notice')
    expect(note).toHaveTextContent('Datos sintéticos')
    expect(note).toHaveTextContent('DATOS SINTÉTICOS de demostración')
    const model = screen.getByRole('region', { name: 'Modelo: Pronóstico de demanda por corredor' })
    expect(model).toHaveTextContent('Versión 1')
    expect(model).toHaveTextContent('scikit-learn 1.9.1')
    expect(model).toHaveTextContent('aaaaaaaaaaaa…')
    expect(model).toHaveTextContent('MAE de la línea base ingenua')
    expect(model).toHaveTextContent('día de la semana: 84,0 %')
  })

  it('muestra el pronóstico con su intervalo y la línea base, y cambia de corredor', async () => {
    open('management')
    const table = await screen.findByRole('table', {
      name: 'Pronóstico de demanda del corredor Distribución urbana norte',
    })
    expect(within(table).getAllByRole('row')).toHaveLength(4)
    expect(table).toHaveTextContent('28,0')
    expect(screen.getByText(/35,5 t/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Corredor'), 'TRK-MED')
    const other = await screen.findByRole('table', {
      name: 'Pronóstico de demanda del corredor Bogotá–Medellín',
    })
    expect(other).toHaveTextContent('—') // sin línea base
    expect(screen.getByText(/sin datos/)).toBeInTheDocument()
  })

  it('las anomalías se explican con una frase y no afirman causalidad', async () => {
    open('management')
    const card = (await screen.findByRole('heading', { name: 'Anomalías por cliente' })).closest(
      'section',
    ) as HTMLElement
    expect(card).toHaveTextContent('los viernes entre las 10:00 y las 12:00')
    expect(card).toHaveTextContent('no demuestra la causa')
    expect(card).toHaveTextContent('Severidad 6,4')
  })

  it('el riesgo de retraso se presenta como estimación, no como certeza', async () => {
    open('management')
    const table = await screen.findByRole('table', { name: 'Riesgo de retraso por cliente' })
    expect(table).toHaveTextContent('74,9 %')
    expect(table).toHaveTextContent('08:00')
    expect(screen.getByText(/Es una estimación, no una certeza/)).toBeInTheDocument()
  })

  it('muestra los segmentos y los límites conocidos', async () => {
    open('management')
    const segment = await screen.findByRole('region', { name: 'Ventana estrecha' })
    expect(segment).toHaveTextContent('28 clientes')
    expect(screen.getByText(/no son categorías\s+objetivas/)).toBeInTheDocument()
    expect(screen.getByText(/se entrenaron con DATOS SINTÉTICOS/)).toBeInTheDocument()
  })
})

describe('estados', () => {
  it('mientras entrena muestra que puede tardar', async () => {
    open('management', '/patrones', { patterns: vi.fn(() => new Promise(() => undefined)) })
    expect(await screen.findByText(/la primera vez toma unos segundos/)).toBeInTheDocument()
  })

  it('un error se explica y permite reintentar', async () => {
    const patterns = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError(422, 'DATOS_INSUFICIENTES', 'Se necesitan al menos 28 días.'),
      )
      .mockResolvedValue(makePatterns())
    open('management', '/patrones', { patterns })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Se necesitan al menos 28 días.')
    await userEvent.click(within(alert).getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { name: 'Anomalías por cliente' })).toBeInTheDocument()
  })

  it('reentrenar llama al servidor y muestra el nuevo resultado', async () => {
    const client = open('management')
    await screen.findByRole('heading', { name: 'Anomalías por cliente' })
    await userEvent.click(screen.getByRole('button', { name: 'Reentrenar modelos' }))
    expect(client.retrainPatterns).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/Generado el/)).toBeInTheDocument()
  })

  it('un límite de reentrenamientos se muestra sin perder el resultado anterior', async () => {
    const retrainPatterns = vi.fn(() =>
      Promise.reject(
        new ApiError(429, 'LIMITE', 'Demasiados reentrenamientos seguidos; espere un momento.'),
      ),
    )
    open('management', '/patrones', { retrainPatterns })
    await screen.findByRole('heading', { name: 'Anomalías por cliente' })
    await userEvent.click(screen.getByRole('button', { name: 'Reentrenar modelos' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Demasiados reentrenamientos')
    expect(screen.getByRole('heading', { name: 'Anomalías por cliente' })).toBeInTheDocument()
  })
})

describe('tablero de capacidad', () => {
  it('con ML disponible muestra el pronóstico frente al percentil y la demanda de diseño', async () => {
    const dashboard = makeDashboard({
      ml_forecast_available: true,
      ml_forecast: [
        {
          corridor_code: 'URB-N',
          corridor_name: 'Distribución urbana norte',
          day: '2026-10-10',
          p50_t: 28.4,
          p90_t: 33.1,
          baseline_t: 30.2,
          historical_p90_t: 35.5,
        },
      ],
    })
    open('management', '/capacidad', { dashboard: vi.fn(() => Promise.resolve(dashboard)) })
    const table = await screen.findByRole('table', {
      name: 'Pronóstico ML frente al percentil histórico',
    })
    expect(table).toHaveTextContent('28,4')
    expect(table).toHaveTextContent('35,5')
    expect(screen.getByText(/disponible \(ver el panel inferior\)/)).toBeInTheDocument()
  })

  it('sin ML lo declara no disponible y no muestra el panel', async () => {
    open('management', '/capacidad')
    await screen.findByRole('heading', { name: 'Capacidad de flota' })
    expect(
      screen.queryByRole('table', { name: 'Pronóstico ML frente al percentil histórico' }),
    ).toBeNull()
    expect(screen.getByText(/Pronóstico de demanda con ML:/).parentElement).toHaveTextContent(
      'No disponible',
    )
  })
})
