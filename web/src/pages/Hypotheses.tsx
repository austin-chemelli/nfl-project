import { useSearchParams } from 'react-router'
import { FinePrint } from '../components/FinePrint'
import { Tabs } from '../components/Tabs'
import { Loaded, Page } from '../components/ui'
import { useHypotheses, useMeta } from '../data/api'
import { groupOf } from '../lib/meta'
import { Effects } from './hypotheses/Effects'
import { OverTime } from './hypotheses/OverTime'
import { resolveItem } from './hypotheses/helpers'

export default function HypothesesPage() {
  const q = useHypotheses()
  const meta = useMeta()
  const [params, setParams] = useSearchParams()
  const groupName = (id: string) => (meta.data ? groupOf(meta.data, id)?.name : undefined)

  return (
    <Page
      title="What history says"
      lede="What history says about each belief the approaches hold, one feature at a time."
    >
      <Loaded q={q} what="hypotheses">
        {(h) => (
          <>
            <p className="-mt-4 text-[13px] text-ink-3">
              {h.trained_seasons[0]}–{h.trained_seasons[h.trained_seasons.length - 1]}, {h.n_games.toLocaleString('en-US')} games. Generated {h.generated_at.slice(0, 16).replace('T', ' ')} UTC.
            </p>
            <p className="text-[13px] text-ink-3">
              Finished seasons only, so 2026 isn&apos;t here. It starts before the backtest because it studies past results and doesn&apos;t score forecasts; season-by-season scores start in 2005, as the backtest does.
            </p>
            <FinePrint label="How to read this, and the caveats">
              <ul className="list-disc space-y-1.5 pl-5">
                <li><b>Effect</b> = change in the home team's win probability, in points, when the feature is one standard deviation (SD) better for the home side than the away side, at a pick'em game. +1.0 means a 50% game becomes 51%.</li>
                <li><b>Range</b> = the 5th to 95th percentile over 200 refits that resample whole seasons (a 90% interval). The fit is shrunk toward zero, so every effect is modest. With this many features, a few will look good by chance (multiple comparisons).</li>
                <li><b>Observational, not causal.</b> Teams that rest more are not randomly assigned.</li>
                <li><b>Collinear features share credit.</b> Several strength measures say nearly the same thing, so credit splits between them. "On its own" shows the feature fit alone; the gap to "after the others" is the shared credit.</li>
                <li><b>Small samples for newer data.</b> Features that start in 2022 (FTN charting) have about a fifth of the games; their intervals are wide.</li>
                <li><b>Verdicts:</b> matters means the 90% range excludes zero and the effect is at least 0.75 points per +1 SD; weak means a small effect with a clear interval, or one bigger than its noise but not clear; no evidence means indistinguishable from zero.</li>
              </ul>
            </FinePrint>
            <Tabs
              label="Views"
              default="time"
              tabs={[
                {
                  id: 'time',
                  label: 'Over time',
                  content: (
                    <OverTime
                      h={h}
                      itemKey={resolveItem(h.by_season.items, params.get('item'))}
                      onPick={(key) => setParams((p) => { const n = new URLSearchParams(p); n.set('item', key); return n }, { replace: true })}
                    />
                  ),
                },
                { id: 'effects', label: 'Each feature', content: <Effects h={h} groupName={groupName} /> },
              ]}
            />
          </>
        )}
      </Loaded>
    </Page>
  )
}
