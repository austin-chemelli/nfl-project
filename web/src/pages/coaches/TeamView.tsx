import { Card } from '../../components/ui'
import type { Coaches, TeamCaller } from '../../data/contract'
import { Profile } from './Profile'
import { SIDE_NAME } from './helpers'

function CallerCard({ side, block, metrics, season }: { side: 'off' | 'def'; block: TeamCaller | null; metrics: Coaches['metrics']; season: number }) {
  if (!block) {
    return (
      <Card>
        <h3 className="text-base font-semibold">{SIDE_NAME[side]}</h3>
        <p className="mt-1 text-ink-2">No play-caller established in the coordinator table.</p>
      </Card>
    )
  }
  const role = block.source === 'play_caller' ? 'Play-caller' : 'Coordinator (play-caller not confirmed)'
  return (
    <Card className="flex flex-col gap-3">
      <div>
        <h3 className="text-base font-semibold">{SIDE_NAME[side]}: {block.name}</h3>
        <p className="text-[13px] text-ink-3">{role}.{block.is_head_coach ? ' Also the head coach.' : ''}</p>
      </div>
      <p>{block.sentence}</p>
      {block.has_history && block.prior ? (
        <Profile summary={block.prior} metrics={metrics} side={side} />
      ) : (
        <p className="text-[13px] text-ink-3">No history yet: {season} tendencies come only from news (see the game page narrative).</p>
      )}
    </Card>
  )
}

export function TeamView({ site, team, onTeam }: { site: Coaches; team: string; onTeam: (t: string) => void }) {
  const teams = Object.keys(site.teams).sort()
  const t = site.teams[team]
  return (
    <div className="flex flex-col gap-4">
      <label className="flex w-40 flex-col gap-1 text-[13px] text-ink-3">
        Team ({site.current_season} season)
        <select className="rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink" value={team} onChange={(e) => onTeam(e.target.value)}>
          {teams.map((c) => <option key={c}>{c}</option>)}
        </select>
      </label>
      <div>
        <p><span className="font-semibold">Head coach:</span> {t.head_coach ?? '–'}</p>
        <p className="text-[13px] text-ink-3">
          Profiles use seasons before {site.current_season} only. New coordinators have no participation history; their {site.current_season} tendencies come only from news (see the game page narrative).
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <CallerCard side="off" block={t.off} metrics={site.metrics} season={site.current_season} />
        <CallerCard side="def" block={t.def} metrics={site.metrics} season={site.current_season} />
      </div>
    </div>
  )
}
