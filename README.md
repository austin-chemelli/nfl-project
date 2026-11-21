# nfl-project

A weekly NFL preview and prediction tool, built to be educational first and market-aware second.

Several **approaches** look at the same evidence the way different kinds of fans do. The **Traditionalist** trusts records, momentum, rest and home crowds. The **Analyst** lives in EPA and quarterback play. The **Sharp** starts from the betting line. The **Student** has no opinions and learns only from results. Each approach comes in two flavors: a hand-set *persona* (what that fan believes) and a *fitted* version (what history says about the same evidence). The gap between them is the point: the Traditionalist, for example, weighs momentum about four times more than the data supports.

Every week, predictions for every game are locked before kickoff and committed to this repository with a SHA-256 hash, then scored publicly against the betting market. The scoring covers forecast quality, odds-weighted paper bets, closing-line value, and how often each approach was right when it disagreed with the market.

## Scorecard

<!-- scorecard:start -->

### Live record

| Model | Games | Log loss | Brier |
|---|---|---|---|
| Market (vig-free moneyline) | 30 | 0.4828 | 0.1532 |
| The Traditionalist | 30 | 0.5383 | 0.1785 |
| The Analyst | 30 | 0.5322 | 0.1754 |
| The Sharp | 30 | 0.5692 | 0.1923 |
| The Student | 30 | 0.5293 | 0.1740 |
| Elo | 30 | 0.5309 | 0.1761 |
| Home team 57% | 30 | 0.7500 | 0.2782 |

Lower is better. A season of live games cannot rank models; see the backtest for intervals.

### Backtest, 2005–2025 (walk-forward: each season scored by models trained only on earlier seasons)

| Model | Games | Log loss | Δ vs market (90% CI) |
|---|---|---|---|
| Market (vig-free moneyline) | 5,834 | 0.6088 |  |
| The Traditionalist | 5,834 | 0.6290 | +0.0201 (+0.0153 to +0.0248) |
| The Analyst | 5,834 | 0.6243 | +0.0155 (+0.0120 to +0.0196) |
| The Sharp | 5,834 | 0.6281 | +0.0193 (+0.0153 to +0.0240) |
| The Student | 5,834 | 0.6236 | +0.0148 (+0.0113 to +0.0186) |
| Elo | 5,834 | 0.6290 | +0.0201 (+0.0159 to +0.0241) |
| Home team 57% | 5,834 | 0.6869 | +0.0780 (+0.0707 to +0.0843) |

<!-- scorecard:end -->

## How it works

- **Data:** nflverse play-by-play (1999–), schedules, FTN charting (2022–), injuries and depth charts; The Odds API for timestamped lines. Raw files are kept as immutable snapshots.
- **Features:** about 60 point-in-time features (team strength, quarterback, health, form, rest and travel, venue, coaching, scheme, market), grouped into 15 higher-level groups whose inner weights are fitted from history.
- **Approaches:** persona weights on the groups, a fitted flavor shrunk toward the persona, walk-forward fitting, calibration, and an ensemble.
- **Honesty rules:** every input carries a "known as of" timestamp, and a prediction may only use what was known before its lock. Leakage guards run as tests in CI. When results look too good, the first assumption is leakage; two leaks found that way are documented in [docs/journal.md](docs/journal.md).

Design: [docs/architecture.md](docs/architecture.md) · decisions: [docs/adr/](docs/adr/) · feature groups: [docs/feature-groups.md](docs/feature-groups.md) · weekly operation: [docs/runbook.md](docs/runbook.md) · plan: [docs/tasks.md](docs/tasks.md).

## Running it

```
uv sync --group dev
uv run nfl run-all          # full historical build (first run downloads ~2 GB)
uv run nfl lock --slot sat --dry-run
uv run pytest -q
```

## Limits

Observational data, small samples, and an efficient market: a single season of live games can't rank models, and no approach here beats the betting line in the backtest. That is a result, not a bug. No real-money betting.

## Credits and license

Data from [nflverse](https://github.com/nflverse) (CC-BY 4.0), including FTN Data charting (CC-BY-SA 4.0). Lines from [The Odds API](https://the-odds-api.com). Code is MIT-licensed ([LICENSE](LICENSE)); published derived data (predictions, features, scorecards) is CC-BY-SA 4.0.

Fan-made and not affiliated with the NFL or any team.
