import { BookStrip, type StripDot } from '../../charts'
import { Section, TableScroll, td, th } from '../../components/ui'
import type { BookLine, Game } from '../../data/contract'
import { pct, spreadLabel } from '../../lib/format'
import { bookName, booksRange, booksSentence, disagrees, hasBooks, price } from './books'
import { etStamp, fmtPts } from './line'

/** Each sportsbook's line at our latest snapshot before kickoff, and where they disagree (ADR 0024, M20.13). */
export function Books({ g }: { g: Game }) {
  const b = g.books
  if (!b || !hasBooks(g)) return null
  const sides = { above: g.home, below: g.away, aboveColor: 'var(--team-home)', belowColor: 'var(--team-away)' }
  const dots = (k: 'spread_home' | 'total', p: (r: BookLine) => string): StripDot[] =>
    b.books.flatMap((r) => (r[k] == null ? [] : [{ key: r.book, v: r[k]!, label: bookName(r.book), detail: p(r) }]))
  const spreadPrice = (r: BookLine) => (r.spread_home == null ? '' : `${price(r.spread_home >= 0 ? r.home_price : r.away_price)}`)
  const rows = [...b.books].sort((a, c) => (c.spread_home ?? -99) - (a.spread_home ?? -99) || bookName(a.book).localeCompare(bookName(c.book)))
  const flag = disagrees(b)
  return (
    <Section
      title="What each sportsbook says"
      help="Each book's line at our last snapshot before kickoff; the consensus is their median. A gap means the market hasn't settled, not a mistake to exploit."
    >
      <p className={`m-0 ${flag ? 'border-l-[3px] border-[var(--warning)] pl-2 text-ink' : 'text-ink-2'}`} data-testid="books-read">
        <strong className="font-semibold">{!flag ? 'Books agree:' : b.key != null || b.flags.includes('spread_gap') ? 'Books split on the spread:' : 'Books split on the total:'}</strong>{' '}
        {/* a split names who sits where; an agreement is just the range */}
        {flag ? booksSentence(b, g.home, g.away).replace(/\.$/, '') : booksRange(b, g.home, g.away)} · {b.books.length} books, {etStamp(b.snapshot_ts)}
      </p>
      <div className="mt-3 flex flex-col gap-3">
        {b.spread && <BookStrip label="Spread" dots={dots('spread_home', spreadPrice)} median={b.spread.median} format={(v) => spreadLabel(v, g.home, g.away)} sides={sides} />}
        {b.total && <BookStrip label="Total" dots={dots('total', (r) => `o ${price(r.over_price)} / u ${price(r.under_price)}`)} median={b.total.median} format={fmtPts} />}
      </div>
      <TableScroll>
        <table className="mt-3 w-full border-collapse text-[14px]">
          <thead>
            <tr>
              <th className={th}>Book</th>
              <th className={th}>Spread</th>
              <th className={th}>Total</th>
              <th className={th}>{g.home} win chance</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.book}>
                <td className={td}>{bookName(r.book)}</td>
                <td className={`${td} tabular whitespace-nowrap`}>
                  {spreadLabel(r.spread_home, g.home, g.away)} <span className="text-ink-3">{spreadPrice(r)}</span>
                </td>
                <td className={`${td} tabular`}>{r.total == null ? '–' : fmtPts(r.total)}</td>
                <td className={`${td} tabular`}>{r.p_home == null ? '–' : pct(r.p_home)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
      {b.n_stale > 0 && <p className="mt-2 mb-0 text-[12px] text-ink-3">{b.n_stale} more left out: their quote was over six hours old.</p>}
    </Section>
  )
}
