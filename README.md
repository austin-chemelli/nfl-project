# nfl-project

A weekly NFL preview and prediction tool, built to be educational first and market-aware second.

Several **approaches** look at the same evidence the way different kinds of fans do. The **Traditionalist** trusts records, momentum, rest and home crowds. The **Analyst** lives in EPA and quarterback play. The **Sharp** starts from the betting line. The **Student** has no opinions and learns only from results. Each approach comes in two flavors: a hand-set *persona* (what that fan believes) and a *fitted* version (what history says about the same evidence). The gap between them is the point: the Traditionalist, for example, weighs momentum about four times more than the data supports.

Every week, predictions for every game are locked before kickoff and committed to this repository with a SHA-256 hash, then scored publicly against the betting market. The scoring covers forecast quality, odds-weighted paper bets, closing-line value, and how often each approach was right when it disagreed with the market.

## Scorecard

<!-- scorecard:start -->

### Live record

| Model | Games | Log loss | Brier |
|---|---|---|---|
| Market (vig-free moneyline) | 14 | 0.4132 | 0.1196 |
| The Traditionalist | 14 | 0.4302 | 0.1272 |
| The Analyst | 14 | 0.4591 | 0.1400 |
| The Sharp | 14 | 0.5453 | 0.1797 |
| The Student | 14 | 0.4515 | 0.1366 |
| Elo | 14 | 0.4755 | 0.1497 |
| Home team 57% | 14 | 0.7433 | 0.2749 |

Lower is better. A season of live games cannot rank models; see the backtest for intervals.

### Backtest, 2005–2025 (walk-forward: each season scored by models trained only on earlier seasons)

| Model | Games | Log loss | Δ vs market (90% CI) |
|---|---|---|---|
| Market (vig-free moneyline) | 5,818 | 0.6090 |  |
| The Traditionalist | 5,818 | 0.6289 | +0.0199 (+0.0146 to +0.0249) |
| The Analyst | 5,818 | 0.6246 | +0.0156 (+0.0119 to +0.0196) |
| The Sharp | 5,818 | 0.6286 | +0.0196 (+0.0147 to +0.0244) |
| The Student | 5,818 | 0.6243 | +0.0153 (+0.0113 to +0.0191) |
| The Student v2 | 5,818 | 0.6240 | +0.0150 (+0.0112 to +0.0187) |
| Elo | 5,818 | 0.6291 | +0.0201 (+0.0153 to +0.0240) |
| Home team 57% | 5,818 | 0.6867 | +0.0777 (+0.0712 to +0.0840) |

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
