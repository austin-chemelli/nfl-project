import { useState } from 'react'
import { Link } from 'react-router'
import { Help } from '../../components/Help'
import { Card, DataTable, ModelBadge, Section, StatTile, td, th } from '../../components/ui'
import type { Meta } from '../../data/contract'
import { encodeWeights, fitToward, type Evaluation, type FitToward, type GroupWeights, type MatrixInput, type SeasonResult } from '../../diy'
import { llVsMarket, pct } from '../../lib/format'
import { groupName, helpFor } from '../../lib/meta'
import { ReliabilityChart, SeasonEdgeBars } from './charts'
import { gameLabel, signedPct } from './points'

export interface Baseline { id: string; name: string; ev: Evaluation }

const rel = (delta: number, market: number) => {
  const r = (100 * delta) / market
  return `${Math.abs(r).toFixed(1)}% ${r < 0 ? 'better' : 'worse'} than the market`
}

const LL_HELP = 'How far off the probabilities were, averaged over every game. It punishes confident misses hard. Lower is better; always saying 50% scores 0.693. Shown next to the market, which is the reference.'
const VS_HELP = "Percent better or worse than the betting market's own win probabilities (vig removed), measured in log loss."

/** Section 1: headline tiles, verdict, comparison table. */
export function Headline({ mine, baselines }: { mine: Evaluation; baselines: Baseline[] }) {
  const o = mine.overall
  const student = baselines.find((b) => b.id === 'student')
  const mkt = o.market_log_loss
  if (o.log_loss == null || mkt == null || o.delta == null) return <p className="text-ink-2">No scored games in this window.</p>
  const stu = student?.ev.overall
  let verdict: string
  if (o.d_hi < 0) verdict = 'Your weights beat the market over this window, and the 90% range excludes zero.'
  else if (o.d_lo > 0) verdict = 'Your weights trailed the market over this window, and the 90% range excludes zero.'
  else verdict = 'Your weights are statistically indistinguishable from the market over this window.'
  const ahead = stu?.log_loss != null ? (o.log_loss < stu.log_loss ? 'ahead of' : 'behind') : null
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="Against the market" help={VS_HELP} value={rel(o.delta, mkt).replace(' than the market', '')} sub={llVsMarket(o.log_loss, mkt)} />
        <StatTile label="Picks right" help="A pick is the team you gave more than a 50% chance. The market's own favorite is the comparison." value={pct(o.accuracy, 1)} sub={`market ${pct(o.market_accuracy, 1)}`} />
        <StatTile
          label="Against The Student"
          help="The Student weights every group equally to start and learns only from past results, refitting each year. Beating it means your opinions added something the data alone did not."
          value={stu?.log_loss != null ? `${Math.abs(o.log_loss - stu.log_loss).toFixed(3)} ${o.log_loss < stu.log_loss ? 'better' : 'worse'}` : '–'}
          sub={stu?.log_loss != null && stu.market_log_loss != null ? `Student: ${llVsMarket(stu.log_loss, stu.market_log_loss)}` : undefined}
        />
      </div>
      <p className="mt-3 max-w-3xl">
        {verdict}
        {ahead && ` You are ${ahead} the data-only Student, though ${o.n.toLocaleString('en-US')} games over ${o.seasons} seasons cannot rank close approaches.`}
      </p>
      <p className="mt-1 text-[13px] text-ink-3">
        Your log loss has a 90% range of {o.ll_lo.toFixed(3)} to {o.ll_hi.toFixed(3)} (resampling whole seasons).
        {mine.first_season_in_sample && ' The first season was calibrated on itself.'}
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[34rem] border-collapse text-[14px]">
          <thead>
            <tr>
              <th className={th}>Approach</th>
              <th className={th}><Help text={LL_HELP}>Log loss</Help></th>
              <th className={th}><Help text={VS_HELP}>Against the market</Help></th>
              <th className={th}>Picks right</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className={`${td} font-medium`}>Yours</td>
              <td className={`${td} tabular`}>{llVsMarket(o.log_loss, mkt)}</td>
              <td className={td}>{rel(o.delta, mkt)}</td>
              <td className={`${td} tabular`}>{pct(o.accuracy, 1)}</td>
            </tr>
            {baselines.map((b) => {
              const bo = b.ev.overall
              return (
                <tr key={b.id}>
                  <td className={td}><ModelBadge modelId={b.id} label={b.name} /></td>
                  <td className={`${td} tabular`}>{bo.log_loss != null && bo.market_log_loss != null ? llVsMarket(bo.log_loss, bo.market_log_loss) : '–'}</td>
                  <td className={td}>{bo.delta != null && bo.market_log_loss != null ? rel(bo.delta, bo.market_log_loss) : '–'}</td>
                  <td className={`${td} tabular`}>{pct(bo.accuracy, 1)}</td>
                </tr>
              )
            })}
            <tr>
              <td className={td}><ModelBadge modelId="market_baseline" label="The market (vig removed)" /></td>
              <td className={`${td} tabular`}>{mkt.toFixed(3)}</td>
              <td className={`${td} text-ink-3`}>the reference</td>
              <td className={`${td} tabular`}>{pct(o.market_accuracy, 1)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[13px] text-ink-3">The approaches here use their stated weights, so their numbers differ slightly from the tracker, where the public lines are lightly fitted to history.</p>
    </>
  )
}

