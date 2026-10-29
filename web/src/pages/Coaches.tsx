import { useSearchParams } from 'react-router'
import { Loaded, Page, Section, Segmented } from '../components/ui'
import { useCoaches } from '../data/api'
import type { Coaches } from '../data/contract'
import { CoachView } from './coaches/CoachView'
import { TeamView } from './coaches/TeamView'
import { SIDE_NAME, metricsFor } from './coaches/helpers'

type Mode = 'team' | 'coach'

export default function CoachesPage() {
  const q = useCoaches()
  const [params, setParams] = useSearchParams()
  const mode: Mode = params.get('view') === 'coach' || params.has('coach') ? 'coach' : 'team'
  const update = (fn: (p: URLSearchParams) => void) =>
    setParams((prev) => { const n = new URLSearchParams(prev); fn(n); return n }, { replace: true })

  return (
    <Page
      title="Coaches & schemes"
      lede="What each play-caller's units have done, set against that season's league, and what that says about a team's coordinators this year."
    >
      {/* The header renders at once; the 1.2 MB file loads below it. */}
      <Loaded q={q} what="coaches">
        {(site) => (
          <>
            <Notes site={site} />
            <div>
              <Segmented<Mode>
                label="View"
                value={mode}
                onChange={(m) => update((n) => { if (m === 'team') { n.delete('view'); n.delete('coach') } else n.set('view', 'coach') })}
                options={[{ value: 'team', label: 'Team view' }, { value: 'coach', label: 'Coach view' }]}
              />
            </div>
            {mode === 'team' ? (
              <TeamView
                site={site}
                team={params.get('team') && params.get('team')! in site.teams ? params.get('team')! : Object.keys(site.teams).sort()[0]}
                onTeam={(t) => update((n) => n.set('team', t))}
              />
            ) : (
              <CoachView site={site} coach={params.get('coach')} onCoach={(c) => update((n) => n.set('coach', c))} />
            )}
          </>
        )}
      </Loaded>
    </Page>
  )
}

function Notes({ site }: { site: Coaches }) {
  return (
    <Section title="How to read this">
      <ul className="list-disc space-y-1.5 pl-5 text-ink-2">
        <li>Percentiles compare a unit with the rest of the league in the <b>same season</b>: 80% means more than 80% of teams. 50% is the league middle.</li>
        <li>{site.note}</li>
        <li>Coverage (man / zone / two-high) is charted only from 2018, and the charting provider changed in 2023, so league-wide man rates jump. That is why nothing here averages raw rates across seasons.</li>
        <li>Observational: a coordinator's numbers also reflect his roster and quarterback.</li>
        <li>Coordinator assignments were extracted from public sources and then validated by hand.</li>
      </ul>
      <details className="mt-3 text-[13px]">
        <summary className="cursor-pointer text-ink-2 hover:text-ink">What each measure means</summary>
        <div className="mt-2 grid gap-4 md:grid-cols-2">
          {(['off', 'def'] as const).map((side) => (
            <div key={side}>
              <h3 className="font-semibold">{SIDE_NAME[side]}</h3>
              <ul className="mt-1 space-y-1 text-ink-2">
                {metricsFor(site.metrics, side).map(([k, d]) => (
                  <li key={k}><b>{d.label}</b> ({d.kind === 'scheme' ? 'what they chose' : 'how it went'}): {d.help}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </details>
    </Section>
  )
}
