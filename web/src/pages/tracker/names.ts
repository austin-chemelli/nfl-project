import type { Meta } from '../../data/contract'
import { SHORT } from '../../lib/models'
import { shortName } from './helpers'

/** Short label for a model id ("Analyst", "Market"). */
export function label(id: string): string {
  return SHORT[id] ?? id
}

/** Name for mid-sentence use: "the Analyst", "the ensemble", "the Elo reference". */
export function sentenceName(meta: Meta, id: string): string {
  const a = meta.approaches.find((x) => x.id === id)
  if (a) return shortName(a.name)
  if (id === 'ensemble') return 'the ensemble'
  return `the ${label(id)} line`
}

export const KEY_LINES = ['traditionalist', 'analyst', 'sharp', 'student', 'ensemble', 'market_baseline'] as const
export const REF_LINES = ['elo_v0', 'home_naive'] as const
