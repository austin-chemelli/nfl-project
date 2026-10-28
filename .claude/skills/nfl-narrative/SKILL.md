---
name: nfl-narrative
description: Research one NFL week's games on the web (injuries, QB status, beat-writer news, scheme and matchup analysis, public betting percentages, weather) and produce validated narrative records (schema v2) for the nfl-project pipeline. Use when Austin asks to run the narrative research for a season/week or game, e.g. "/nfl-narrative 2026 8" or "/nfl-narrative 2026 8 2026_08_BAL_BUF".
context: fork
agent: general-purpose
model: sonnet
background: false
---

# nfl-narrative

You are the development-time stand-in for the pipeline's narrative extraction job. You do the
same research the Sonnet API job will do, and produce records in the same contract (schema v2,
prompt `narrative_v2`), so the two can be compared later. The record is the product.

Arguments: $ARGUMENTS (format: `<season> <week> [game_id ...]`; no game ids = every game of the week).
Work in `~/dev/nfl-project`.

## Rules (the same ones the API job has)

1. **Sources only from the last 10 days and before now.** Each claim and note carries the page URL;
   claims also carry the published date (or `published_at: null` with `confidence: low`).
2. **No numbers that aren't in a source.** Ratings (`sentiment`, `hype`, …) are your judgment, but
   every *fact* (who is out, who starts, public percentages, weather, "blitzes on 40% of downs")
   needs a cited source.
3. **Unknown means null or empty, not a guess.** `public_bet_pct_home` is null unless a consensus
   page gave a number. `qb_status` is 2 when you could not establish the starter. Empty lists are fine.
4. **Neutral writing.** Describe what the week's coverage says; no picks, no hot takes.
5. **Log every query** in `searches`, in order.
6. **Never fabricate a URL.** Cite only pages you opened (WebFetch) or that a search returned with
   that exact URL.
7. **Don't stamp the time.** `ingest` sets `known_as_of` from the clock. You may fill `known_as_of`
   with your best estimate (it's kept as `reported_finished_at`); it must still be before kickoff.
   `producer: "claude_code"`, `model: "claude-code/<model you are running as>"`.

## Steps

1. `uv run nfl narrative slate <season> <week>`: games, kickoffs (UTC), venues, QBs, coaches, the
   current line. `uv run nfl narrative example` prints a complete valid v2 record.
2. For each game, search (WebSearch) and open what you'll cite (WebFetch). Typical set, adapt:
   - `<Away full name> injury report week <W> <season>`, same for home; practice reports
   - `<Team> <QB> status` only if the QB is on the report or the slate shows a change
   - `<Team> news` for each team (beat writers: coaching, locker room, motivation, quotes)
   - **Scheme and form**, per team: `<Team> defense blitz rate coverage <season>`,
     `<Team> offense run game play-action trends`, `<Team> defense struggling against`,
     film-breakdown pieces (The Athletic snippets, team-site film reviews, PFF/Sharp Football
     articles, local outlets). Look for what the unit has been *doing lately* and whether it works.
   - **Matchup**: `<Away> vs <Home> week <W> preview`, `<Away> <Home> matchup breakdown`, `keys to
     the game`. Look for points several outlets agree on ("shootout", "their pass rush against a
     backup tackle", "can't stop the run").
   - `<Away> <Home> public betting percentages` (Action Network, Covers, VSiN consensus pages)
   - `<Stadium city> weather <game date>` for outdoor games
3. Fill one record per game.
   - **Per team `summary`**: a short paragraph (3–5 sentences): where the team stands this week:
     results, who's missing and what that changes, what the coach said, the mood.
   - **Per team `notes`** (3–8 bullets): one concrete item each, with `kind` (injury / coaching /
     scheme / form / other), `impact` for this team (−2 hurts a lot … +2 helps a lot), `source_url`.
     E.g. "Starting LT out; rookie makes first start against a top-5 pass rush" (injury, −2).
   - **Per team `scheme_trends`** (0–4): `unit` offense/defense, the `trend` in plain words
     ("blitzing on third down far more over the last three weeks"), `working` true/false/null per
     the coverage, `sources` (all URLs that describe it).
   - **Game `matchup_notes`** (0–5): what analysts say about how the teams match up. `support` =
     how many *independent outlets* say it (syndicated copies of one article count once), and
     `sources` lists each of them. Prefer points with support ≥ 2.
   - Ratings: `qb_status` 0 healthy starter / 1 questionable, limited, or new / 2 backup or
     unknown; `injury_impact` 0 nothing notable / 1 a role player or two / 2 a key starter (OT,
     CB1, WR1, EDGE) / 3 several key starters or the QB; `sentiment` −1..1 (coverage tone);
     `hype` 0..1 (national attention); `coaching_turmoil` 0..1; `motivation` −1..1; `revenge` /
     `lookahead` only when coverage explicitly says so; `upset_buzz` 0..1; `weather_concern` 0..1
     (0 dome or mild, 0.5 wind 15+ mph or rain, 1 severe).
   - `claims`: the key facts, each with source, date, confidence (as v1).
4. Write each record to a scratch file `<game_id>.json` and run
   `uv run nfl narrative ingest <path>`. Fix validation errors and re-run until it stores. Then
   `uv run nfl features --families narrative` and `uv run nfl site` (the Game page shows it).
5. Report back: games done; per game the counts of notes, scheme trends, matchup notes (with their
   support) and claims; what you couldn't establish; total searches; any unreliable source.

## Scope

Development and testing only. The production path is the API job (`nfl.llm`, M6.2) on the Console
key; never wire this skill into a scheduled run.
