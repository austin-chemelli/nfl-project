# ADR 0001: Free, redistributable data only

Status: accepted 2026-10-23.

## Context
In-season coverage, personnel and formation charting is only available from paid sources (NFL Pro, PFF, FTN direct, Fantasy Points), none of which permit republishing. nflverse ships FTN charting in-season (box count, blitzers, motion, play-action, RPO, QB alignment) and participation data (coverage, personnel) after the season. The project is public and its derived data will be published.

## Options
1. nflverse + The Odds API free tier only.
2. Add a paid consumer source (Fantasy Points ~$200/yr) for private research, cite it in previews.
3. Build on a paid API (PFF Pro, FTN) as a first-class source.

## Decision
Option 1. Paid sources may be added later as a personal research input, never into the published store.

## Consequences
Coverage and personnel features arrive each February with the participation drop, so matchup-style features are offseason work. The backtest and the live system use the same provider, which keeps them consistent. Published derived data inherits FTN's CC-BY-SA (see ADR 0011).
