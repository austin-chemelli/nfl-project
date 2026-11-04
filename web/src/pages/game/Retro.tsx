/**
 * Game retrospective (ADR 0016): what happened, how the forecasts did, and how much was luck.
 * Descriptive, not causal; every number comes from the RetroGame record.
 */
import { useState } from 'react'
import { FinePrint } from '../../components/FinePrint'
import { Help } from '../../components/Help'
import { Card, ModelBadge, Section, Segmented, TableScroll, td, th } from '../../components/ui'
import type { Efficiency, GradedPick, RetroGame, TeamRetro } from '../../data/contract'
import { DivergingBars, RangeRow, type RangeRowData } from '../../charts'
import { dash, fmtEff, pct, pts } from '../../lib/format'

export function Retro({ r }: { r: RetroGame }) {
  return (
    <div className="flex flex-col gap-8">
      <Headlines r={r} />
      <PlayedLike r={r} />
      <EfficiencySection r={r} />
      <LuckSection r={r} />
      <Forecasts r={r} />
      <Groups key={r.game_id} r={r} />
      <FinePrint>
        <p>The retrospective describes the game; it does not prove why it went that way. Every number is computed from play-by-play, and every sentence is filled in from those numbers.</p>
        <p>"Expected" comes from league rates in the same situations (2015–2025), and swings are priced in points by what such events are worth on average. Fumble recoveries, kicks and return plays are mostly luck; conversions, interceptions and penalties also reflect how the team played.</p>
        <p>In the forecast table, dimmed rows are references (the market and simple baselines), not entrants, and cannot be "best". One game is a very noisy score for any model.</p>
        <p>Group values overlap and do not add up to anything: read their order, not their size.</p>
      </FinePrint>
    </div>
  )
}

// ------------------------------------------------------------------------------------ headlines

function Headlines({ r }: { r: RetroGame }) {
  if (r.headlines.length === 0) return null
  return (
    <Section title="What happened" help="A few plain-language takeaways, each computed from the numbers below. They describe the game; they do not prove why it went that way.">
      <ul className="list-disc space-y-1.5 pl-5 text-[15px]">
        {r.headlines.map((h) => (
          <li key={h}>{h}</li>
        ))}
      </ul>
    </Section>
  )
}

// ------------------------------------------------------------------------------------ forecasts

const isRef = (p: GradedPick) => p.kind !== 'approach'

function Forecasts({ r }: { r: RetroGame }) {
  return (
    <Section
      title="How the forecasts did"
      help="Each model's pregame pick for this game, scored after the fact. The market and the simple reference lines are shown for comparison but cannot be 'best'."
    >
      <TableScroll>
        <table className="w-full border-collapse text-[14px]">
          <thead>
            <tr>
              <th className={th}>Forecast</th>
              <th className={th}>Pick</th>
              <th className={th}>Result</th>
              <th className={th}>
                <Help text="How surprised the forecast was by the result: lower is better, 0.693 is a coin flip. One game is a very noisy score.">Log loss</Help>
              </th>
              <th className={th}>
                <Help text="How far the forecast's point spread was from the actual margin, in points. Lower is better.">Spread error</Help>
              </th>
            </tr>
          </thead>
          <tbody>
            {r.predictions.map((p) => (
              <PickRow key={p.model_id} p={p} />
            ))}
          </tbody>
        </table>
      </TableScroll>
    </Section>
  )
}

