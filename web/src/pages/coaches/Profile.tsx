import { Help } from '../../components/Help'
import type { Coaches, CoachSummary } from '../../data/contract'
import { consistencyText, metricsFor, pct0, pctWords } from './helpers'

/** A compact percentile strip: the fill runs from 0 to the percentile, a tick marks the league middle. */
export function PercentileBar({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <span className="text-ink-3">–</span>
  return (
    <span className="relative inline-block h-2 w-24 shrink-0 rounded-full bg-surface-2 align-middle" aria-hidden>
      <span className="absolute inset-y-0 left-0 rounded-full bg-[var(--accent)]" style={{ width: `${Math.max(2, 100 * pct)}%` }} />
      <span className="absolute -top-0.5 bottom-[-2px] left-1/2 w-px bg-[var(--text-muted)]" />
    </span>
  )
}

function MetricList({ summary, metrics, side, kind }: { summary: CoachSummary; metrics: Coaches['metrics']; side: 'off' | 'def'; kind: string }) {
  const rows = metricsFor(metrics, side, kind).filter(([k]) => summary.metrics[k]?.pct != null)
  if (!rows.length) return <p className="text-[13px] text-ink-3">Not enough charted plays yet.</p>
  return (
    <ul className="flex flex-col gap-2">
      {rows.map(([k, d]) => {
        const v = summary.metrics[k]
        return (
          <li key={k} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5 sm:grid-cols-[11rem_auto_1fr]">
            <span className="text-[13px] font-medium"><Help text={d.help}>{d.label}</Help></span>
            <span className="flex items-center gap-2 sm:order-none">
              <PercentileBar pct={v.pct} />
              <span className="tabular w-10 text-right text-[13px]">{pct0(v.pct)}</span>
            </span>
            <span className="col-span-2 text-[13px] text-ink-2 sm:col-span-1" title={`Recency-weighted over ${v.seasons} season(s)`}>
              {pctWords(v.pct, d)}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/** Prior profile / summary: history line, consistency, then percentile strips for scheme and result. */
export function Profile({ summary, metrics, side }: { summary: CoachSummary; metrics: Coaches['metrics']; side: 'off' | 'def' }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-ink-2">
        <span className="tabular"><Help text="Seasons in which he held a play-calling job with charted data. His history travels with him across teams.">{summary.n_seasons} seasons of history</Help></span>
        <span title={summary.teams.join(', ')}>{summary.n_teams} team{summary.n_teams === 1 ? '' : 's'}: {summary.teams.join(', ')}</span>
        <span>
          <Help text="How much his unit's percentile moved from season to season (average spread across the scheme measures). Needs 3+ seasons. 'Changes a lot' means his tendencies are a weak guide to this season.">
            Consistency: {consistencyText(summary.consistency)}
          </Help>
        </span>
      </div>
      <p className="text-[13px] text-ink-3">{summary.history}.</p>
      <div>
        <h4 className="mb-1.5 text-[13px] font-semibold">What he chooses <span className="font-normal text-ink-3">(percentile vs league, recent seasons weighted most; 50% = league middle)</span></h4>
        <MetricList summary={summary} metrics={metrics} side={side} kind="scheme" />
      </div>
      <div>
        <h4 className="mb-1.5 text-[13px] font-semibold">How it has gone <span className="font-normal text-ink-3">(EPA-based; for a defense, a high percentile means worse)</span></h4>
        <MetricList summary={summary} metrics={metrics} side={side} kind="result" />
      </div>
    </div>
  )
}
