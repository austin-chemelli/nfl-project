import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FinePrint } from '../../components/FinePrint'
import { DataTable, Loaded, ModelBadge, Section, StatTile, td, th } from '../../components/ui'
import { useCustomSeason } from '../../data/api'
import { llVsMarket } from '../../lib/format'
import { colorVar, SHORT } from '../../lib/models'
import type { YouLine } from '../../you/current'
import { Unofficial } from '../../you/YouBar'
import { LINES, yourRecord, type LineRecord, type RecordLine } from './yourRecord'

const names = (): Record<RecordLine, string> => ({ you: SHORT.you, student: SHORT.student, market: 'Market' })
const MODEL: Record<RecordLine, string> = { you: 'you', student: 'student', market: 'market_baseline' }
const ll = (r: LineRecord) => (r.logLoss == null ? '–' : r.logLoss.toFixed(3))
const picks = (r: LineRecord) => (r.n ? `${r.right} of ${r.n}` : '–')

/** The reader's own saved line over this season's graded games, scored in this browser (ADR 0034). Unofficial. */
export function YourLine({ season, you }: { season: number; you: YouLine }) {
  const q = useCustomSeason(season)
  return (
    <Loaded q={q} what="your line" shape="tracker">
      {(data) => <Body data={data} you={you} />}
    </Loaded>
  )
}

function Body({ data, you }: { data: Parameters<typeof yourRecord>[0]; you: YouLine }) {
  const rec = useMemo(() => yourRecord(data, you), [data, you])
  const { all, since } = rec
  const name = SHORT.you
  const saved = new Date(you.savedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const sinceTxt =
    since.you.n === 0 ? 'no games have finished since you saved' : `${picks(since.you)} right, ${since.you.logLoss == null ? '–' : since.you.logLoss.toFixed(3)} log loss`
  return (
    <Section title="Your line">
      <p className="max-w-3xl text-ink-2">
        {all.you.n === 0
          ? `${name} has no scored games yet this season.`
          : `Over ${all.you.n} games this season, ${name === 'You' ? 'your line' : name} scored ${all.you.logLoss == null ? '–' : all.you.logLoss.toFixed(3)} log loss, against ${all.student.logLoss == null ? '–' : all.student.logLoss.toFixed(3)} for the Student and ${all.market.logLoss == null ? '–' : all.market.logLoss.toFixed(3)} for the market.`}
        <Unofficial />
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile
          label="Log loss vs the market"
          value={all.you.logLoss == null ? '–' : all.you.logLoss.toFixed(3)}
          sub={<>{all.you.logLoss != null && all.market.logLoss != null ? llVsMarket(all.you.logLoss, all.market.logLoss) : 'no market line yet'}<Unofficial /></>}
          help="Lower is better; 0.693 is a coin flip. Gaps under 0.025 are too close to call."
        />
        <StatTile
          label="Picks right"
          value={picks(all.you)}
          sub={`Student ${picks(all.student)}, market ${picks(all.market)}`}
          help="The side each line favored; a pick of exactly 50% counts for nobody."
        />
        <StatTile label={`Since you saved (${saved})`} value={since.you.n ? `${since.you.n} games` : 'None yet'} sub={sinceTxt} help="Only games that kicked off after you saved: the part your weights could not have been shaped by." />
      </div>
      {since.you.n > 0 && (
        <p className="text-[13px] text-ink-2">
          Since you saved, the Student was {picks(since.student)} right ({since.student.logLoss?.toFixed(3) ?? '–'}) and the market {picks(since.market)} ({since.market.logLoss?.toFixed(3) ?? '–'}).
        </p>
      )}
      <h3 className="mt-2 font-medium">Running log loss, by week</h3>
      <p className="text-[13px] text-ink-2">Average since week 1; lower is better.</p>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 288 }}>
          <LineChart data={rec.weeks} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" />
            <XAxis dataKey="week" type="number" domain={['dataMin', 'dataMax']} allowDecimals={false} stroke="var(--text-muted)" tick={{ fontSize: 12 }} />
            <YAxis domain={['auto', 'auto']} tickFormatter={(v: number) => v.toFixed(2)} stroke="var(--text-muted)" tick={{ fontSize: 12 }} width={44} />
            <Tooltip formatter={(v, k) => [Number(v).toFixed(3), names()[k as RecordLine] ?? String(k)]} labelFormatter={(w) => `Week ${w}`} contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', fontSize: 13 }} />
            {LINES.map((k) => (
              <Line key={k} dataKey={k} name={k} type="monotone" stroke={colorVar(MODEL[k])} strokeWidth={k === 'you' ? 2.5 : 1.5} strokeDasharray={k === 'market' ? '4 3' : undefined} dot={false} connectNulls isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTable summary="Show the numbers: your line this season">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Line</th>
              <th className={th}>Games</th>
              <th className={th}>Log loss</th>
              <th className={th}>Picks right</th>
              <th className={th}>Since you saved</th>
            </tr>
          </thead>
          <tbody>
            {LINES.map((k) => (
              <tr key={k}>
                <td className={td}><ModelBadge modelId={MODEL[k]} reference={k === 'market'} />{k === 'you' && <Unofficial />}</td>
                <td className={`${td} tabular`}>{all[k].n}</td>
                <td className={`${td} tabular`}>{ll(all[k])}</td>
                <td className={`${td} tabular`}>{picks(all[k])}</td>
                <td className={`${td} tabular`}>{since[k].n ? `${picks(since[k])}, ${ll(since[k])}` : '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
      <FinePrint>
        <p>Unofficial: your line is scored in this browser. It is never locked, graded or added to the ledger, and no one else sees it.</p>
        <p>It is built from the same inputs the Student read at its graded lock for each game, so it is comparable game for game.</p>
        <p>The Student&apos;s lines before 2026-11-21 were its earlier model version (wave 2), while yours uses this season&apos;s groups. Weeks before the first public lock (Week 9) are backfill for both.</p>
        <p>Your weights were set after seeing these results unless you saved before them, which is why &quot;since you saved&quot; is shown on its own. A few hundred games can&apos;t rank close lines.</p>
      </FinePrint>
    </Section>
  )
}
