import { Card } from '../../components/ui'

const ext = { target: '_blank', rel: 'noreferrer noopener' } as const

/** Static copy (ADR 0033): the legal situation as of the dates stated. Not legal advice. */
export function TexasBox() {
  return (
    <Card>
      <h2 className="text-lg font-semibold">Betting from Texas (not legal advice)</h2>
      <ul className="mt-2 flex list-disc flex-col gap-2 pl-5 text-[14px] text-ink-2">
        <li>
          Texas has no legal sportsbooks; bills failed in 2023 and 2025, and the next chance is the January 2027 legislative session (
          <a href="https://www.texastribune.org/" {...ext}>Texas Tribune, 2026-05-01</a>).
        </li>
        <li>
          Federally regulated prediction markets (Underdog Predict, Kalshi, Polymarket US and others) sell contracts on NFL games to Texans under CFTC rules. The state disputes it: the Lt. Governor ordered a study of &quot;gambling loopholes&quot; in March 2026 and a Senate committee held a hearing on 2026-09-15; no enforcement had been reported as of 2026-11-20.
        </li>
        <li>
          Underdog Predict prices contracts from 1¢ to 99¢ (the price is the implied chance) and charges a fee per contract, reported at about 3.5% of the stake at 50¢. Its pick&apos;em game is a different product: a parlay against the house with fixed payouts, so the cut compounds.
        </li>
        <li>Our odds feed carries Kalshi and Polymarket US but not Underdog Predict, so the weekly card gives every fair price in cents as well as American odds.</li>
        <li>No legal advice; rules are changing. Never use an unlicensed or offshore book.</li>
      </ul>
    </Card>
  )
}
