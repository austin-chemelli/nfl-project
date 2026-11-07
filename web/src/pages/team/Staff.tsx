import { Card } from '../../components/ui'
import { FinePrint } from '../../components/FinePrint'
import { Block } from './Block'
import type { TeamFile } from '../../data/contract'
import { callerTitle, careerLine, changeLines, evidenceLabel, otherStaff, type Side } from './staff'

type Caller = NonNullable<TeamFile['units']['off']['caller']>

function SourceLink({ url, evidence }: { url: string | null | undefined; evidence: string | null | undefined }) {
  const label = evidenceLabel(evidence)
  if (!url || !label) return null
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="text-[13px] underline decoration-line underline-offset-2 hover:text-ink">
      {label}
    </a>
  )
}

function CallerCard({ side, caller }: { side: Side; caller: Caller | null }) {
  const unit = side === 'off' ? 'offense' : 'defense'
  if (!caller) {
    return (
      <Card>
        <h3 className="text-base font-semibold">Runs the {unit}</h3>
        <p className="mt-1 text-ink-2">No one established</p>
      </Card>
    )
  }
  if (!caller.confirmed) {
    return (
      <Card className="flex flex-col gap-1">
        <h3 className="text-base font-semibold">Runs the {unit}</h3>
        <p className="break-words font-medium">{caller.name}</p>
        <p className="text-[13px] text-ink-3">{callerTitle(caller, side)}</p>
        <p className="text-ink-2">Play-caller not confirmed</p>
      </Card>
    )
  }
  const career = careerLine(caller.career)
  return (
    <Card className="flex flex-col gap-1">
      <h3 className="text-base font-semibold">Calls the {unit}</h3>
      <p className="break-words font-medium">{caller.name}</p>
      <p className="text-[13px] text-ink-3">{callerTitle(caller, side)}</p>
      {caller.situation_text ? <p className="text-ink-2">{caller.situation_text}</p> : null}
      {career ? <p className="text-[13px] text-ink-3">{career}</p> : null}
      <p className="break-all"><SourceLink url={caller.source_url} evidence={caller.evidence} /></p>
    </Card>
  )
}

export function Staff({ file }: { file: TeamFile }) {
  const others = otherStaff(file)
  const changes = changeLines(file.staff.changes)
  return (
    <div className="flex flex-col gap-8">
      <Block title={`Who calls the plays in ${file.season}`}>
        <div className="grid gap-4 md:grid-cols-2">
          <CallerCard side="off" caller={file.units.off.caller} />
          <CallerCard side="def" caller={file.units.def.caller} />
        </div>
      </Block>
      {others.length > 0 ? (
        <Block title="Coaching staff">
          <ul className="flex flex-col gap-2">
            {others.map((s) => (
              <li key={`${s.role}-${s.name}`} className="break-words">
                <span className="font-medium">{s.name}</span> <span className="text-[13px] text-ink-3">{s.title}</span>{' '}
                <span className="break-all"><SourceLink url={s.source_url} evidence={s.evidence} /></span>
              </li>
            ))}
          </ul>
        </Block>
      ) : null}
      {changes.length > 0 ? (
        <Block title="Changes this season">
          <ul className="flex flex-col gap-2">
            {changes.map((c) => <li key={c.text} className="break-words">{c.text}</li>)}
          </ul>
        </Block>
      ) : null}
      <FinePrint>
        <p>Team site: the team's own coaches page or announcement. News: a news report. 32-team list: a league-wide roundup of play-callers.</p>
        <p>When no source names a unit's play-caller, the card shows the coordinator and says so.</p>
        <p>Career lines list seasons a source confirms, from 2016, so a gap doesn't mean time off. First year means first in our table of NFL staffs.</p>
      </FinePrint>
    </div>
  )
}
