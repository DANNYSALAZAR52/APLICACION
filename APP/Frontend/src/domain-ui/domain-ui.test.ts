import { describe, expect, it } from 'vitest'

import { makeDashboard } from '../test/fixtures'
import { csvCell, dashboardRows, toCsv } from './csv'
import {
  NOT_AVAILABLE,
  describeGap,
  formatDateTime,
  formatDecimal,
  formatInt,
  formatMoney,
  formatPercent,
  scenarioLabel,
  solverStatusLabel,
  vehicleLabel,
} from './format'
import { can, roleLabel } from './roles'

describe('formatos', () => {
  it('un dato ausente nunca se muestra como cero', () => {
    for (const value of [null, undefined, Number.NaN]) {
      expect(formatInt(value)).toBe(NOT_AVAILABLE)
      expect(formatDecimal(value)).toBe(NOT_AVAILABLE)
      expect(formatPercent(value)).toBe(NOT_AVAILABLE)
      expect(formatMoney(value)).toBe(NOT_AVAILABLE)
    }
    expect(formatInt(0)).toBe('0')
  })

  it('formatea fracciones como porcentaje con coma decimal', () => {
    expect(formatPercent(0.085)).toBe('8,5 %')
    expect(formatPercent(0)).toBe('0,0 %')
  })

  it('formatea decimales y moneda en es-CO', () => {
    expect(formatDecimal(1234.5)).toContain('1.234,5')
    expect(formatMoney(1500000)).toMatch(/1\.500\.000/)
  })

  it('muestra las fechas en hora de Bogotá con la zona explícita', () => {
    const text = formatDateTime('2026-10-13T13:00:00Z') // 13:00 UTC = 08:00 Bogotá
    expect(text).toContain('hora de Bogotá')
    expect(text).toMatch(/8:00/)
    expect(text).not.toMatch(/13:00/)
  })

  it('fecha ausente o inválida es "No disponible"', () => {
    expect(formatDateTime(null)).toBe(NOT_AVAILABLE)
    expect(formatDateTime('no-es-fecha')).toBe(NOT_AVAILABLE)
  })

  it('describe la brecha con texto (negativo = déficit)', () => {
    expect(describeGap(-3)).toEqual({ label: 'Déficit de 3', kind: 'deficit' })
    expect(describeGap(2)).toEqual({ label: 'Holgura de 2', kind: 'surplus' })
    expect(describeGap(0)).toEqual({ label: 'Equilibrada', kind: 'balanced' })
  })

  it('traduce etiquetas conocidas y deja pasar las desconocidas', () => {
    expect(vehicleLabel('doble_troque')).toBe('Doble troque')
    expect(vehicleLabel('semirremolque_x')).toBe('semirremolque x')
    expect(solverStatusLabel('feasible')).toContain('sin prueba de optimalidad')
    expect(scenarioLabel('base')).toBe('Base')
    expect(roleLabel('super_admin')).toBe('Superadministrador')
  })

  it('can() consulta la lista de permisos', () => {
    expect(can(['capacity:read'], 'capacity:read')).toBe(true)
    expect(can(['capacity:read'], 'tenants:manage')).toBe(false)
  })
})

describe('exportación CSV', () => {
  it.each(['=1+1', '+SUMA(A1)', '-2+3', '@cmd', '\t=x', '\r=x'])(
    'neutraliza la fórmula %j',
    (text) => {
      expect(csvCell(text).replace(/^"/, '').startsWith("'")).toBe(true)
    },
  )

  it('no altera números reales, ni siquiera negativos', () => {
    expect(csvCell(-3)).toBe('-3')
    expect(csvCell(12.5)).toBe('12.5')
  })

  it('ausente = celda vacía, no cero; infinito tampoco se exporta', () => {
    expect(csvCell(null)).toBe('')
    expect(csvCell(undefined)).toBe('')
    expect(csvCell(Number.POSITIVE_INFINITY)).toBe('')
  })

  it('escapa comas, comillas y saltos de línea', () => {
    expect(csvCell('a,b')).toBe('"a,b"')
    expect(csvCell('dijo "hola"')).toBe('"dijo ""hola"""')
    expect(csvCell('l1\nl2')).toBe('"l1\nl2"')
  })

  it('conserva acentos y usa CRLF', () => {
    expect(toCsv([['Año', 'Déficit'], [1, 2]])).toBe('Año,Déficit\r\n1,2')
  })

  it('el CSV del tablero empieza con la etiqueta de demostración y neutraliza texto de datos', () => {
    const data = makeDashboard()
    data.fleet[0] = { ...data.fleet[0]!, vehicle_type: '=HYPERLINK("http://malo")' }
    const csv = toCsv(dashboardRows(data))
    expect(csv.startsWith('DATOS DE DEMOSTRACIÓN')).toBe(true)
    expect(csv).not.toMatch(/(^|,)=HYPERLINK/m)
    expect(csv).toContain(`'=HYPERLINK`)
  })
})
