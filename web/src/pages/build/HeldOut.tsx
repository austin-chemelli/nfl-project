/**
 * The honest check on in-sample tuning: hide the last seasons while you set the sliders, then
 * reveal how those weights did on games you never looked at, beside the Student and the market.
 */
import { useMemo, useState } from 'react'
import { Card } from '../../components/ui'
import type { DiyMatrix } from '../../data/contract'
import { evaluate, weightsFor, type Evaluation, type GroupWeights } from '../../diy'
import { llVsMarket } from '../../lib/format'

/** n-weighted log loss and market log loss over the seasons from `from` on. */
function heldOut(ev: Evaluation, from: number) {
  let n = 0, ll = 0, nm = 0, mll = 0
  for (const s of ev.seasons) {
    if (s.season < from) continue
    n += s.n
    ll += s.log_loss * s.n
    if (s.market_log_loss != null) { nm += s.n; mll += s.market_log_loss * s.n }
  }
  return n ? { n, ll: ll / n, mll: nm ? mll / nm : null } : null
}

export function HeldOut({ hide, hiddenFrom, lastSeason, weights, matrix, active, onHide }: {
  hide: boolean
  hiddenFrom: number
  lastSeason: number
  weights: GroupWeights
  matrix: DiyMatrix
  active: boolean
  onHide: (on: boolean) => void
}) {
  const [shown, setShown] = useState<string | null>(null)
  const key = JSON.stringify(weights)
  const result = useMemo(() => {
    if (shown !== key || !active) return null
    const mine = heldOut(evaluate(weights, matrix), hiddenFrom)
    const student = heldOut(evaluate(weightsFor('student', matrix, {}), matrix), hiddenFrom)
    return { mine, student }
  }, [shown, key, active, weights, matrix, hiddenFrom])
  const span = `${hiddenFrom}–${lastSeason}`
  return (
    <Card>
      <h2 className="text-lg font-semibold">Check it on seasons you haven't seen</h2>
      <p className="max-w-3xl text-ink-2">
        Moving sliders until the history below looks good is overfitting by eye: with about 270 games a season, some settings look great by luck. Hide the last 3 seasons, set your weights on the rest, then reveal how they did on the games you never looked at. Every game of this season is out of sample too: the history stops at {lastSeason}.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={hide} onChange={(e) => onHide(e.target.checked)} />
          Hide {span} from the results below
        </label>
        {hide && (
          <button type="button" disabled={!active} onClick={() => setShown(key)} className="rounded-md border border-line bg-surface-1 px-3 py-1 text-[14px] hover:bg-surface-2 disabled:opacity-50">
            Reveal {span} for these weights
          </button>
        )}
      </div>
      {hide && result?.mine && (
        <div className="mt-3 text-[14px]" role="status">
          <p className="m-0">
            On the {result.mine.n.toLocaleString('en-US')} held-out games ({span}), your log loss was {result.mine.mll != null ? llVsMarket(result.mine.ll, result.mine.mll) : result.mine.ll.toFixed(3)}
            {result.student && `; the Student's was ${result.student.ll.toFixed(3)}`}. Lower is better.
          </p>
          <p className="m-0 mt-1 text-[13px] text-ink-3">
            That is the fair test of the weights you set while they were hidden. Change the sliders after looking and it stops being one.
          </p>
        </div>
      )}
    </Card>
  )
}
