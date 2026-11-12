/**
 * Run a simulation in a Web Worker when the browser has one, else on the main thread after a tick
 * (tests, old browsers). One worker is shared; each call gets its own answer by id.
 */
import { simulateSeason, type SimInput, type TeamOdds, type Winner } from './simulate'

export type SimRequest = { id: number; input: SimInput; nRuns: number; seed: number; decided: [string, Winner][] }
export type SimResponse = { id: number; odds: Record<string, TeamOdds> }

let worker: Worker | null | undefined
let next = 1
const waiting = new Map<number, (odds: Record<string, TeamOdds>) => void>()

function getWorker(): Worker | null {
  if (worker !== undefined) return worker
  try {
    worker = typeof Worker === 'undefined' ? null : new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
  } catch {
    worker = null
  }
  worker?.addEventListener('message', (e: MessageEvent<SimResponse>) => {
    waiting.get(e.data.id)?.(e.data.odds)
    waiting.delete(e.data.id)
  })
  return worker
}

export function runSimulation(input: SimInput, nRuns: number, seed: number, decided: ReadonlyMap<string, Winner> = new Map()): Promise<Record<string, TeamOdds>> {
  const w = getWorker()
  if (!w) return new Promise((res) => setTimeout(() => res(simulateSeason(input, { nRuns, seed, decided })), 0))
  const id = next++
  return new Promise((res) => {
    waiting.set(id, res)
    const msg: SimRequest = { id, input, nRuns, seed, decided: [...decided] }
    w.postMessage(msg)
  })
}
