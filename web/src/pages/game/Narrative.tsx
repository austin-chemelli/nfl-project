import { Help } from '../../components/Help'
import { Card, Section } from '../../components/ui'
import type { Game, Narrative as N } from '../../data/contract'
import { impactMarker, QB_STATUS, sortMatchupNotes, sortNotes, sourcesText, trendStatus } from './helpers'

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">{children}</a>
}

function Sources({ urls }: { urls: string[] }) {
  if (!urls.length) return null
  return (
    <span className="text-[13px]">
      {urls.map((u, i) => (
        <span key={u}>{i > 0 && ', '}<Link href={u}>source {i + 1}</Link></span>
      ))}
    </span>
  )
}

function Team({ t }: { t: N['home'] }) {
  const notes = sortNotes(t.notes)
  return (
    <Card>
      <h3 className="text-[16px] font-semibold">{t.team}</h3>
      <p className="mt-1">{t.summary}</p>
      <p className="mt-1 text-[13px] text-ink-3">
        QB: {t.qb_name ?? 'n/a'} ({QB_STATUS[t.qb_status] ?? t.qb_status})
        {t.key_absences.length > 0 && ` · key absences: ${t.key_absences.join(', ')}`}
        {t.revenge && ' · revenge game'}
        {t.lookahead && ' · lookahead spot'}
      </p>
      {notes.length > 0 && (
        <>
          <h4 className="mt-3 text-[14px] font-semibold"><Help text="▲ helps and ▼ hurts this team; more arrows mean a bigger effect.">What matters</Help></h4>
          <ul className="mt-1 flex flex-col gap-1.5">
            {notes.map((n) => {
              const m = impactMarker(n.impact)
              return (
                <li key={n.text} className="text-[14px]">
                  <span className="font-medium whitespace-nowrap" style={{ color: n.impact > 0 ? 'var(--good)' : n.impact < 0 ? 'var(--critical)' : undefined }}>
                    <span aria-hidden>{m.arrows}</span> {m.words}
                  </span>{' '}
                  <span className="text-ink-3">({n.kind})</span> {n.text}{' '}
                  {n.source_url && <Link href={n.source_url}>source</Link>}
                </li>
              )
            })}
          </ul>
        </>
      )}
      {t.scheme_trends.length > 0 && (
        <>
          <h4 className="mt-3 text-[14px] font-semibold"><Help text="What analysts say the unit is doing lately and whether it is working.">Scheme trends</Help></h4>
          <ul className="mt-1 flex flex-col gap-1.5">
            {t.scheme_trends.map((s) => (
              <li key={`${s.unit}-${s.trend}`} className="text-[14px]">
                <span className="font-medium capitalize">{s.unit}</span>: {s.trend} <span className="text-ink-3">({trendStatus(s.working)})</span>{' '}
                <Sources urls={s.sources} />
              </li>
            ))}
          </ul>
        </>
      )}
      {notes.length === 0 && t.scheme_trends.length === 0 && <p className="mt-2 text-[13px] text-ink-3">No detailed notes in this research record (older format).</p>}
    </Card>
  )
}

export function NarrativeSection({ g }: { g: Game }) {
  const nar = g.narrative
  if (!nar) {
    return (
      <Section title="The week's narrative">
        <p className="text-ink-2">No narrative research for this game yet.</p>
      </Section>
    )
  }
  const mnotes = sortMatchupNotes(nar.matchup_notes)
  return (
    <Section title="The week's narrative" help="Text written from cited public coverage. It never feeds the probabilities.">
      <p className="mb-3 max-w-3xl text-[13px] text-ink-3">
        What the week's coverage says, as of {nar.known_as_of} (producer: {nar.producer}, model: {nar.model}). Written from cited sources; it never
        feeds the probabilities.
      </p>
      {nar.consensus_narrative && (
        <p className="mb-4 max-w-3xl">
          <b>The story:</b> {nar.consensus_narrative}
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Team t={nar.away} />
        <Team t={nar.home} />
      </div>
      {mnotes.length > 0 && (
        <div className="mt-6">
          <h3 className="text-[16px] font-semibold">
            <Help text="Takes from public analysis of how these two teams match up. More independent sources agreeing means more weight.">
              What people are saying about the matchup
            </Help>
          </h3>
          <ul className="mt-2 flex flex-col gap-2">
            {mnotes.map((n) => (
              <li key={n.text}>
                {n.text} <span className="text-ink-3">({sourcesText(n.support || n.sources.length)}{n.sources.length ? ': ' : ''}</span>
                <Sources urls={n.sources} />
                <span className="text-ink-3">)</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <details className="mt-4">
        <summary className="cursor-pointer text-ink-2 hover:text-ink">Claims and sources ({nar.claims.length})</summary>
        <ul className="mt-2 flex flex-col gap-1.5 text-[14px]">
          {nar.claims.map((c) => (
            <li key={`${c.source_url}-${c.claim}`}>
              {c.claim}{' '}
              <span className="text-ink-3">
                ({c.category}, {c.confidence} confidence{c.published_at ? `, ${c.published_at}` : ''})
              </span>{' '}
              <Link href={c.source_url}>{c.source_title || c.source_url}</Link>
            </li>
          ))}
        </ul>
      </details>
    </Section>
  )
}