function PickRow({ p }: { p: GradedPick }) {
  const ref = isRef(p)
  const cls = ref ? 'text-ink-3' : ''
  return (
    <tr className={p.best ? 'bg-surface-2' : undefined} data-best={p.best || undefined}>
      <td className={`${td} ${cls}`}>
        <span className={p.best ? 'font-semibold' : ''}>
          {ref ? p.label : <ModelBadge modelId={p.model_id} label={p.label} />}
        </span>
        {p.best && (
          <span className="ml-2 rounded border border-[var(--good)] px-1.5 py-px text-[11px] font-medium uppercase tracking-wide text-[var(--good)]">Best</span>
        )}
        {ref && <span className="ml-2 text-[11px] uppercase tracking-wide">reference</span>}
      </td>
      <td className={`${td} tabular whitespace-nowrap ${cls}`}>
        <span className="font-medium">{p.pick}</span> {pct(p.p_pick)}
      </td>
      <td className={`${td} ${cls}`}>
        {p.right == null ? dash : p.right ? <span aria-label="Right">✓ right</span> : <span aria-label="Wrong">✗ wrong</span>}
      </td>
      <td className={`${td} tabular ${cls}`}>{p.log_loss.toFixed(2)}</td>
      <td className={`${td} tabular ${cls}`}>{p.spread_error == null ? dash : `${p.spread_error.toFixed(1)} pts`}</td>
    </tr>
  )
}

// ------------------------------------------------------------------------------------ played like

function PlayedLike({ r }: { r: RetroGame }) {
  const pl = r.played_like
  const m = r.result.margin
  const winner = m > 0 ? r.home : m < 0 ? r.away : null
  const homeW = Math.round(100 * pl.p_home)
  const label = (team: string, p: number) => (
    <div className="flex flex-col">
      <span className="font-semibold">{team}</span>
      <span className="tabular text-ink-2">{pct(p)}</span>
      {winner === team && <span className="text-[12px] font-medium text-[var(--good)]">✓ won</span>}
    </div>
  )
  return (
    <Section
      title="Played like"
      help="How often a team wins when it plays as efficiently as each side did here, turnovers aside, according to league history. It asks whether the result matched the play."
    >
      <Card>
        <div className="flex items-start justify-between gap-3">
          {label(r.away, 1 - pl.p_home)}
          <div className="text-right">{label(r.home, pl.p_home)}</div>
        </div>
        <div
          className="mt-2 flex h-4 overflow-hidden rounded"
          role="img"
          aria-label={`Played like: ${r.home} ${homeW}%, ${r.away} ${100 - homeW}%`}
        >
          <div style={{ width: `${100 - homeW}%`, background: 'var(--text-muted)' }} />
          <div style={{ width: `${homeW}%`, background: 'var(--text-secondary)' }} />
        </div>
        <p className="mt-3 text-[14px] text-ink-2">{pl.sentence}</p>
      </Card>
    </Section>
  )
}

// ------------------------------------------------------------------------------------ efficiency

type Verdict = 'better' | 'worse' | 'same' | 'neutral'
// Pass rate over expected describes a style: more passing is neither better nor worse.
const isStyle = (e: Efficiency) => e.metric.endsWith('_proe')
function verdict(e: Efficiency): Verdict {
  if (isStyle(e)) return 'neutral'
  if (e.game == null || e.season == null || e.game === e.season) return 'same'
  return (e.game > e.season) === e.higher_is_better ? 'better' : 'worse'
}

const VERDICT_TEXT: Record<Verdict, string> = { better: 'Better than the season level.', worse: 'Worse than the season level.', same: 'Same as the season level.', neutral: 'A style measure: more passing is neither better nor worse.' }

function EfficiencySection({ r }: { r: RetroGame }) {
  const [side, setSide] = useState<'away' | 'home'>(r.result.margin > 0 ? 'home' : 'away')
  const t = r.teams[side]
  return (
    <Section
      title="Efficiency"
      help="How each unit played in this game next to its season to date (before this game). The band is the league's typical range (the middle 80% of teams this season), the tick the league average. The game dot is green when it beat the team's season level and red when it fell short."
    >
      <div className="mb-3">
        <Segmented
          label="Team"
          value={side}
          onChange={setSide}
          options={[{ value: 'away', label: r.away }, { value: 'home', label: r.home }]}
        />
      </div>
      <Card>
        <RangeLegend />
        <TeamEfficiency key={side} t={t} />
      </Card>
    </Section>
  )
}

