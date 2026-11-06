/** Scatter of labelled points on two axes (M14.3 fills this in; the props below are the contract). */
import type { ReactNode } from 'react'

export type ScatterTone = 'conf-afc' | 'conf-nfc' | 'muted' | 'strong'

export type ScatterPoint = { key: string; label: string; x: number; y: number; tone?: ScatterTone }

export type ScatterAxis = {
  title: string
  /** Draw the lowest value at the right or top, so "better" points the same way on both axes. */
  flip?: boolean
  /** League mean: a dashed line. */
  mean?: number
  format: (v: number) => string
  /** Add "better →" or "↑ better" to the title. Only for a measure with a direction. */
  better?: boolean
}

export type ScatterProps = {
  points: ScatterPoint[]
  x: ScatterAxis
  y: ScatterAxis
  /** Corner captions: top left, top right, bottom left, bottom right. */
  quadrants?: [string, string, string, string]
  selected?: string | null
  onSelect?: (key: string) => void
  tip?: (key: string) => ReactNode
  /** Names the chart for assistive tech; the per-point list is added to it. */
  label: string
}

export function Scatter({ label }: ScatterProps) {
  return <svg role="img" aria-label={label} />
}
