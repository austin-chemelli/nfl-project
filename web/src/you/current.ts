/**
 * The resolved custom line, as a React context (ADR 0034). Kept apart from the provider so the data
 * hooks (data/api.ts) can read it without importing the provider, which reads the data hooks.
 */
import { createContext, useContext } from 'react'
import type { GroupWeights } from '../diy'
import { APPROACHES, HEADLINE } from '../lib/models'
import type { LineParams } from './line'
import type { Migration, SavedApproach } from './store'

export const YOU = 'you'

export interface YouLine {
  name: string
  points: GroupWeights
  line: LineParams
  isDefault: boolean
  savedAt: string
  /** what changed since it was saved under an older registry (nothing when `changed` is false) */
  migration: Migration
}

export interface Lines {
  /** the saved line, ready to score; null when none is saved or it can't be scored yet */
  you: YouLine | null
  saved: SavedApproach | null
  /** none: nothing saved; ready; calibrating: refitting after a model update; unavailable: can't be scored with this data (no inputs, no group with history, or the refit failed) */
  status: 'none' | 'ready' | 'calibrating' | 'unavailable'
  /** the line pages lead with: the reader's own when saved as the default, else the Student */
  headline: string
  /** the approaches to list, "you" last when ready */
  approaches: readonly string[]
}

const SERVER = APPROACHES.filter((a) => a !== YOU)

export const NO_LINES: Lines = { you: null, saved: null, status: 'none', headline: HEADLINE, approaches: SERVER }

export const LinesContext = createContext<Lines>(NO_LINES)

/** The reader's lines: which approach leads, and their own line when saved. */
export const useLines = () => useContext(LinesContext)
/** The line the page leads with ('student', or 'you' when the reader made theirs the default). */
export const useHeadline = () => useContext(LinesContext).headline