const UNIT_ORDER = ['epa', 'pct', 'pp']

/** Keeps the longest labels to two lines in the narrow label column on phones. */
const shortLabel = (s: string) => s.replace(/^Opponent /, 'Opp. ').replace(/ over expected$/, ' over exp.')

/** A change vs the season level: EPA as is, rates in percentage points. */
function effDelta(d: number, unit: string): string {
  const sign = d < 0 ? '−' : '+'
  if (unit === 'epa') return `${sign}${Math.abs(d).toFixed(2)}`
  if (unit === 'pct') return `${sign}${(100 * Math.abs(d)).toFixed(1)} pts`
  return `${sign}${Math.abs(d).toFixed(1)} pts`
}

function RangeLegend() {
  const item = 'inline-flex items-center gap-1'
  return (
    <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2">
      <span className={item}><span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-[var(--text-secondary)]" /> Season to date</span>
      <span className={item}><span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--good)]" /> This game, better</span>
      <span className={item}><span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--critical)]" /> worse</span>
      <span className={item}><span className="inline-block h-3 w-0.5 bg-[var(--text-muted)]" /> League average</span>
      <span className={item}><span className="inline-block h-2.5 w-5 rounded-sm bg-[var(--div-mid)]" /> Typical range</span>
    </div>
  )
}

function TeamEfficiency({ t }: { t: TeamRetro }) {
  return (
    <>
      {(['off', 'def'] as const).map((side) => {
        const effs = t.efficiency.filter((e) => e.unit_side === side)
        const rank = (u: string) => (UNIT_ORDER.includes(u) ? UNIT_ORDER.indexOf(u) : UNIT_ORDER.length)
        const units = [...new Set(effs.map((e) => e.unit))].sort((a, b) => rank(a) - rank(b))
        return (
          <div key={side} className="mt-3 first:mt-0">
            <h4 className="text-[12px] font-medium uppercase tracking-wide text-ink-3">
              {t.team} {side === 'off' ? 'offense' : 'defense'}
            </h4>
            {units.map((u) => {
              const rows: RangeRowData[] = effs.filter((e) => e.unit === u).map((e) => {
                const v = verdict(e)
                return {
                  key: e.metric,
                  label: shortLabel(e.label),
                  game: e.game,
                  season: e.season,
                  league: e.league,
                  lo: e.league_lo,
                  hi: e.league_hi,
                  verdict: v,
                  title: `${e.label}: this game ${fmtEff(e.game, u)}, season to date ${fmtEff(e.season, u)} (${e.season_games} games), league ${fmtEff(e.league, u)}${e.league_lo != null && e.league_hi != null ? `, typical team ${fmtEff(e.league_lo, u)} to ${fmtEff(e.league_hi, u)}` : ''}. ${VERDICT_TEXT[v]}`,
                }
              })
              return <RangeRow key={u} rows={rows} format={(x) => fmtEff(x, u)} formatDelta={(d) => effDelta(d, u)} legend={false} labelWidth={150} />
            })}
          </div>
        )
      })}
    </>
  )
}

// ------------------------------------------------------------------------------------ luck

function LuckSection({ r }: { r: RetroGame }) {
  return (
    <Section
      title="Luck and swing plays"
      help="Events that swing games, each compared with what was expected (league rates in the same situations; for 3rd and 4th downs, adjusted for both teams' form this season) and priced in points by what such events are worth on average. Positive helped that team. Fumble recoveries, kicks and return plays are mostly luck; the ones marked partly skill also reflect how the team played."
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <TeamLuck t={r.teams.away} />
        <TeamLuck t={r.teams.home} />
      </div>
    </Section>
  )
}

