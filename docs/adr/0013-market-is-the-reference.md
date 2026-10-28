# ADR 0013: The market is the reference, never an input

Status: accepted 2026-10-27. Amends ADR 0003 (features) and ADR 0012 (groups).

## Context
The Sharp persona weighted the market's own forecast (the spread) at about 85% of its budget, so its predictions were the market plus noise. Austin's reaction: the point of the project is to build our own way of judging games from football information and then *compare* it with the market, not to restate the market. Market behavior (line movement, where the public is, books disagreeing) is still interesting as a supplement.

## Decision
- **The market's forecast is never an input to an approach.** `market.spread_line`, `market.p_home_vigfree`, `market.total_line` and anything derived from the level of the line are excluded from every approach and from the DIY page. They remain the **reference**: the market baseline on every scorecard, the divergence analysis, and the ledger.
- **A "Market behavior" group is allowed as a supplement**, capped at **20% of any persona's attention budget**: `market.line_move_pts` (where the line has moved since it opened), `narrative.public_bet_pct_home` (where the public is). These describe how the market is *behaving*, not what it predicts. Most exist live only (one untimestamped line per historical game), so this group contributes almost nothing to backtests; the UI says so.
- **The Sharp is redefined** as the reader of market behavior: fades the public, follows line movement, and otherwise trusts efficiency and the quarterback. Its historical record is therefore mostly an Analyst-like record; its identity shows up live. Its card says exactly that.
- The Student stays market-free (unchanged). The ensemble is the average of the four personas: "what our fans collectively think", market-free.

## Consequences
Every approach now trails the market by about 0.015 log loss in the backtest instead of the Sharp "tying" it. That is the honest picture: the market already contains the football information plus everything else. The divergence analysis ("when we disagree with the market, who is right?") becomes the central comparison. The Market group in the registry is renamed "Market behavior"; `market.key_number` is dropped (it needs the line's level). The DIY page loses its market slider.

## Amendment 2026-10-28 (code review)
`market.ml_spread_gap` (vig-free moneyline probability minus Φ(spread/13.5)) was removed from Market behavior and added to the forbidden set. Φ(spread/13.5) is not how books map spreads to moneylines, so the gap was mostly a monotone function of the spread (correlation 0.63 with the spread on 2005–2025; about 45% of the spread's information). It leaked the line's level into the Sharp and the DIY page and inflated the Sharp's backtest. Market behavior is now line movement and the public's side only, both live-only, so the group contributes nothing to backtests, and live-only inputs are standardized with declared scale priors so they can't swing a prediction on raw units.
