/** The named weight sets the Season view and the Build presets share (season.py `weights_for`). */
import type { MatrixInput } from './evaluate'
import { normalize, type GroupWeights, type Weights } from './weights'

export const SET_IDS = ['yours', 'traditionalist', 'analyst', 'sharp', 'student'] as const
export type SetId = (typeof SET_IDS)[number]
export const isSetId = (s: string | null | undefined): s is SetId => (SET_IDS as readonly string[]).includes(s ?? '')

/** Group weights (or per-season weights for the Student's yearly refits) for a weight set. */
export function weightsFor(setId: SetId, matrix: MatrixInput, yours: GroupWeights): Weights {
  if (setId === 'yours') return normalize(yours).weights
  if (setId === 'student') {
    return Object.fromEntries(Object.entries(matrix.student_fitted ?? {}).map(([s, v]) => [s, v.W]))
  }
  return { ...(matrix.personas?.[setId]?.W ?? {}) }
}

/** Signed weights -> signed attention points (largest magnitude = 100), active groups only. */
export function pointsFromWeights(w: GroupWeights, active: string[]): GroupWeights {
  const sel = active.filter((g) => g in w)
  const top = Math.max(0, ...sel.map((g) => Math.abs(w[g])))
  return Object.fromEntries(sel.map((g) => [g, top ? Math.round((100 * w[g]) / top) : 0]))
}

/** A persona's stated group weights. */
export const personaWeights = (id: string, matrix: MatrixInput): GroupWeights => ({ ...(matrix.personas?.[id]?.W ?? {}) })
