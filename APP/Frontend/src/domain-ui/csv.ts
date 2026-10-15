import type { DashboardResponse } from '../api/types'
import { scenarioLabel, vehicleLabel } from './format'

const FORMULA_PREFIX = /^[=+\-@\t\r]/

/**
 * Neutraliza celdas que una hoja de cálculo interpretaría como fórmula (=, +, -, @): se
 * antepone una comilla simple. Los números reales (valores numéricos) no se alteran, así que un
 * valor negativo legítimo como -3 se exporta como número, no como texto.
 */
export function csvCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : ''
  const safe = FORMULA_PREFIX.test(value) ? `'${value}` : value
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe
}

export const toCsv = (rows: (string | number | null | undefined)[][]): string =>
  rows.map((row) => row.map(csvCell).join(',')).join('\r\n')

/** Filas del tablero para exportar (flota por método y proyecciones). */
export function dashboardRows(d: DashboardResponse): (string | number | null)[][] {
  const rows: (string | number | null)[][] = [
    [d.demo_label],
    ['Versión del algoritmo', d.algorithm_version],
    ['Fecha de cálculo (UTC)', d.run_at],
    [],
    ['Tipo', 'Flota actual', 'Balance', 'Lean', 'Monte Carlo P95', 'Mix óptimo', 'Propio vs tercero', 'Brecha'],
  ]
  for (const row of [...d.fleet, d.totals]) {
    rows.push([
      vehicleLabel(row.vehicle_type),
      row.current,
      row.balance,
      row.lean,
      row.monte_carlo_p95,
      row.mix,
      row.own_vs_third,
      row.gap,
    ])
  }
  rows.push([], ['Proyección', 'Año', 'Flota requerida total'])
  for (const projection of d.projections) {
    for (const year of projection.years) {
      rows.push([scenarioLabel(projection.scenario), year.year, year.total_required])
    }
  }
  return rows
}

/** Entrega al navegador un archivo ya generado (por ejemplo, un Excel del servidor). */
export function saveBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/** Descarga un CSV (con BOM para que Excel respete los acentos). */
export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob(['﻿', content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
