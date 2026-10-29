import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Card, Loaded, Page, Section } from '../components/ui'
import { useDiyMatrix, useMeta } from '../data/api'
import type { DiyMatrix, Meta } from '../data/contract'
import { decodeWeights, encodeWeights, evaluate, normalize, personaWeights, pointsFromWeights, weightsFor, type GroupWeights } from '../diy'
import { BudgetDonut } from './build/charts'
import { GroupSliders } from './build/Controls'
import { blankPoints, headingShares, rampColor } from './build/points'
import { Aging, Bets, ByContext, Calibration, Divergence, FitTowardYou, Headline, SeasonByseason, type Baseline } from './build/Results'

const HIDDEN_SEASONS = 3
const SETTLE_MS = 250
const PERSONAS = ['traditionalist', 'analyst', 'sharp'] as const

const personaName = (meta: Meta, matrix: DiyMatrix, id: string) => meta.approaches.find((a) => a.id === id)?.name ?? matrix.personas[id]?.name ?? id

export default function BuildPage() {
  const meta = useMeta()
  const matrix = useDiyMatrix()
  return (
    <Page
      title="Build your own approach"
      lede="Spend attention points on the things that matter to you and see how those beliefs would have done in every game since 2005. Overall confidence is not an input: calibration sets it from earlier seasons, so a loud set of weights gets no credit. Hover any group for what it measures."
    >
      <Loaded q={meta} what="the groups">
        {(m) => <Loaded q={matrix} what="the game matrix">{(mx) => <Builder meta={m} matrix={mx} />}</Loaded>}
      </Loaded>
    </Page>
  )
}