function TeamLuck({ t }: { t: TeamRetro }) {
  const rows = [
    ...t.luck.map((f) => ({
      key: f.factor,
      label: f.partly_skill ? `${f.label} *` : f.label,
      value: f.swing_pts,
      title: f.sentence,
    })),
    { key: 'net', label: 'Net swing', value: t.luck_net, title: `Net swing for ${t.team}: ${pts(t.luck_net)}`, color: 'var(--text-secondary)' },
  ]
  const hasPartly = t.luck.some((f) => f.partly_skill)
  const pure = Math.round(t.luck.filter((f) => !f.partly_skill).reduce((a, f) => a + f.swing_pts, 0) * 10) / 10
  return (
    <Card>
      <h3 className="text-[15px] font-semibold">
        {t.team}: net swing <span className="tabular">{pts(t.luck_net)}</span>
      </h3>
      <p className="mb-2 text-[13px] text-ink-2">
        Pure luck (fumble recoveries, kicks, return plays): <span className="tabular font-medium text-ink">{pts(pure)}</span>
      </p>
      <DivergingBars
        rows={rows.map((x) => ({ ...x, label: x.key === 'net' ? <b>{x.label}</b> : x.label }))}
        leftLabel="hurt"
        rightLabel="helped"
        format={(v) => pts(v)}
        labelWidth={150}
      />
      <details className="mt-3 border-t border-line pt-2 text-[13px] text-ink-2">
        <summary className="cursor-pointer text-ink-3 hover:text-ink">What each swing was</summary>
      <ul className="mt-2 space-y-1.5">
        {t.luck.map((f) => (
          <li key={f.factor}>
            <span className="font-medium text-ink">{f.label}</span>
            {f.partly_skill && (
              <>
                {' '}
                <Help text="Part of this swing is skill (the team's own play), so it is not all luck.">
                  <span className="text-ink-3">partly skill</span>
                </Help>
              </>
            )}
            : {f.sentence}
          </li>
        ))}
      </ul>
      </details>
      {hasPartly && <p className="mt-2 text-[12px] text-ink-3">* partly skill, not pure luck.</p>}
    </Card>
  )
}

// ------------------------------------------------------------------------------------ groups

function Groups({ r }: { r: RetroGame }) {
  const ids = r.attribution.map((a) => a.model_id)
  const [sel, setSel] = useState(r.best_model && ids.includes(r.best_model) ? r.best_model : (ids[0] ?? ''))
  const a = r.attribution.find((x) => x.model_id === sel)
  if (!a) return null
  const rows = [...a.groups].sort((x, y) => y.value - x.value).map((g) => {
    const top = g.group === a.most_valuable
    return {
      key: g.group,
      label: top ? <b>★ {g.label}</b> : g.label,
      value: g.value,
      title: `${g.label}: ${g.value >= 0 ? 'helped' : 'hurt'} this forecast by ${Math.abs(g.value).toFixed(3)} log loss (${g.pp >= 0 ? '+' : '−'}${Math.abs(g.pp).toFixed(1)} pts of win chance toward ${r.home} when included).`,
    }
  })
  const topLabel = a.groups.find((g) => g.group === a.most_valuable)?.label
  return (
    <Section
      title="Which groups mattered"
      help="For each group of evidence: how much worse (or better) this forecast would have scored had that group been left out. Positive means the group helped the forecast on this game."
    >
      <div className="mb-3 overflow-x-auto">
        <Segmented
          label="Approach"
          value={sel}
          onChange={setSel}
          options={r.attribution.map((x) => ({ value: x.model_id, label: x.label.replace(/^The /, '') }))}
        />
      </div>
      <Card>
        {topLabel && (
          <p className="mb-2 text-[14px]">
            Most valuable for {a.label}: <b>{topLabel}</b>
          </p>
        )}
        <DivergingBars rows={rows} leftLabel="hurt the forecast" rightLabel="helped the forecast" format={(v) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(3)}`} labelWidth={150} />
      </Card>
    </Section>
  )
}
