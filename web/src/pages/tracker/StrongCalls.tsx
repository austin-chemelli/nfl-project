import { Link } from 'react-router'
import { DataTable, ModelBadge, Section, TableScroll, td, th } from '../../components/ui'
import type { Tracker } from '../../data/contract'
import { APPROACHES } from '../../lib/models'
import { outcome } from '../game/differ'
import { divergenceSentence } from './helpers'
import { label } from './names'

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-US', { timeZone: 'America/New_York', weekday: 'short', month: 'short', day: 'numeric' }) : null)
const PC = (v: number | null) => (v == null ? '–' : `${Math.round(100 * v)}%`)
const gameLabel = (id: string) => id.split('_').slice(2).join(' @ ')

/** Every approach-game 10+ points from the market at a lock, with its reasons and how it went (ADR 0024). */
export function StrongCalls({ t }: { t: Tracker }) {
  const sc = t.strong_calls
  const since = day(sc?.first_lock ?? null)
  const context = APPROACHES.map((m) => t.divergence.find((r) => r.model_id === m && r.bucket === '10+')).filter((r) => r != null)
  return (
    <>
      <Section title="Strong calls" help="An approach 10+ points of win chance from the market at the lock. Recorded then with the groups pulling its way and the quarterback it assumed; graded after the game.">
        {!sc || sc.calls.length === 0 ? (
          <p className="text-ink-2">No strong calls recorded yet. The next lock records any it makes.</p>
        ) : (
          <>
            <p className="m-0 mb-3 text-ink-2">Live record since {since}. A handful of calls can&apos;t rank anything; the backtest has thousands.</p>
            <TableScroll>
              <table className="w-full border-collapse text-[14px]">
                <thead>
                  <tr>
                    <th className={th}>Approach</th>
                    <th className={th}>Calls</th>
                    <th className={th}>Right</th>
                    <th className={th}>Score, market&apos;s</th>
                    <th className={th}>Line moved toward</th>
                  </tr>
                </thead>
                <tbody>
                  {sc.record.filter((r) => r.n > 0).map((r) => (
                    <tr key={r.model_id}>
                      <td className={td}><ModelBadge modelId={r.model_id} /></td>
                      <td className={`${td} tabular`}>{r.n}</td>
                      <td className={`${td} tabular`}>{r.decided ? `${r.right} of ${r.decided}` : '–'}</td>
                      <td className={`${td} tabular`}>{r.log_loss != null && r.market_log_loss != null ? `${r.log_loss.toFixed(3)}, ${r.market_log_loss.toFixed(3)}` : '–'}</td>
                      <td className={`${td} tabular`}>{r.with_close ? `${r.moved_toward} of ${r.with_close}` : '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
            <ul className="mt-4 flex list-none flex-col gap-2 p-0">
              {sc.calls.map((c) => (
                <li key={`${c.game_id}-${c.model_id}-${c.lock_ts}`} className="border-b border-line pb-2">
                  <div className="flex flex-wrap items-baseline gap-x-2 text-[13px] text-ink-3">
                    <span>Week {c.week}</span>
                    <Link to={`/game/${c.game_id}`}>{gameLabel(c.game_id)}</Link>
                    <ModelBadge modelId={c.model_id} />
                    {outcome(c) && <span className={c.result === 'right' ? 'text-[var(--good)]' : c.result === 'wrong' ? 'text-[var(--critical)]' : ''}>{outcome(c)}</span>}
                  </div>
                  <p className="m-0 mt-0.5 text-ink">{c.sentence}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </Section>
      {context.length > 0 && (
        <Section title="The same gap in the backtest" help="Every game since 2005 where an approach was 10+ points from the closing market, scored as if locked.">
          <TableScroll>
            <table className="w-full border-collapse text-[14px]">
              <thead>
                <tr>
                  <th className={th}>Approach</th>
                  <th className={th}>Games 10+ pts off</th>
                  <th className={th}>Its side won</th>
                  <th className={th}>Market expected</th>
                </tr>
              </thead>
              <tbody>
                {context.map((r) => (
                  <tr key={r.model_id} title={divergenceSentence(r, label(r.model_id))}>
                    <td className={td}><ModelBadge modelId={r.model_id} /></td>
                    <td className={`${td} tabular`}>{r.n.toLocaleString('en-US')}</td>
                    <td className={`${td} tabular`}>{PC(r.lean_win_rate)}</td>
                    <td className={`${td} tabular`}>{PC(r.market_expected_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        </Section>
      )}
      <DataTable summary="What the score means">
        <p className="text-[13px] text-ink-2">The score is log loss on those games; lower is better, and the market&apos;s is beside it. Line moved toward counts calls where the spread moved toward the approach&apos;s side between the lock and kickoff.</p>
      </DataTable>
    </>
  )
}
