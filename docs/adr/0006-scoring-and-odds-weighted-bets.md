# ADR 0006: Forecast quality first; odds-weighted paper bets and divergence buckets second

Status: accepted 2026-10-25.

## Context
Betting is a lens, not the goal, but a win/loss tally ignores the odds, and season P&L is noise. The interesting question is "when an approach disagrees with the market, how often is it right?"

## Decision
- Primary metrics per model: log loss, Brier, calibration (ECE, reliability bins), spread MAE, versus `market_baseline` and `home_naive`.
- Paper ledger: at each lock, every model stakes a flat 1 unit on the moneyline (or the spread when the disagreement is in spread terms) wherever `|model_p − market_p_vigfree| > 0.05`. Bets are immutable rows at the real price. Track units, hit rate and closing-line value (CLV), which is the primary edge metric. Fractional Kelly is a later sizing variant.
- Divergence buckets: graded rows grouped by `|model_p − market_p|` (0–2.5, 2.5–5, 5–10, 10+ points) with n, hit rate and log loss per model. Shown on the tracker and per approach.
- Every public table states n and that ~180 live games cannot rank models.

## Consequences
Needs timestamped lines at lock and at close, hence the Odds API in M3. Amended 2026-10-26: the historical endpoint is paid-only on the free plan, so the closing line is our own snapshot taken within 3h of kickoff (3 credits each; ~5 kickoff windows a week), falling back to nflverse's schedule line. Backfill bets are priced at nflverse's closing-ish line, so their CLV is undefined and their ROI is a harsh lower bound. Threshold and stake are config values, expected to be tuned later.
