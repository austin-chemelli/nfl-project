import type { SimilarFlag } from '../../data/contract'
import { flagGroups, type FlagCard } from './similar'

const EDGE: Record<SimilarFlag['kind'], string> = {
  red: 'border-l-[var(--critical)]',
  fine: 'border-l-[var(--warning)]',
  strength: 'border-l-[var(--good)]',
}
/** A mark that is not color: the shape says which group a card is in. */
const MARK: Record<SimilarFlag['kind'], string> = { red: '▲', fine: '◆', strength: '●' }

/** Two thin bars: the share of past teams with the trait that got there, and the share of the rest. Counts are printed too. */
function Bars({ card }: { card: FlagCard }) {
  const row = (label: string, [hits, n]: [number, number], strong: boolean) => (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-[12px] text-ink-3">{label}</span>
      <span aria-hidden className="h-1.5 min-w-0 flex-1 rounded-full bg-[var(--band)]">
        <span className="block h-full rounded-full" style={{ width: `${n > 0 ? (100 * hits) / n : 0}%`, background: strong ? 'var(--text-secondary)' : 'var(--band-strong)' }} />
      </span>
      <span className="tabular w-[4.25rem] shrink-0 whitespace-nowrap text-right text-[12px] text-ink-2">{hits} of {n}</span>
    </div>
  )
  return (
    <div className="mt-2 flex flex-col gap-1">
      {row('This trait', card.flagged, true)}
      {row('The rest', card.others, false)}
    </div>
  )
}

/** What history says about this team, in up to three groups. Each card is built from the counts, on the same record. */
export function FlagCards({ flags }: { flags: SimilarFlag[] }) {
  const groups = flagGroups(flags)
  if (groups.length === 0) {
    return <p className="text-ink-2">Nothing on our list of measures stands out for this team against past teams at the same record.</p>
  }
  return (
    <div className="flex flex-col gap-4">
      {groups.map((g) => (
        <section key={g.kind} aria-label={g.title}>
          <h4 className="mb-1.5 text-[12px] font-medium uppercase tracking-wide text-ink-3">
            <span aria-hidden>{MARK[g.kind]} </span>
            {g.title}
          </h4>
          <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-2 xl:grid-cols-3">
            {g.cards.map((c) => (
              <li key={c.key} className={`min-w-0 rounded-lg border border-line border-l-4 bg-surface-1 p-3 text-[13px] ${EDGE[c.kind]}`}>
                <p className="m-0 text-ink-2">
                  <strong className="font-semibold text-ink">{c.title}</strong> {c.lead ? `${c.lead} ` : ''}
                  {c.body}
                </p>
                <Bars card={c} />
                <p className="mb-0 mt-1.5 text-[12px] text-ink-3">{c.verdict}.{c.note ? ` ${c.note}` : ''}</p>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