function KeyGames({ s, meta }: { s: SeasonResult; meta: Meta }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] border-collapse text-[13px]">
        <thead>
          <tr>
            <th className={th}>Game</th>
            <th className={th}>Home won</th>
            <th className={th}>Your home win</th>
            <th className={th}>Market</th>
            <th className={th}><Help text="How much more this game hurt your log loss than the market's. Higher means you were further off than the market.">Cost vs market</Help></th>
            <th className={th}><Help text="The group of beliefs that moved your probability the most.">Biggest push</Help></th>
          </tr>
        </thead>
        <tbody>
          {s.key_games?.map((k) => (
            <tr key={k.game_id}>
              <td className={td}>{gameLabel(k.game_id)}</td>
              <td className={td}>{k.home_won ? 'yes' : 'no'}</td>
              <td className={`${td} tabular`}>{pct(k.p, 1)}</td>
              <td className={`${td} tabular`}>{pct(k.market_p, 1)}</td>
              <td className={`${td} tabular`}>{k.delta.toFixed(3)}</td>
              <td className={td}>
                <Help text={helpFor(meta, k.group)}>{groupName(meta, k.group)}</Help> (toward {k.group_logit > 0 ? 'the home team' : 'the road team'})
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Section 2: season by season, with the best and worst seasons opened up. */
export function SeasonByseason({ mine, meta, signed }: { mine: Evaluation; meta: Meta; signed: GroupWeights }) {
  const rows = mine.seasons.filter((r) => r.delta != null).map((r) => ({ season: r.season, edge: -(r.delta as number) }))
  const wins = rows.filter((r) => r.edge > 0).length
  const link = (season: number) => `/season/${season}?set=yours&w=${encodeWeights(signed)}`
  return (
    <Section title="Season by season" help="Bars above zero are seasons where you were closer to what happened than the market was.">
      {rows.length ? (
        <>
          <SeasonEdgeBars rows={rows} />
          <p className="mt-2 text-[13px] text-ink-2">
            Blue: you beat the market that season. Red: the market beat you. You were ahead in {wins} of {rows.length} seasons. Bars are the market's log loss minus yours, per game.
          </p>
          <DataTable>
            <table className="w-full border-collapse text-[13px]">
              <thead><tr><th className={th}>Season</th><th className={th}>Games</th><th className={th}>Edge vs market (per game)</th></tr></thead>
              <tbody>{rows.map((r) => <tr key={r.season}><td className={td}>{r.season}</td><td className={td}>{mine.seasons.find((s) => s.season === r.season)?.n}</td><td className={`${td} tabular`}>{r.edge >= 0 ? '+' : '−'}{Math.abs(r.edge).toFixed(4)}</td></tr>)}</tbody>
            </table>
          </DataTable>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {([['Best seasons', mine.best], ['Worst seasons', mine.worst]] as const).map(([title, list]) => (
              <details key={title} className="rounded-lg border border-line bg-surface-1 p-3">
                <summary className="cursor-pointer font-medium">{title}</summary>
                <div className="mt-3 flex flex-col gap-4">
                  {list.map((r) => {
                    const edge = -(r.delta as number)
                    const mk = r.market_log_loss as number
                    return (
                      <div key={r.season}>
                        <p>
                          <strong>{r.season}</strong>: {Math.abs((100 * edge) / mk).toFixed(1)}% {edge > 0 ? 'better' : 'worse'} than the market over {r.n} games.{' '}
                          <Link className="text-accent underline" to={link(r.season)}>See every {r.season} game with your weights</Link>
                        </p>
                        <KeyGames s={r} meta={meta} />
                      </div>
                    )
                  })}
                </div>
              </details>
            ))}
          </div>
        </>
      ) : <p className="text-ink-2">No market lines in this window.</p>}
    </Section>
  )
}

export function Aging({ mine }: { mine: Evaluation }) {
  return (
    <Section title="Did your weights age?" help="Whether your edge over the market has been shrinking or growing over the seasons.">
      <p className="max-w-3xl">{mine.aging.sentence}</p>
    </Section>
  )
}

export function Calibration({ mine }: { mine: Evaluation }) {
  const rows = mine.reliability.map((r) => ({ mean: 100 * r.mean_p, hit: 100 * r.hit_rate, ideal: 100 * r.mean_p, n: r.n }))
  return (
    <Section title="Are your percentages honest?" help="Games grouped by the home win chance you gave; the line shows how often the home team really won. On the dashed diagonal means well calibrated. Calibration is fitted on earlier seasons only.">
      <ReliabilityChart rows={rows} />
      <DataTable>
        <table className="w-full border-collapse text-[13px]">
          <thead><tr><th className={th}>You said (home win)</th><th className={th}>Games</th><th className={th}>Home team won</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.mean}><td className={`${td} tabular`}>{r.mean.toFixed(0)}%</td><td className={td}>{r.n}</td><td className={`${td} tabular`}>{r.hit.toFixed(0)}%</td></tr>)}</tbody>
        </table>
      </DataTable>
    </Section>
  )
}