function Builder({ meta, matrix }: { meta: Meta; matrix: DiyMatrix }) {
  const [sp, setSp] = useSearchParams()
  const active = useMemo(() => matrix.groups.filter((g) => !matrix.inactive.includes(g)), [matrix])
  const groups = meta.groups.groups.filter((g) => matrix.groups.includes(g.id))
  const lastSeason = Math.max(...matrix.columns.season)
  const hiddenFrom = lastSeason - HIDDEN_SEASONS + 1
  const hide = sp.get('hide') === '1'
  const maxSeason = hide ? hiddenFrom - 1 : null

  // Points are shareable as ?w=, but a drag fires hundreds of input events and Safari/Firefox throw
  // past ~100 history.replaceState calls in a few seconds. So sliders move local state; the URL and
  // the (phone-expensive) evaluation follow once the drag pauses for SETTLE_MS.
  const wParam = sp.get('w')
  const fromUrl: GroupWeights = useMemo(() => {
    const d = wParam == null ? blankPoints(active) : decodeWeights(wParam)
    return Object.fromEntries(Object.entries(d).filter(([g]) => active.includes(g)))
  }, [wParam, active])
  const [points, setPoints] = useState(fromUrl)
  const [settled, setSettled] = useState(fromUrl)
  const written = useRef(wParam)
  useEffect(() => {
    // the URL changed from outside (back button, a pasted link): adopt it
    if (wParam === written.current) return
    written.current = wParam
    setPoints(fromUrl)
    setSettled(fromUrl)
  }, [wParam, fromUrl])

  const writeUrl = useCallback((next: GroupWeights, extra?: Record<string, string | null>) => {
    written.current = encodeWeights(next)
    setSp((prev) => {
      const n = new URLSearchParams(prev)
      n.set('w', written.current as string)
      for (const [k, v] of Object.entries(extra ?? {})) {
        if (v == null) n.delete(k)
        else n.set(k, v)
      }
      return n
    }, { replace: true })
  }, [setSp])
  useEffect(() => {
    if (points === settled) return
    const t = setTimeout(() => {
      setSettled(points)
      writeUrl(points)
    }, SETTLE_MS)
    return () => clearTimeout(t)
  }, [points, settled, writeUrl])
  /** Presets, fit-toward and the hide toggle apply at once. */
  const update = (next: GroupWeights, extra?: Record<string, string | null>) => {
    setPoints(next)
    setSettled(next)
    writeUrl(next, extra)
  }

  const { weights: liveWeights, total, capped } = useMemo(() => normalize(points), [points])
  const { weights } = useMemo(() => normalize(settled), [settled])
  const stale = points !== settled

  // Baselines don't depend on the sliders: computed once per window, after the first paint so the
  // controls appear immediately (the four evaluations cost ~100 ms together).
  const [done, setDone] = useState<{ key: string; list: Baseline[] } | null>(null)
  const baseKey = String(maxSeason)
  useEffect(() => {
    const t = setTimeout(() => {
      const list = [...PERSONAS, 'student' as const].map((id) => ({
        id, name: personaName(meta, matrix, id),
        ev: evaluate(id === 'student' ? weightsFor('student', matrix, {}) : personaWeights(id, matrix), matrix, { maxSeason }),
      }))
      setDone({ key: baseKey, list })
    }, 0)
    return () => clearTimeout(t)
  }, [matrix, meta, maxSeason, baseKey])
  const baselines: Baseline[] = done?.key === baseKey ? done.list : []
  const settledTotal = Object.values(weights).some((v) => v !== 0)
  const mine = useMemo(() => (settledTotal ? evaluate(weights, matrix, { maxSeason }) : null), [weights, matrix, maxSeason, settledTotal])

  const presets: { id: string; label: string; points: GroupWeights }[] = [
    { id: 'blank', label: 'Blank (equal weights)', points: blankPoints(active) },
    ...PERSONAS.map((id) => ({ id, label: personaName(meta, matrix, id), points: pointsFromWeights(personaWeights(id, matrix), active) })),
    { id: 'student', label: 'What the data says (The Student)', points: pointsFromWeights(matrix.student_fitted[String(lastSeason)]?.W ?? {}, active) },
  ]
  const shares = Object.fromEntries(Object.entries(liveWeights).map(([g, v]) => [g, 100 * Math.abs(v)]))
  const rows = headingShares(liveWeights, groups, meta.groups.headings)

  return (
    <>
      <Section title="Start from">
        <div className="flex flex-wrap gap-2">
          {presets.map((p) => (
            <button key={p.id} type="button" onClick={() => update(p.points)} className="rounded-md border border-line bg-surface-1 px-3 py-1.5 text-[14px] hover:bg-surface-2">
              {p.label}
            </button>
          ))}
        </div>
      </Section>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <GroupSliders
          groups={groups}
          headings={meta.groups.headings}
          points={points}
          shares={shares}
          inactive={matrix.inactive}
          onChange={(id, v) => setPoints((p) => ({ ...p, [id]: v }))}
        />
        <div className="lg:sticky lg:top-4 lg:self-start">
          <Card>
            <h2 className="text-lg font-semibold">Your budget</h2>
            <p className="text-[13px] text-ink-2">You spent {total.toFixed(0)} points; charts show them as shares of a 100-point budget, by heading.</p>
            {total === 0 ? (
              <p className="mt-3 text-[var(--warning)]" role="status">
                {Object.values(points).some((v) => v !== 0)
                  ? 'Market behavior alone can’t be scored: it is capped at 20% of a budget, so give another group some points.'
                  : 'Give at least one group some points.'}
              </p>
            ) : (
              <>
                {capped && (
                  <p className="mt-2 text-[13px] text-ink-2" role="status">
                    Market behavior is held at 20% of your budget (the most any approach may put on it), so its weight was reduced.
                  </p>
                )}
                <BudgetDonut rows={rows} />
                <ul className="mt-2 flex flex-col gap-1 text-[14px]">
                  {rows.map((r, i) => (
                    <li key={r.heading} className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-2">
                        <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: rampColor(i, rows.length) }} />
                        {r.heading}
                      </span>
                      <span className="tabular">{r.share.toFixed(0)}%</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>
        </div>
      </div>

      <Card>
        <p className="text-ink-2">
          Tuning weights until the backtest looks good is overfitting by eye: with about 270 games a season, some settings will look great by luck. Set your weights first, then reveal the recent seasons.
        </p>
        <label className="mt-2 inline-flex items-center gap-2">
          <input type="checkbox" checked={hide} onChange={(e) => update(points, { hide: e.target.checked ? '1' : null })} />
          Hide the last {HIDDEN_SEASONS} seasons ({hiddenFrom}-{lastSeason}) until I reveal them
        </label>
      </Card>

      {mine && (
        <div className={`flex flex-col gap-8 transition-opacity ${stale ? 'opacity-60' : ''}`} aria-busy={stale}>
          <Section title="How you would have done">
            <Headline mine={mine} baselines={baselines} />
          </Section>
          <SeasonByseason mine={mine} meta={meta} signed={settled} />
          <Aging mine={mine} />
          <Calibration mine={mine} />
          <ByContext mine={mine} />
          <Divergence mine={mine} />
          <Bets mine={mine} />
          <FitTowardYou
            weights={weights}
            matrix={matrix}
            maxSeason={maxSeason}
            meta={meta}
            onApply={(sh) => update(pointsFromWeights(sh, active))}
          />
        </div>
      )}
    </>
  )
}
