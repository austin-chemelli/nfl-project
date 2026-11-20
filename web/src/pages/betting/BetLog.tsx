import { useMemo, useRef, useState } from 'react'
import { Section, StatTile, TableScroll, td, th } from '../../components/ui'
import type { BettingWeek } from '../../data/contract'
import { betClv, betProfit, deleteBet, downloadFile, exportName, gradeBet, importBets, summarize, toCsv, toJson, useBets } from '../../lib/betLog'
import { american, dash, dollars, pts, signedPct } from '../../lib/format'
import { BetForm } from './BetForm'
import { PaperRecord } from './PaperRecord'
import type { Draft } from './WeekCard'
import { clvText, closingMap, describeBet, gameOptions } from './weekFacts'

const RESULT: Record<string, string> = { open: 'Open', win: 'Won', loss: 'Lost', push: 'Push' }
const cls = (x: number | null) => (x == null || x === 0 ? '' : x > 0 ? 'text-[var(--good)]' : 'text-[var(--critical)]')
const money = (x: number) => `${x > 0 ? '+' : ''}${dollars(x, 2)}`

/** The private log: bets you placed, kept in this browser, graded against the closing lines. */
export function BetLog({ w, draft, draftKey, defaultStake, onAdded }: { w: BettingWeek; draft: Draft | null; draftKey: number; defaultStake: number | null; onAdded: () => void }) {
  const bets = useBets()
  const games = useMemo(() => closingMap(w), [w])
  const options = useMemo(() => gameOptions(w), [w])
  const sum = useMemo(() => summarize(bets, games), [bets, games])
  const rows = useMemo(() => [...bets].sort((a, b) => b.placed_at.localeCompare(a.placed_at)), [bets])
  const [note, setNote] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)

  async function onImport(f: File | undefined) {
    if (!f) return
    const r = importBets(await f.text())
    setNote(`Imported ${r.added} new ${r.added === 1 ? 'bet' : 'bets'}${r.skipped ? `; skipped ${r.skipped} that couldn’t be read` : ''}.`)
    if (file.current) file.current.value = ''
  }

  return (
    <div className="flex flex-col gap-8">
      <Section title="Log a bet" help="Record a bet you actually placed. It stays in this browser; nothing is sent anywhere.">
        <BetForm key={draftKey} games={options} draft={draft} defaultStake={defaultStake} onAdded={onAdded} />
      </Section>

      <Section title="Your results">
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <StatTile label="Bets" value={sum.bets} sub={sum.open ? `${sum.open} open` : undefined} />
            <StatTile label="Won–lost–push" value={`${sum.wins}–${sum.losses}–${sum.pushes}`} />
            <StatTile label="Staked" value={dollars(sum.staked, 2)} sub="settled bets" />
            <StatTile label="Profit" value={<span className={cls(sum.profit)}>{sum.bets - sum.open > 0 ? money(sum.profit) : dash}</span>} sub="after fees" />
            <StatTile label="Return" value={signedPct(sum.roi)} sub="profit per dollar staked" />
            <StatTile label="Closing-line value" value={sum.avgClvMl == null ? dash : pts(sum.avgClvMl)} sub="moneyline bets, vs the close" help="How your price compares with the closing fair chance, in points of win chance. Positive means you got a better price than the market settled on." />
          </div>
          <div>
            <h3 className="mb-1 text-[14px] font-semibold">The card&apos;s paper record at the locks</h3>
            <PaperRecord w={w} />
          </div>
        </div>
      </Section>

      <Section
        title="My bets"
        aside={
          <div className="flex flex-wrap gap-2 text-[13px]">
            <button type="button" onClick={() => downloadFile(exportName('csv'), 'text/csv', toCsv(bets))} disabled={bets.length === 0} className="rounded border border-line px-2 py-1 hover:bg-surface-2 disabled:opacity-50">
              Export CSV
            </button>
            <button type="button" onClick={() => downloadFile(exportName('json'), 'application/json', toJson(bets))} disabled={bets.length === 0} className="rounded border border-line px-2 py-1 hover:bg-surface-2 disabled:opacity-50">
              Export JSON
            </button>
            <label className="cursor-pointer rounded border border-line px-2 py-1 hover:bg-surface-2">
              Import JSON
              <input ref={file} type="file" accept="application/json,.json" className="sr-only" onChange={(e) => void onImport(e.target.files?.[0])} />
            </label>
          </div>
        }
      >
        {note && <p role="status" className="mb-2 text-[13px] text-ink-2">{note}</p>}
        {rows.length === 0 ? (
          <p className="text-[14px] text-ink-2">No bets logged yet.</p>
        ) : (
          <TableScroll>
            <table className="w-full text-[13px]">
              <thead>
                <tr>
                  <th className={th}>Game</th>
                  <th className={th}>Bet</th>
                  <th className={th}>Price</th>
                  <th className={th}>Stake</th>
                  <th className={th}>Venue</th>
                  <th className={th}>Result</th>
                  <th className={th}>Profit</th>
                  <th className={th}>CLV</th>
                  <th className={th}><span className="sr-only">Delete</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => {
                  const g = games.get(e.game_id)
                  const r = gradeBet(e, g)
                  const p = betProfit(e, r)
                  return (
                    <tr key={e.id}>
                      <td className={td}>{g ? `${g.away} @ ${g.home}` : e.game_id}</td>
                      <td className={td}>{describeBet(e, g)}</td>
                      <td className={`${td} tabular`}>{american(e.price)}</td>
                      <td className={`${td} tabular`}>{dollars(e.stake, 2)}</td>
                      <td className={td}>{e.venue || dash}</td>
                      <td className={td}>{RESULT[r]}</td>
                      <td className={`${td} tabular ${cls(p)}`}>{p == null ? dash : money(p)}</td>
                      <td className={`${td} tabular`}>{clvText(e, betClv(e, g))}</td>
                      <td className={td}>
                        <button type="button" onClick={() => deleteBet(e.id)} aria-label={`Delete ${describeBet(e, g)}`} className="rounded border border-line px-2 py-0.5 text-[12px] text-ink-2 hover:bg-surface-2">
                          Delete
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </TableScroll>
        )}
        <p className="mt-3 text-[13px] text-ink-3">Kept in this browser only; nothing is sent anywhere. Export a copy now and then.</p>
        <p className="text-[13px] text-ink-3">Keep a record of every trade for taxes.</p>
      </Section>
    </div>
  )
}
