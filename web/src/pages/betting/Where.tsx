import { Section, TableScroll, td, th } from '../../components/ui'
import type { BettingMath } from '../../data/contract'
import { american, signedPct } from '../../lib/format'
import { Lede } from './common'
import { TexasBox } from './TexasBox'

const POOLS: Record<string, string> = {
  every_favorite: 'Every favorite',
  every_underdog: 'Every underdog',
  model_picks: "The Student's picks",
  model_leans_5: "The Student's leans of 5+ points",
}

/** What the same bets return at a book, a worse book, and an exchange. */
export function Where({ m }: { m: BettingMath }) {
  return (
    <>
      <Section title="Where you bet changes the cost" help="Return on the same bets at a licensed book, at a book whose price is 10 or 20 cents worse, on an exchange, and with a fee of 2% or 4% of the stake.">
        <Lede>The same bets cost different amounts at different places.</Lede>
        <TableScroll>
          <table className="w-full text-[13px]">
            <thead>
              <tr>
                <th className={th}>Bets</th>
                <th className={th}>Book</th>
                <th className={th}>10¢ worse</th>
                <th className={th}>20¢ worse</th>
                <th className={th}>Exchange</th>
                <th className={th}>+2% fee</th>
                <th className={th}>+4% fee</th>
              </tr>
            </thead>
            <tbody>
              {m.fees.map((f) => (
                <tr key={f.pool}>
                  <td className={td}>{POOLS[f.pool] ?? f.pool}</td>
                  {[f.book, f.book_minus_10c, f.book_minus_20c, f.exchange, f.fee_2pct, f.fee_4pct].map((v, i) => (
                    <td key={i} className={`${td} tabular`}>{signedPct(v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      </Section>

      <Section title="An exchange's fee, by contract price" help="Prediction markets price a contract from 1¢ to 99¢; the price is the implied chance. The fee is charged per contract, so it weighs most on long shots.">
        <Lede>The fee is a bigger share of your stake the cheaper the contract.</Lede>
        <TableScroll>
          <table className="w-full text-[13px]">
            <thead>
              <tr>
                <th className={th}>Contract price</th>
                <th className={th}>Fee, as % of stake</th>
                <th className={th}>Same as American odds</th>
              </tr>
            </thead>
            <tbody>
              {m.exchange_fee.map((e) => (
                <tr key={e.price_cents}>
                  <td className={`${td} tabular`}>{e.price_cents}¢</td>
                  <td className={`${td} tabular`}>{e.fee_pct_of_stake}%</td>
                  <td className={`${td} tabular`}>{american(e.american_equiv)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      </Section>

      <TexasBox />
    </>
  )
}
