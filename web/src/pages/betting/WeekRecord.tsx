import { DataTable, Section } from '../../components/ui'
import type { BettingWeek } from '../../data/contract'
import { Lede } from './common'
import { PaperRecord } from './PaperRecord'
import { RecordChart } from './RecordChart'
import { HISTORY_ROWS } from './facts'
import { RulesTable } from './RulesTable'

/** What following the card would have returned: the same rules in history next to this season at the locks. */
export function WeekRecord({ w }: { w: BettingWeek }) {
  return (
    <div className="flex flex-col gap-8">
      <Section title="Return per bet" help="History re-ranks the bets each season using earlier seasons only, then follows the top five a week. The 2026 bars are graded at the consensus price at each lock, one unit a bet; a handful of games a week says very little.">
        <Lede>Above zero means ahead of the house.</Lede>
        <RecordChart w={w} />
        <DataTable>
          <RulesTable rules={w.rules} rows={HISTORY_ROWS} />
        </DataTable>
      </Section>
      <Section title="This season at the locks">
        <PaperRecord w={w} />
      </Section>
    </div>
  )
}
