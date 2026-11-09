# ADR 0027: Player value in points, and scored impact claims

Status: accepted 2026-11-08 (Austin). Closes hub decision D13. Extends ADR 0005 (point-in-time), ADR 0012 (groups), ADR 0018 (the bar for a public line), ADR 0025 (SQL models) and ADR 0026 (the candidates ledger). Plan and research: `.notes/plans/player-impact.md` and the three `research-player-*.md` notes beside it. Tasks: M24.

## Context
The model knows one player: the quarterback features follow the projected starter, and everyone else enters through `availability.injury_impact`, a hand-set weight per position times a status weight. Austin wants a player's impact quantified beyond the quarterback, with props and fantasy explicitly later and never the main focus. The research (2026-11-08) found: an elite quarterback is worth 4 to 7 points of spread over his backup and a star elsewhere 0.5 to 1.5, at most about 2; books price quarterback news within minutes, so a feature known at lock adds nothing the closing line lacks, though it can still improve our line; free nflverse data carries weekly player stats, snap counts (2012+), PFR advanced stats (2018+), contracts and draft picks; our raw play-by-play carries 43 player-id columns that `curate` drops, and the participation files carry who was on the field (offseason only). No free site publishes a checkable per-player number, and none scores its injury claims afterwards. No free, redistributable player-props source exists; the Odds API charges 4 credits per game and the game-line snapshots already use most of the free tier.

## Options
1. **Scope.** (a) Narrow: a value table and a value-weighted injury feature, model only. (b) Scored impact: (a) plus a number in points for every key absence on the game and team pages, graded afterwards against the market's move. (c) Wide: (b) plus with/without splits, player cards and a props pilot.
2. **When the feature may change a public line.** (a) As soon as it beats `injury_impact` on the backtest. (b) Context only for at least one lock cycle; it joins the Health group only after it clears the ledger's gates and a shadow line (ADR 0026's funnel).
3. **Props.** (a) A quarterback-only pilot now, 16 credits a week, paid for by dropping a game-line snapshot. (b) Parked.
4. **Positions in v1.** (a) QB, WR/TE, RB, the offensive line as a unit, edge rushers, corners and safeties. (b) Also interior linemen and linebackers, whose free data separates players poorly.
5. **Where it lives.** (a) A phase of M23. (b) Its own milestone reusing M23's ledger, SQL runner and reliability badge. M23 excluded player data by design and runs in its own worktree.

## Decision
1(b), 2(b), 3(b), 4(a), 5(b): milestone **M24**.

- **A player value table**, `marts/derived/player_value` (a SQL model through M23.3's runner): one row per (season, week, player, team): position group, snap share to date, a value in **points of spread** with its parts, and `known_as_of`. Value = a position prior from the published sizes (a top starter 0.5 to 1.5; the quarterback keeps `features/qb.py`) × a quality multiplier from production to date (EPA per target and target share; pressures per rush; coverage targets allowed), shrunk toward the position mean with a plays-based prior like the quarterback's 250 dropbacks; contract APY and draft slot are the prior for players with few snaps. Week W reads games through W−1 and prior seasons, decayed 0.75 a season.
- **Status-to-play rates from our own history** (injuries × snap counts, 2013+: the 2012 file is empty upstream): P(played | report status, position group, report day), published, replacing PFF's quoted 73% for Questionable.
- **`availability.value_lost`** = Σ over listed starters of value × P(out | status), home minus away, built into the store but in no approach. It and `availability.ol_weakest` are candidates in the ledger (ADR 0026), screened after M23.0 settles calibration. They join the Health group at a later registry bump only after a shadow line earns it; `injury_impact` stays until then.
- **Scored claims, not what-ifs.** While the feature is context only, the public claim is the player's value: "X is worth about 1.2 points; Questionable, plays 71% of the time". `marts/player_claims` (append-only, written by the daily pass) records each claim; when a player's status changes to Out between two daily snapshots, the claim is graded against the market's move in that window (`market_history`, ADR 0024), and at season's end against the margin residual. Graded claims show on the tracker beside strong calls, with the frame that most values are under a point. When the feature is promoted, the quarterback what-if generalises to these players.
- **Pages:** the game's Injuries tab leads with a `FormationMap` (the 11 starters, each sized by value lost) over the list; the team page gets an availability panel (key players by value, status, our status-to-play rate, value at risk). Every number carries the `ReliabilityBadge` once M23.8b ships.
- **New sources** in the registry: `stats_player` (weekly), `snap_counts`, `players`, `pfr_advstats` (week pass, rush, rec, def), `contracts`, `draft_picks`; `curate` keeps the play-by-play's player-id columns. Next Gen Stats ships no parquet (csv.gz only) and waits.
- **Parked, with their trigger:** with/without splits and player cards (after the claims have a season of grades), props (a credit plan and the Odds API's redistribution terms), a lineup plus-minus on participation (offseason experiment).

## Point-in-time rules
- A week-W value uses games through W−1; season-summary rows (NGS week 0, full-season tables) are never read; a leakage test per model.
- Injury status is the last daily snapshot before `known_as_of`, never the post-game report; snap counts for W−1 arrive about a day after the game, so a Monday build may lack Monday night's.
- Participation trains the quality priors on 2016–2025 and is never a live input.

## Consequences
- Four days of work in four day-sized PRs, and the first real use of M23's ledger and SQL runner by another milestone; M24's screening waits on M23 phase 0 (about two days), its ingests don't.
- The public record gains a new kind of claim, graded by the market's move; it will show that most non-quarterback absences move a line by under a point, which is the honest finding.
- Licences for PFR- and OTC-derived data are unconfirmed; the site shows derived values, not those tables.
- Files M24 owns: the registry, `ingest.py`, `curate.py`, `features/availability.py`, `swings.py`, the Injuries tab, the team availability panel. Shared and sequenced with M23: `candidates.py`, `groups.py` (only at the bump), additive `site.py` sections.

## Measured

**M24.0, the sources (2026-11-08, local data).** Nine curated tables, built in under 3 seconds from the raw files: `player_weeks` 485,478 rows (1999–2026), `snap_counts` 335,997 (2013–2026; the 2012 file is empty upstream), PFR advanced by week 2018–2026 (pass 5,704, rush 19,428, rec 37,671, def 65,843), `players` 24,867, `contracts` 53,624, `draft_picks` 12,927. The crosswalk: 99.8% to 100% of snap-count rows find a gsis id through `players` in every season (target 95%), and 99.98% of PFR defense rows. The plays table now carries 16 player columns; receiver ids are present on every completed pass back to 2010.

**M24.1, status to play (2016–2025 regular season, final report, players who had at least a quarter of their unit's snaps in an earlier game that season; 90% Wilson intervals).** Counting every listed player instead mixed availability with role: healthy backup quarterbacks never take a snap, which read as "healthy QBs play 82%".

| Final status | Listed player-weeks | Played |
|---|---|---|
| Out | 7,673 | 0.0% |
| Doubtful | 1,265 | 0.9% (0.6 to 1.5) |
| Questionable | 11,706 | 70.4% (69.7 to 71.1) |
| No status (listed in practice only) | 23,490 | 95.4% (95.2 to 95.6) |

Questionable by group: linebackers 74.9%, defensive line 74.3%, wide receivers 73.2%, tight ends 72.8%, offensive line 69.2%, running backs 69.0%, defensive backs 65.4%, **quarterbacks 50.4% (45.4 to 55.3, n = 270)**. PFF's often-quoted 73% for Questionable sits a little above ours overall, and a Questionable quarterback is a coin flip.
