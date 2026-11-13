/**
 * Runs "now" and "what if" for the What if mode (M26.4). Both come from the browser's engine on one
 * seed, so they share random numbers and the difference is the decisions. A quick pass (2,000 runs)
 * answers within a fraction of a second; the full pass (10,000) replaces it. "Now" is cached per
 * source; a newer scenario discards the answers of an older one.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { LeagueFile } from '../../data/contract'
import { runSimulation } from '../../lib/league/client'
import { simInputFrom, type Source } from '../../lib/league/input'
import type { TeamOdds, Winner } from '../../lib/league/simulate'

export const RUNS = { quick: 2000, full: 10000 }
type Odds = Record<string, TeamOdds>
export type WhatIfState = { now: Odds | null; next: Odds | null; runs: number; busy: boolean }

export function useWhatIf(file: LeagueFile, source: Source, decided: Map<string, Winner>, enabled: boolean, runs = RUNS): WhatIfState {
  const input = useMemo(() => simInputFrom(file, source), [file, source])
  const seed = (file.seed ?? 1) >>> 0
  const key = [...decided].sort().map(([g, w]) => `${g}:${w}`).join(',')
  const nowCache = useRef(new Map<string, Promise<Odds>>())
  const [state, setState] = useState<WhatIfState>({ now: null, next: null, runs: 0, busy: false })
  const ticket = useRef(0)

  useEffect(() => {
    if (!enabled || !input) return
    const t = ++ticket.current
    const nowOf = (n: number) => {
      const k = `${source}|${n}|${file.as_of}`
      let p = nowCache.current.get(k)
      if (!p) nowCache.current.set(k, (p = runSimulation(input, n, seed)))
      return p
    }
    const nextOf = (n: number) => (decided.size === 0 ? nowOf(n) : runSimulation(input, n, seed, decided))
    setState((s) => ({ ...s, busy: true }))
    void (async () => {
      const [now1, next1] = await Promise.all([nowOf(runs.quick), nextOf(runs.quick)])
      if (t !== ticket.current) return
      setState({ now: now1, next: next1, runs: runs.quick, busy: true })
      const [now2, next2] = await Promise.all([nowOf(runs.full), nextOf(runs.full)])
      if (t !== ticket.current) return
      setState({ now: now2, next: next2, runs: runs.full, busy: false })
    })()
    // decided is captured through `key`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, input, key, seed, runs.quick, runs.full])

  return state
}
