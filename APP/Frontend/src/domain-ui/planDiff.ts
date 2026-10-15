// Diferencia entre dos secuencias de paradas (solo presentación).

export type SeqChange = 'same' | 'moved' | 'new' | 'removed'

export interface SeqItem {
  item: string
  change: SeqChange
}

/**
 * Muestra la secuencia nueva marcando lo que cambió de lugar o es nuevo, y al final lo que ya
 * no está. Una parada "cambió de lugar" si su posición relativa entre las paradas comunes cambió.
 */
export function diffSequences(before: readonly string[], after: readonly string[]): SeqItem[] {
  const common = after.filter((x) => before.includes(x))
  const beforeCommon = before.filter((x) => after.includes(x))
  const result: SeqItem[] = after.map((item) => {
    if (!before.includes(item)) return { item, change: 'new' }
    return { item, change: common.indexOf(item) === beforeCommon.indexOf(item) ? 'same' : 'moved' }
  })
  for (const item of before) if (!after.includes(item)) result.push({ item, change: 'removed' })
  return result
}
