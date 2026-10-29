import { Help } from '../components/Help'
import { Card, Loaded, Page, Section, DataTable, td, th } from '../components/ui'
import { useAudit, useMeta } from '../data/api'
import type { Audit, Meta } from '../data/contract'
import { groupName, helpFor } from '../lib/meta'
import { colorVar } from '../lib/models'
import { snapshotAgo, snapshotLabel, sortedShares, topNullRates } from './method/helpers'

const REPO = 'https://github.com/austin-chemelli/nfl-project'
const LOCKS = `${REPO}/tree/main/public/predictions`
const DOCS = `${REPO}/tree/main/docs`

const LEAKS: [string, string][] = [
  ['Quarterback starter leak.', 'The "projected starter" was the passer with the most dropbacks in the game, which leaked in-game injuries and benchings into about 3% of team-games. The Sharp briefly "beat the market" with an interval below zero. It now uses the game\'s first passer, with a regression test.'],
  ['Market miscalibration.', 'The remaining Sharp edge was exactly the error of a spread-only probability formula (the calibrated spread scored 0.6083, identical to the Sharp). The market line is now the vig-free moneyline probability, which removes that fake edge.'],
  ['Lookahead definition.', 'The "lookahead" feature (next opponent\'s strength) mostly measured "this opponent is weak", a copy of team strength, and fit with the wrong sign. It is now the next opponent\'s rating against an average team, and it comes out weak with an interval that includes zero.'],
  ['Team codes.', 'Play-by-play prints current team codes (LA, LAC, LV) for every season, while schedules use the historical ones (STL, SD, OAK). Plays for relocated teams were silently dropped from strength features until we joined on franchise codes.'],
  ['Kickoff times and old injury files.', '1999 schedules have no kickoff times (imputed by slot and flagged), and older injury files store the season as a decimal.'],
]

export default function MethodPage() {
  const meta = useMeta()
  const audit = useAudit()
  return (
    <Page
      title="Method and data"
      lede="A weekly NFL preview and prediction tool that is educational first and market-aware second. Here is how the numbers are made, what they cannot tell you, and the mistakes we found along the way."
    >
      <Loaded q={meta} what="method">
        {(m) => (
          <>
            <HowItWorks meta={m} />
            <Approaches meta={m} />
            <Locks />
            <Limits />
            <Leaks />
            <Freshness meta={m} audit={audit.data} auditError={audit.isError} />
            <NullAudit audit={audit.data} loading={audit.isPending} error={audit.isError} />
            <Credits />
          </>
        )}
      </Loaded>
    </Page>
  )
}

function HowItWorks({ meta }: { meta: Meta }) {
  return (
    <Section title="How it works">
      <div className="max-w-3xl space-y-3 text-[15px] leading-relaxed">
        <p>
          Several <strong>approaches</strong> ({meta.approaches.map((a) => a.name.replace(/^The /, '')).join(', ')}) weigh the same shared evidence differently, like different kinds of fans, plus an <strong>ensemble</strong> (their average). Each approach is <strong>one public line</strong>: the persona&apos;s own weights, lightly fitted to history and then calibrated, so the persona&apos;s biases survive. Models produce every number; an LLM, where used, only explains and is never allowed to introduce a statistic.
        </p>
        <p>
          <strong>The market is the reference, never an input</strong> (ADR 0013). The betting market&apos;s forecast (the spread and moneyline probability) is the line every approach is compared against, and no approach is allowed to read it. The Sharp reads market <em>behavior</em> (line moves, public betting share, disagreement between books) as a capped supplement, never the forecast itself. Feeding the market to a model and then crediting the model for matching the market was the mistake that made an early Sharp look as good as the market.
        </p>
        <p>
          <strong>How it is scored.</strong> Every line is scored in public against the market and a naive baseline on forecast quality (log loss, calibration), on odds-weighted paper bets, and on how often it was right when it disagreed with the market. Forecast quality comes first; betting is a lens.
        </p>
        <p>
          <strong>How numbers are shown.</strong> Probabilities and rates are percentages, differences are points of win probability, weights are shares of a 100-point attention budget, and team gaps are percentile ranks. Log loss is the scoring rule (lower is better, 0.693 is a coin flip), so it always appears next to the market&apos;s score. Differences under 0.005 are noise at this sample size.
        </p>
      </div>
    </Section>
  )
}

