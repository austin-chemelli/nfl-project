import { Help } from '../../components/Help'
import { Segmented } from '../../components/ui'
import type { Group } from '../../data/contract'
import { MARKET_GROUP_CAP, type GroupWeights } from '../../diy'

/** Live-only members: the narrative ratings and line movement exist only at a live lock (null in history). */
const liveOnly = (feature: string) => feature.startsWith('narrative.') || feature.startsWith('market.')

/** What a group holds, from the registry (meta.groups): the slider weighs all of it, history sets the mix. */
function Members({ group }: { group: Group }) {
  const main = group.members.filter((m) => !m.adv)
  const more = group.members.filter((m) => m.adv)
  const item = (m: Group['members'][number]) => (
    <li key={m.feature}>
      <Help text={m.description}>{m.label}</Help>
      {liveOnly(m.feature) && <span className="text-ink-3"> (live only)</span>}
    </li>
  )
  return (
    <details className="mt-1 text-[13px] text-ink-2">
      <summary className="cursor-pointer text-ink-3 hover:text-ink">What's in it ({group.members.length})</summary>
      <ul className="mt-1 ml-4 list-disc">
        {main.map(item)}
        {more.length > 0 && <li className="list-none text-ink-3">and in the detail: {more.map((m) => m.label).join(', ')}</li>}
      </ul>
      <p className="mt-1 text-ink-3">The slider weighs the whole group; how much each part counts inside it is fitted on past seasons, the same for every approach.</p>
    </details>
  )
}

/**
 * Grouped sliders: one block per heading, one row per group. `inactive` groups are live only: they
 * have no history, so they can't move the backtest, but they count in your line this season.
 */
export function GroupSliders({ groups, headings, points, shares, inactive, onChange }: {
  groups: Group[]
  headings: string[]
  points: GroupWeights
  /** group id -> share of the 100-point budget (after the market cap), unsigned */
  shares: GroupWeights
  inactive: string[]
  onChange: (id: string, signed: number) => void
}) {
  return (
    <div className="flex flex-col gap-5">
      {headings.map((h) => {
        const rows = groups.filter((g) => g.heading === h)
        if (!rows.length) return null
        return (
          <fieldset key={h} className="rounded-lg border border-line bg-surface-1 p-3 sm:p-4">
            <legend className="px-1 text-[13px] font-medium uppercase tracking-wide text-ink-3">{h}</legend>
            <div className="flex flex-col gap-4">
              {rows.map((g) => {
                const live = inactive.includes(g.id)
                const v = points[g.id] ?? 0
                const contrarian = v < 0
                return (
                  <div key={g.id}>
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <label htmlFor={`pts-${g.id}`} className="font-medium">
                        <Help text={g.description}>{g.name}</Help>
                      </label>
                      <span className="tabular text-[13px] text-ink-2">
                        {`${contrarian ? '−' : ''}${(shares[g.id] ?? 0).toFixed(0)}% of your budget`}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-3">
                      <input
                        id={`pts-${g.id}`}
                        type="range"
                        min={0}
                        max={100}
                        step={1}
                        value={Math.abs(v)}
                        aria-valuetext={`${Math.abs(v)} points${contrarian ? ', contrarian' : ''}`}
                        onChange={(e) => onChange(g.id, (contrarian ? -1 : 1) * Number(e.target.value))}
                        className="h-2 min-w-0 flex-1 accent-[var(--accent)] disabled:cursor-not-allowed"
                      />
                      <span className="tabular w-8 text-right text-[13px]">{Math.abs(v)}</span>
                      <Segmented
                        label={`${g.name} direction`}
                        value={contrarian ? 'contrarian' : 'normal'}
                        options={[{ value: 'normal', label: 'Normal' }, { value: 'contrarian', label: 'Contrarian' }]}
                        onChange={(d) => onChange(g.id, (d === 'contrarian' ? -1 : 1) * Math.abs(v))}
                      />
                    </div>
                    {live && g.id !== 'market' && <p className="mt-1 text-[13px] text-ink-3">Live only: no history, so it can't move the backtest below, but it counts in your line on this season's games.</p>}
                    {g.id === 'market' && (
                      <p className="mt-1 text-[13px] text-ink-3">
                        The market's own prediction is what everything is compared against, so it is never an input. This is how the line has moved since it opened, live only (no history), so it can't move the backtest but counts in your line this season. Capped at {Math.round(MARKET_GROUP_CAP * 100)}% of your budget.
                      </p>
                    )}
                    <Members group={g} />
                  </div>
                )
              })}
            </div>
          </fieldset>
        )
      })}
    </div>
  )
}
