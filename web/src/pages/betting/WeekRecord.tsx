import { Section } from '../../components/ui'
import type { BettingWeek } from '../../data/contract'
import { Lede } from './common'
import { PaperRecord } from './PaperRecord'
import { RulesTable } from './RulesTable'

/** What following the card would have returned: this season live at the locks, and the same rules in history. */
export function WeekRecord({ w }: { w: BettingWeek }) {
  return (
    <div className="flex flex-col gap-8">
      <Section title="This season at the locks" help="Each target and avoid is graded at the consensus price at each lock, one unit a bet. A handful of games a week is far too few to say anything.">
        <Lede>Targets against avoids, one unit a bet at the consensus price at each lock.</Lede>
        <PaperRecord w={w} />
      </Section>
      <Section title="The same rules in history" help="The card's rules applied to every game since the study began, by period.">
        <Lede>How each group did before this season.</Lede>
        <RulesTable rules={w.rules} />
      </Section>
    </div>
  )
}
