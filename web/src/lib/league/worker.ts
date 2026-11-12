/// <reference lib="webworker" />
/** Runs the season simulation off the main thread (M26.3). Message in: SimRequest; out: SimResponse. */
import { simulateSeason } from './simulate'
import type { SimRequest, SimResponse } from './client'

self.onmessage = (e: MessageEvent<SimRequest>) => {
  const { id, input, nRuns, seed, decided } = e.data
  const odds = simulateSeason(input, { nRuns, seed, decided: new Map(decided) })
  const msg: SimResponse = { id, odds }
  self.postMessage(msg)
}
