/** Model identity: order, colors (CSS variables from the palette), line style. */
export const APPROACHES = ['traditionalist', 'analyst', 'sharp', 'student'] as const
export type ApproachId = (typeof APPROACHES)[number]
export const LINES = [...APPROACHES, 'ensemble'] as const
export const REFERENCES = ['market_baseline', 'elo_v0', 'home_naive'] as const

export function colorVar(modelId: string): string {
  if ((APPROACHES as readonly string[]).includes(modelId) || modelId === 'ensemble') return `var(--series-${modelId})`
  if (modelId === 'market_baseline') return 'var(--series-market)'
  return 'var(--series-ref)'
}

export function dashArray(modelId: string): string | undefined {
  return modelId === 'elo_v0' || modelId === 'home_naive' || modelId === 'global' ? '4 3' : undefined
}

export const SHORT: Record<string, string> = {
  traditionalist: 'Traditionalist', analyst: 'Analyst', sharp: 'Sharp', student: 'Student',
  ensemble: 'Ensemble', market_baseline: 'Market', elo_v0: 'Elo', home_naive: 'Home 57%', global: 'Global fit',
}
