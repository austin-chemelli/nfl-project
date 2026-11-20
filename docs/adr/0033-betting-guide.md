# ADR 0033: The betting guide: rules from our own history, the math public, the card unlisted

Status: accepted 2026-11-20 (track betting-guide, model round 3; Austin approves with the PR). Extends ADR 0006 (paper ledger), ADR 0013 (the market is the reference), ADR 0029 (browser-only storage).

## Context
Austin wants to place small, manual, for-fun bets (Underdog, from Texas) and asked for a smarter way to choose them: singles or parlays, heavy favorites, coin flips, how much to stake, and spreads or totals only with strong evidence. The backtest shows no edge: the market's log loss is 0.6090 against the Student's 0.6243, and every paper ledger line loses money. Texas has no legal sportsbooks; federally regulated prediction markets operate there under dispute. Nothing in the project places, automates or integrates a bet.

## Decision
1. **A study on our own history decides the rules** (`src/nfl/betting/study.py`, `nfl betting study`, findings in `.notes/hub/plans/betting-study.md`). Moneylines 2006-2025 at the schedule's roughly closing prices; model chances from the walk-forward backfill (ADR 0005). Every rule search is walk-forward or split into halves, with the number of rules tried stated (186). The model is a parameter, so a new Student reruns everything; the stored study is rerun automatically when the backfill's model version changes, and weekly by `nfl weekly refresh`.
2. **The card's rules (guide v1)**, each from a finding:
   - Moneyline singles on the headline model's pick to win; never parlays (the cut compounds: −3.6% single, −15.6% at four legs).
   - *Worth a look*: the pick is priced about −185 or shorter (market fair chance 65%+) and the model rates it at least as likely as the market (the least costly bands, −1.3% and −1.9%). At most four a week.
   - *For fun*: coin flips, the model's upset picks, and big favorites the model rates below the market (about the cut).
   - *Skip*: −120 to −185 favorites (−6.2%, negative in both halves) and anything at +185 or longer (long shots −14.4%).
   - *Targeted*: a spread or total must be ahead in both halves, have its 90% range above zero, be ahead over 2021-2025, and have a neighbouring version of the condition point the same way. Only the under in 15+ mph wind outdoors passes (+9.7% on 466 games, measured on recorded wind); the card shows it when the forecast reaches 15 mph. Nothing on spreads passes.
   - *The price needed*: the break-even price of the blended chance, logit(market) + w·(logit(model) − logit(market)), with w fitted on every earlier season (0.02 for 2026), in American odds and in exchange cents after a 0.07·p·(1−p) taker fee.
   - *Stake*: 1% of the reader's bankroll a bet, flat. Kelly on the honest (blended) chance bets almost nothing; on the model's own chance it lost half the bankroll in 83-88% of simulated seasons. A fractional Kelly ledger variant (offseason backlog) is therefore not built: the study answers it.
3. **The paper ledger is untouched** (ADR 0006): the card is its own series, labelled with its rule version (`guide-v1`). Its record is derived from append-only inputs (live lock rows and odds snapshots, priced at the consensus snapshot at or before each lock), so a rerun reproduces it; a changed rule gets a new version, never a rewrite.
4. **Who sees what** (decision 3 of the round plan, recommendation (b)): the math is a public "Betting math" page (`/betting`, `site/betting_math.json`); the weekly card and the bet log are **unlisted** (`/betting/week`, reachable by URL so Austin can use it on his phone, in no nav or public link, `noindex`). One switch per section in `web/src/lib/bettingVisibility.ts` (`public` | `unlisted` | `dev`, the last as `hiddenPages.ts`). The card's data (`site/betting_week.json`) sits in the public bucket like every site file.
5. **The bet log lives in the browser** (ADR 0029's pattern): game, side, price (American or cents), stake, fee, venue; graded against the season's results and our closing consensus (`closing` in `betting_week.json`) with closing-line value; exportable as CSV and JSON. Nothing is sent anywhere.
6. **Honest copy throughout**: no edge in 20 seasons, small samples, a fun test and not income, "not betting advice", the national helpline (1-800-MY-RESET) on every betting page. Texas facts are dated, sourced and "not legal advice"; no unlicensed or offshore book is ever named as a place to bet (the "best price" on the card is among the four state-licensed US books in our feed only).

## Consequences
- The guide follows the model: when the Approaches track ships a new Student, `nfl betting study` (or the next `nfl site`, which notices the new version) refreshes every number; the pages print the model version they use.
- We can't show Underdog Predict's prices: the Odds API carries Kalshi and Polymarket US (`us_ex`), and `underdog` only in `us_dfs` (the pick'em board). Adding `us_ex` h2h to the snapshots would cost 1 credit per snapshot (about 11 a week); proposed, not switched on.
- The windy-under rule is measured on recorded wind; a forecast-based bet earns less. Revisit once a season of forecasts is stored (the weather family keeps every forecast it fetched).
- `nfl site` gains about 17 seconds when the study must be rerun (only on a new model version); `nfl weekly refresh` reruns it every Tuesday.
