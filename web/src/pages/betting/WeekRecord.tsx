import { Section } from '../../components/ui'
import type { BettingWeek } from '../../data/contract'
import { Lede } from './common'
import { GuideRuleTable } from './GuideRuleTable'
import { PaperRecord } from './PaperRecord'

/** What following the card would have returned: this season live, and the same rule in history. */
export function WeekRecord({ w }: { w: BettingWeek }) {
  return (
    <div className="flex flex-col gap-8">
      <Section title="This season at the locks" help="Each card bet is graded at the consensus price at each lock, one unit a bet. A handful of games a week is far too few to say anything.">
        <Lede>What following the card would have returned.</Lede>
        <PaperRecord w={w} />
        <p className="mt-2 text-[13px] text-ink-3">At the consensus price at each lock, 1 unit a bet.</p>
      </Section>
      <Section title="The same rule in history" help="The card's rule applied to every game since the study began, by period.">
        <Lede>How each group of the card did before this season.</Lede>
        <GuideRuleTable rows={w.history} />
      </Section>
    </div>
  )
}
