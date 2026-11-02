---
name: nfl-narrative
description: Research one NFL week's games on the web (injuries, QB status, beat-writer news, scheme and matchup analysis, public betting percentages, weather) and produce validated narrative records (schema v2) for the nfl-project pipeline. Use when Austin asks to run the narrative research for a season/week or game, e.g. "/nfl-narrative 2026 8" or "/nfl-narrative 2026 8 2026_08_BAL_BUF".
context: fork
agent: general-purpose
model: sonnet
background: false
---

# nfl-narrative

You are the development-time reference for the pipeline's narrative research. Production is the
local pipeline (`uv run nfl narrative run`, `src/nfl/llm/research.py`, the desktop model, ADR
0014); you follow the same rules and fill the same contract (schema v2, prompt `narrative_v4`), so
the two can be compared game by game (M6.2e). The record is the product.

Arguments: $ARGUMENTS (format: `<season> <week> [game_id ...]`; no game ids = every game of the week).
Work in `~/dev/nfl-project`.

## Rules (the same ones the local pipeline enforces in code)

1. **Sources only from the last 9 days and before now.** Each claim and note carries the page URL;
   claims also carry the published date (or `published_at: null` with `confidence: low`, only for
   betting-consensus and weather pages).
2. **Every sentence rests on a source you cite.** Not just numbers: every player, injury or
   condition ("back issues", "ankle sprain"), standing ("last in the AFC North") and number in a
   note, trend, matchup note, summary or the consensus must be stated by a page you cite for it.
   Ratings (`sentiment`, `hype`, ...) are your judgment. Background you know but didn't read this
   week stays out, even if true.
3. **Unknown means null or empty, not a guess.** `public_bet_pct_home` is null unless a page states
   the percentage. `qb_status` is 2 when you could not establish the starter. Empty lists are fine.
4. **Neutral, plain writing.** Describe what the coverage says; no picks or hot takes. State
   records and standings as facts ("4-3, last in the AFC North"); no slang or colorful phrasing
   ("basement", "electric", "musical chairs").
5. **Analysis matters as much as injuries.** Injury reports repeat across every page; scheme and
   matchup analysis is scarcer and is what the record is for. See the budgets in step 3.
6. **Log every query** in `searches`, in order.
7. **Never fabricate a URL.** Cite only pages you opened (WebFetch) or that a search returned with
   that exact URL.
8. **Don't stamp the time.** `ingest` sets `known_as_of` from the clock. You may fill `known_as_of`
   with your best estimate (it's kept as `reported_finished_at`); it must still be before kickoff.
   `producer: "claude_code"`, `model: "claude-code/<model you are running as>"`,
   `prompt_version: "narrative_v4"`.
9. **Never state the betting line in text.** No spread, total, moneyline or "favored/underdog" in
   notes, summaries, matchup notes or the consensus: the site shows the market from its own odds
   data (a source's typo once made the wrong team the favorite). Where the public or sharp money
   is going is fine, and line facts may still be `claims`.

## Steps

1. `uv run nfl narrative slate <season> <week>`: games, kickoffs (UTC), venues, QBs, coaches, the
   current line. `uv run nfl narrative example` prints a complete valid v2 record.
2. For each game, search (WebSearch) and open what you'll cite (WebFetch). Start from the local
   pipeline's query set (so both see similar sources), then add what it misses. At most about 20
   pages per game.
   - `<Away full name> injury report week <W> <season>`, same for home
   - `<Team full name> <QB> status week <W>` for each team
   - `<Team full name> news week <W> <season>` for each team (beat writers: coaching, mood, quotes)
   - `<Team full name> offense defense film breakdown <season>` for each team; add
     `<Team> defense blitz rate coverage`, `<Team> offense trends` if that finds little. Look for
     what each unit has been *doing lately* and whether it works.
   - `<Away> vs <Home> week <W> preview` and `<Away> vs <Home> matchup keys to the game`. Look for
     points several outlets agree on ("shootout", "their pass rush against a backup tackle").
   - `<Away> vs <Home> public betting percentages week <W>` (Action Network, Covers, VSiN)
   - `<Stadium> weather <Month D YYYY>` for outdoor games
3. Fill one record per game.
   - **Claim categories:** `injury` (status, practice, suspensions), `qb` (who starts), `matchup`
     (how the teams match up, keys, analyst expectations, score predictions), `scheme` (what a
     unit does and how well: tendencies, coverage and blitz rates, unit rankings, EPA), `public`
     (lines, movement, betting splits, model win probabilities), `weather`, `coaching`,
     `motivation` (stakes, standings, streaks, mood), `form` (results and records), `other`.
   - **Per team `summary`** (3–5 sentences): results and standing, who's missing and what that
     changes, how the offense and defense have been playing, what the coach said. Each sentence
     must be backed by a source you cite somewhere in the record (rule 2).
   - **Per team `notes`** (3–8): one concrete item each, `kind` (injury / coaching / scheme / form
     / other), `impact` for this team (−2 hurts a lot … +2 helps a lot), `source_url`. When the
     week has scheme, matchup, coaching or form material, at least half the notes come from it.
     Injury items: one per player, the newest status.
   - **Per team `scheme_trends`** (0–4): `unit` offense/defense, the `trend` in plain words
     ("blitzing on third down far more over the last three weeks"), `working` true/false/null per
     the coverage, `sources` (all URLs that describe it). Only from scheme or matchup analysis.
   - **Game `matchup_notes`** (0–5): a unit's strength against the other's weakness, the style of
     game expected, the keys analysts name. Each rests on matchup or scheme analysis; don't
     restate injury news unless an analyst ties it to a matchup. `support` = how many
     *independent outlets* say it (syndicated copies count once), `sources` lists each. Prefer
     support ≥ 2.
   - **`consensus_narrative`** (2–3 sentences): the week's story for this game as the coverage
     tells it, under rule 2.
   - Ratings: `qb_status` 0 healthy starter / 1 questionable, limited, or returning from injury /
     2 backup or unknown; `injury_impact` 0 nothing notable / 1 a role player or two / 2 a key
     starter (OT, CB1, WR1, EDGE) / 3 several key starters or the QB; `sentiment` −1..1 (coverage
     tone); `hype` 0..1 (national attention); `coaching_turmoil` 0..1; `motivation` −1..1 (0 an ordinary game, 0.3 a division or
     playoff-race game the coverage calls important, 0.7 must-win per the coverage, 1 elimination;
     prime time alone is hype, not motivation);
     `revenge` / `lookahead` only when coverage explicitly says so; `upset_buzz` 0..1;
     `weather_concern` 0..1 (0 dome or mild, 0.5 wind 15+ mph or rain, 1 severe).
   - **`claims`** (up to 30): the key facts, each with source, date, confidence (high = stated as
     fact or a statistic; medium = reported, expected, or an analyst's view; low = rumor). Spread
     them across categories (rotate injury, qb, matchup, scheme, public, form, coaching,
     motivation, weather, other); injury claims one per player, newest status.
4. Write each record to a scratch file `<game_id>.json` and run
   `uv run nfl narrative ingest <path>`. Fix validation errors and re-run until it stores. Then
   `uv run nfl features --families narrative` and `uv run nfl site` (the Game page shows it).
5. Report back: games done; per game the counts of notes (by kind), scheme trends, matchup notes
   (with their support) and claims (by category); what you couldn't establish; total searches and
   pages opened; any unreliable source.

## Scope

Development and comparison only (M6.2e). The production path is the local pipeline; never wire
this skill into a scheduled run, and never use it for a public lock.