function Approaches({ meta }: { meta: Meta }) {
  return (
    <Section title="The approaches" help="Each approach is a character with its own biases, spreading a 100-point attention budget over the same groups of evidence.">
      <div className="grid gap-4 md:grid-cols-2">
        {meta.approaches.map((a) => {
          const shares = sortedShares(a.public_share)
          const top = shares[0]?.[1] ?? 1
          return (
            <Card key={a.id}>
              <h3 className="flex items-center gap-2 text-base font-semibold">
                <span aria-hidden className="inline-block h-3 w-3 rounded-full" style={{ background: colorVar(a.id) }} />
                {a.name}
              </h3>
              <p className="mt-1 text-[14px] text-ink-2">{a.blurb}</p>
              <p className="mt-2 text-[13px] text-ink-3">
                Leans on: {a.emphasis.map((g, i) => (
                  <span key={g}>
                    {i > 0 && ', '}
                    <Help text={helpFor(meta, g)}>{groupName(meta, g)}</Help>
                  </span>
                ))}
              </p>
              <p className="mt-1 text-[13px] text-ink-3">Home field: {a.home_field_why}.</p>
              <div className="mt-3 text-[12px] uppercase tracking-wide text-ink-3">Attention budget (public line, of 100)</div>
              <ul className="mt-1 space-y-1">
                {shares.map(([g, v]) => (
                  <li key={g} className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-2 text-[13px]">
                    <span className="truncate"><Help text={helpFor(meta, g)}>{groupName(meta, g)}</Help></span>
                    <span className="h-2 rounded-sm bg-surface-2" role="img" aria-label={`${groupName(meta, g)} ${v.toFixed(0)} of 100`}>
                      <span className="block h-2 rounded-sm" style={{ width: `${(100 * v) / top}%`, background: colorVar(a.id) }} />
                    </span>
                    <span className="tabular text-right text-ink-2">{v.toFixed(0)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )
        })}
      </div>
      <p className="mt-3 text-[13px] text-ink-2">Bars are scaled to each approach&apos;s largest group. Hover a group name for what it covers.</p>
    </Section>
  )
}

function Locks() {
  return (
    <Section title="How a lock works" help="A lock is the moment predictions are frozen before kickoff.">
      <div className="max-w-3xl space-y-3 text-[15px] leading-relaxed">
        <p>A <em>lock</em> freezes predictions before kickoff, twice a week (Thursday and Saturday). It:</p>
        <ol className="list-decimal space-y-1 pl-5">
          <li>Downloads the latest public data and an odds snapshot, then rebuilds every feature, each row stamped with the time it became known.</li>
          <li>Scores the games that have not kicked off, using models fitted only through last season: every approach, the ensemble, and the market, Elo and naive reference lines.</li>
          <li>Appends the predictions (they are never edited) and opens paper bets at the current odds.</li>
          <li>Writes a file with a checksum and commits it to git before kickoff, so the record cannot be quietly rewritten. A lock refuses games that have already kicked off, so the live record cannot be backfilled.</li>
        </ol>
        <p>
          The committed locks are public: <a className="text-accent underline" href={LOCKS} target="_blank" rel="noreferrer">browse the lock files on GitHub</a>.
        </p>
        <h3 className="pt-2 font-medium">Point-in-time rules</h3>
        <ul className="list-disc space-y-1 pl-5">
          <li>A prediction may only use data that was known <strong>before</strong> the lock time.</li>
          <li>Models used in season S are trained through season S−1 and frozen all year.</li>
          <li>Backfill scores (the 2005 to 2025 backtest, and weeks before the first live lock) use synthetic locks and frozen models. They are scored after the fact, so they are weaker evidence than live weeks.</li>
          <li>When a result looks too good, assume leakage before skill.</li>
        </ul>
      </div>
    </Section>
  )
}

function Limits() {
  return (
    <Section title="Honest limits">
      <ul className="max-w-3xl list-disc space-y-1 pl-5 text-[15px] leading-relaxed">
        <li>Football data is observational and samples are small: about 180 live games a season cannot rank models, and one season&apos;s paper profit is mostly noise.</li>
        <li>Markets are efficient. In the 2005 to 2025 backtest every approach trails the market by about 0.015 to 0.02 log loss, and when an approach disagrees with the market by 10+ points the market has been right more often.</li>
        <li>Persona weights are opinions. History-fitted weights describe the past, not the future.</li>
        <li>The Sharp&apos;s market-behavior inputs (line moves, public betting share) exist only for live games, so its backtest is thin.</li>
        <li>Narrative (news) features exist only for live games; there is no history to fit.</li>
      </ul>
    </Section>
  )
}

function Leaks() {
  return (
    <Section title="Leaks and bugs we found" help="Each of these made a model look better or worse than it was. They are listed so you can judge how much to trust the rest.">
      <ul className="max-w-3xl list-disc space-y-2 pl-5 text-[15px] leading-relaxed">
        {LEAKS.map(([h, b]) => (
          <li key={h}><strong>{h}</strong> {b}</li>
        ))}
      </ul>
    </Section>
  )
}

function Freshness({ meta, audit, auditError }: { meta: Meta; audit: Audit | undefined; auditError: boolean }) {
  const fresh = audit?.freshness && Object.keys(audit.freshness).length ? audit.freshness : meta.freshness
  const entries = Object.entries(fresh)
  return (
    <Section title="Data freshness" help="When each source was last downloaded; stale data would make a lock weaker.">
      {entries.length === 0 ? (
        <p className="text-ink-2">No freshness information is published yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full max-w-2xl text-[13px]">
            <thead>
              <tr>
                <th className={th}>Dataset</th>
                <th className={th}>Latest snapshot</th>
                <th className={th}>Age</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([k, v]) => (
                <tr key={k}>
                  <td className={td}>{k.replace(/_/g, ' ')}</td>
                  <td className={`${td} tabular`}>{snapshotLabel(v)}</td>
                  <td className={td}>{snapshotAgo(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[13px] text-ink-2">
        Site data generated {new Date(meta.generated_at).toLocaleString('en-US', { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' })} UTC.
        {auditError && ' (The audit file could not be loaded; showing the freshness from the main data file.)'}
      </p>
    </Section>
  )
}

function NullAudit({ audit, loading, error }: { audit: Audit | undefined; loading: boolean; error: boolean }) {
  const { shown, total } = topNullRates(audit?.null_rates)
  return (
    <Section title="Null-rate audit" help="How much of each column is missing, by season. Missing values are handled explicitly, not silently filled.">
      {loading ? (
        <p className="text-ink-2">Loading audit…</p>
      ) : error || !audit?.null_rates?.length ? (
        <p className="text-ink-2">No null-rate audit has been published yet.</p>
      ) : (
        <>
          <p className="text-[14px] text-ink-2">
            Share of missing values per column and season. Some columns are often empty (for example, FTN charting starts in 2022); features handle that explicitly.
          </p>
          <DataTable summary={`Show the ${shown.length} columns with the most missing values`}>
            <table className="w-full text-[13px]">
              <thead>
                <tr>
                  <th className={th}>Table</th>
                  <th className={th}>Column</th>
                  <th className={th}>Season</th>
                  <th className={th}>Missing</th>
                  <th className={th}>Rows</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={`${r.tbl}|${r.col}|${r.season}`}>
                    <td className={td}>{r.tbl}</td>
                    <td className={td}>{r.col}</td>
                    <td className={`${td} tabular`}>{r.season}</td>
                    <td className={`${td} tabular`}>{(100 * r.null_rate).toFixed(1)}%</td>
                    <td className={`${td} tabular`}>{r.n_rows.toLocaleString('en-US')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {total > shown.length && <p className="mt-2 text-ink-3">Top {shown.length} of {total} column-seasons with any missing values.</p>}
          </DataTable>
        </>
      )}
    </Section>
  )
}

function Credits() {
  return (
    <Section title="Docs, credits and license">
      <ul className="list-disc space-y-1 pl-5 text-[14px]">
        <li>Design docs, decisions (ADRs), tasks and runbook: <a className="text-accent underline" href={DOCS} target="_blank" rel="noreferrer">{DOCS}</a></li>
        <li>Data: <a className="text-accent underline" href="https://github.com/nflverse" target="_blank" rel="noreferrer">nflverse</a> (CC-BY 4.0), including FTN charting (CC-BY-SA 4.0); odds from <a className="text-accent underline" href="https://the-odds-api.com" target="_blank" rel="noreferrer">The Odds API</a>.</li>
        <li>Code is MIT-licensed; published derived data (predictions, features, scorecards) is CC-BY-SA 4.0.</li>
        <li>Fan-made, not affiliated with the NFL.</li>
      </ul>
    </Section>
  )
}
