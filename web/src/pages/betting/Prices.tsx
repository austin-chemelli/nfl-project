import { DivergingBars, DotWhisker } from '../../charts'
import { DataTable, Section, td, th } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { pct, signedPct } from '../../lib/format'
import { Lede } from './common'
import { field, minus, periodKeys, periodLabel } from './facts'

const ptsOff = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)} pts`

/** Every side bet at the closing moneyline, by price band. */
export function Prices({ m }: { m: BettingMath }) {
  const periods = periodKeys(m.bands[0])
  return (
    <>
      <Section title="Return by price" help="Return is profit per dollar staked, betting every side in the band at the closing moneyline. The whisker is a 90% range.">
        <Lede>Every side bet at the closing moneyline, by price.</Lede>
        <DotWhisker
          rowHeight={38}
          labelWidth={190}
          rows={m.bands
            .filter((b) => b.roi != null)
            .map((b) => ({
              key: b.band,
              label: (
                <span className="min-w-0 truncate leading-tight">
                  {b.label}
                  <span className="block text-[11px] text-ink-3">{minus(b.prices)}</span>
                </span>
              ),
              value: b.roi!,
              lo: b.roi_lo ?? b.roi!,
              hi: b.roi_hi ?? b.roi!,
              title: `${b.label} (${minus(b.prices)}): ${signedPct(b.roi)}, 90% range ${signedPct(b.roi_lo)} to ${signedPct(b.roi_hi)}, ${b.n.toLocaleString('en-US')} bets`,
            }))}
          format={(v) => signedPct(v, 0)}
          refLabel="Break-even"
          leftLabel="loses money"
          rightLabel="makes money"
        />
      </Section>

      <Section title="Do favorites win as often as their price says?" help="The gap between how often a side won and the chance its price implied, without the bookmaker's cut. Positive: it won more often than the price said.">
        <Lede>Favorites and long shots won close to what their prices implied; the gaps are small.</Lede>
        <DivergingBars
          ariaLabel="Win rate minus the fair chance, by price band"
          rowHeight={30}
          labelWidth={150}
          leftLabel="won less than priced"
          rightLabel="won more than priced"
          format={ptsOff}
          rows={m.bands
            .filter((b) => b.bias != null)
            .map((b) => ({
              key: b.band,
              label: b.label,
              value: 100 * b.bias!,
              title: `${b.label}: won ${pct(b.win_rate, 1)}, the price implied ${pct(b.p_mkt, 1)}`,
            }))}
        />
        <DataTable summary="Show the numbers: prices">
          <table className="w-full text-[13px]">
            <thead>
              <tr>
                <th className={th}>Price</th>
                <th className={th}>Bets</th>
                <th className={th}>Win rate</th>
                <th className={th}>Fair chance</th>
                <th className={th}>Return</th>
                <th className={th}>90% range</th>
                {periods.map((p) => (
                  <th key={p} className={th}>{periodLabel(p)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {m.bands.map((b) => (
                <tr key={b.band}>
                  <td className={td}>
                    {b.label} <span className="text-ink-3">{minus(b.prices)}</span>
                  </td>
                  <td className={`${td} tabular`}>{b.n.toLocaleString('en-US')}</td>
                  <td className={`${td} tabular`}>{pct(b.win_rate, 1)}</td>
                  <td className={`${td} tabular`}>{pct(b.p_mkt, 1)}</td>
                  <td className={`${td} tabular`}>{signedPct(b.roi)}</td>
                  <td className={`${td} tabular`}>{signedPct(b.roi_lo)} to {signedPct(b.roi_hi)}</td>
                  {periods.map((p) => (
                    <td key={p} className={`${td} tabular`}>{signedPct(field(b, `roi_${p}`))}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </DataTable>
      </Section>
    </>
  )
}