export function ByContext({ mine }: { mine: Evaluation }) {
  return (
    <Section title="By game type">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem] border-collapse text-[14px]">
          <thead><tr><th className={th}>Kind</th><th className={th}>Bucket</th><th className={th}>Games</th><th className={th}><Help text="The market's log loss minus yours, per game. Positive = better than the market.">Edge vs market</Help></th><th className={th}>± s.e.</th></tr></thead>
          <tbody>
            {mine.by_context.map((b) => (
              <tr key={`${b.group}-${b.bucket}`}>
                <td className={td}>{b.group}</td><td className={td}>{b.bucket}</td><td className={`${td} tabular`}>{b.n}</td>
                <td className={`${td} tabular`}>{b.delta == null ? '–' : `${-b.delta >= 0 ? '+' : '−'}${Math.abs(b.delta).toFixed(4)}`}</td>
                <td className={`${td} tabular`}>{b.delta_se == null ? '–' : b.delta_se.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[13px] text-ink-3">Positive edge = better than the market. Close games and blowouts are labeled by outcome, which nobody knows in advance.</p>
    </Section>
  )
}

export function Divergence({ mine }: { mine: Evaluation }) {
  return (
    <Section title="When you disagree with the market" help="Games grouped by how far your home win chance was from the market's, in points of win probability.">
      <ul className="flex max-w-3xl flex-col gap-1.5">
        {mine.divergence.map((d) => (
          <li key={d.bucket}>
            {d.n === 0 || d.lean_win_rate == null || d.market_expected_rate == null
              ? <>Gap of {d.bucket} pts: no games.</>
              : <>Gap of <strong>{d.bucket} pts</strong> ({d.n.toLocaleString('en-US')} games): the side you leaned to won <strong>{pct(d.lean_win_rate)}</strong>; the market expected {pct(d.market_expected_rate)}.</>}
          </li>
        ))}
      </ul>
    </Section>
  )
}

export function Bets({ mine }: { mine: Evaluation }) {
  const b = mine.bets
  return (
    <Section title="Paper bets (noisy)">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="Units" help="Profit in bet sizes: each bet risks 1 unit." value={`${b.units >= 0 ? '+' : '−'}${Math.abs(b.units).toFixed(1)}`} />
        <StatTile label="ROI" help="Profit as a share of the money risked." value={b.roi == null ? '–' : signedPct(100 * b.roi, 1)} />
        <StatTile label="Record" help="Bets won and lost." value={`${b.wins}-${b.losses}`} />
      </div>
      <p className="mt-2 text-[13px] text-ink-3">1 unit on the moneyline whenever you differ from the vig-free market by more than 5 points. A few hundred bets cannot separate skill from luck.</p>
    </Section>
  )
}

/** "Fit toward you": a ridge fit that nudges your weights toward what history says. */
export function FitTowardYou({ weights, matrix, maxSeason, meta, onApply }: {
  weights: GroupWeights
  matrix: MatrixInput
  maxSeason: number | null
  meta: Meta
  onApply: (shares: GroupWeights) => void
}) {
  const [fit, setFit] = useState<{ key: string; result: FitToward } | null>(null)
  const key = `${encodeWeights(weights)}|${maxSeason}`
  const shown = fit?.key === key ? fit.result : null
  return (
    <Section title="What history would do to your weights" help="A ridge fit over all scored seasons, shrunk toward your weights, so it moves them only as far as the data insists. Hindsight by design.">
      <button type="button" onClick={() => setFit({ key, result: fitToward(weights, matrix, { maxSeason }) })} className="rounded-md border border-line bg-surface-2 px-3 py-1.5 text-[14px] font-medium hover:bg-surface-1">
        Fit toward you
      </button>
      {shown && (
        <Card className="mt-3">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[22rem] border-collapse text-[14px]">
              <thead><tr><th className={th}>Group</th><th className={th}>You</th><th className={th}>History</th><th className={th}>Change</th></tr></thead>
              <tbody>
                {Object.keys(shown.shares)
                  .map((g) => ({ g, you: shown.user_shares[g], hist: shown.shares[g] }))
                  .sort((a, b) => Math.abs(b.hist - b.you) - Math.abs(a.hist - a.you))
                  .map((r) => (
                    <tr key={r.g}>
                      <td className={td}><Help text={helpFor(meta, r.g)}>{groupName(meta, r.g)}</Help></td>
                      <td className={`${td} tabular`}>{signedPct(r.you, 1)}</td>
                      <td className={`${td} tabular`}>{signedPct(r.hist, 1)}</td>
                      <td className={`${td} tabular`}>{r.hist - r.you >= 0 ? '+' : '−'}{Math.abs(r.hist - r.you).toFixed(1)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[13px] text-ink-3">Signed shares of a 100-point budget after a ridge fit toward your weights over all scored seasons (hindsight by design: this is what the data would nudge you toward).</p>
          <button type="button" onClick={() => onApply(shown.shares)} className="mt-2 rounded-md border border-line px-3 py-1.5 text-[14px] hover:bg-surface-2">
            Use these weights
          </button>
        </Card>
      )}
    </Section>
  )
}
