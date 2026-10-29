import { Help } from '../../components/Help'
import { Segmented } from '../../components/ui'
import type { Group } from '../../data/contract'
import { MARKET_GROUP_CAP, type GroupWeights } from '../../diy'

/** Grouped sliders: one block per heading, one row per group. Inactive groups are shown disabled with why. */
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
                const off = inactive.includes(g.id)
                const v = points[g.id] ?? 0
                const contrarian = v < 0
                return (
                  <div key={g.id} className={off ? 'opacity-60' : ''}>
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <label htmlFor={`pts-${g.id}`} className="font-medium">
                        <Help text={g.description}>{g.name}</Help>
                      </label>
                      <span className="tabular text-[13px] text-ink-2">
                        {off ? 'ignored' : `${contrarian ? '−' : ''}${(shares[g.id] ?? 0).toFixed(0)}% of your budget`}
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
                        disabled={off}
                        aria-valuetext={`${Math.abs(v)} points${contrarian ? ', contrarian' : ''}`}
                        onChange={(e) => onChange(g.id, (contrarian ? -1 : 1) * Number(e.target.value))}
                        className="h-2 min-w-0 flex-1 accent-[var(--accent)] disabled:cursor-not-allowed"
                      />
                      <span className="tabular w-8 text-right text-[13px]">{Math.abs(v)}</span>
                      <Segmented
                        label={`${g.name} direction`}
                        value={contrarian ? 'contrarian' : 'normal'}
                        options={[{ value: 'normal', label: 'Normal' }, { value: 'contrarian', label: 'Contrarian' }]}
                        onChange={(d) => !off && onChange(g.id, (d === 'contrarian' ? -1 : 1) * Math.abs(v))}
                      />
                    </div>
                    {off && <p className="mt-1 text-[13px] text-ink-3">No history for this group yet, so it can't be tested; its weight is ignored.</p>}
                    {g.id === 'market' && (
                      <p className="mt-1 text-[13px] text-ink-3">
                        The market's own prediction is what we compare against, so it is never an input. These signals only describe how the market is behaving. They are mostly live-only (no history), so they barely move the backtest. Capped at {Math.round(MARKET_GROUP_CAP * 100)}% of your budget.
                      </p>
                    )}
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
