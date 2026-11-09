import type { Meta } from '../../data/contract'
import { SHORT } from '../../lib/models'
import { shortName } from './helpers'

/** Short label for a model id ("Analyst", "Market"). */
export function label(id: string): string {
  return SHORT[id] ?? id
}

/** Name for mid-sentence use: "the Analyst", "the Elo line". */
export function sentenceName(meta: Meta, id: string): string {
  const a = meta.approaches.find((x) => x.id === id)
  if (a) return shortName(a.name)
  return `the ${label(id)} line`
}

export const KEY_LINES = ['traditionalist', 'analyst', 'sharp', 'student', 'student_v2', 'market_baseline'] as const
export const REF_LINES = ['elo_v0', 'home_naive'] as const
