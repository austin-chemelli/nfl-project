---
name: nfl-narrative
description: Research one NFL week's games on the web (injuries, QB status, beat-writer news, public betting percentages, weather) and produce validated narrative records for the nfl-project pipeline. Use when Austin asks to run the narrative research for a season/week or game, e.g. "/nfl-narrative 2026 8" or "/nfl-narrative 2026 8 2026_08_BAL_BUF".
---

# nfl-narrative

You are the development-time stand-in for the pipeline's narrative extraction job. You do the
same research the Sonnet API job will do, and produce records in the same contract, so the two can
be compared later. The record is the product; the pipeline never reads your prose.

Arguments: `<season> <week> [game_id ...]`. No game ids = every game of the week.

## Rules (the same ones the API job has)

1. **Sources only from the last 10 days and before now.** Each claim carries the page URL and its
   published date. If a page has no date, say so (`published_at: null`) and use `confidence: low`.
2. **No numbers that aren't in a source.** Ratings (`sentiment`, `hype`, ...) are your judgment,
   but every *fact* (who is out, who starts, public percentages, weather) needs a claim.
3. **Unknown means null, not a guess.** `public_bet_pct_home` is null unless a consensus page gave
   a number. `qb_status` is 2 when you could not establish the starter.
4. **Neutral summaries.** No hot takes, no predictions. Describe what the week's coverage says.
5. **Log every query** in `searches`, in the order you ran them.
6. **Never fabricate a URL.** Only cite pages you actually opened (WebFetch) or that a search
   result returned with that exact URL.
7. **Stamp honestly.** `known_as_of` is the UTC time you finished the record. It must be before
   kickoff. `producer: "claude_code"`, `model: "claude-code"` plus the model you are running as if
   you know it (e.g. `"claude-code/opus-5.5"`).

## Steps

1. `cd ~/dev/nfl-project && uv run nfl narrative slate <season> <week>` to get the games, kickoffs
   (UTC), venues, QBs, coaches and the current line. `uv run nfl narrative example` prints a
   complete valid record if you need the shape.
2. For each requested game, run searches (WebSearch), then open the pages you will cite (WebFetch).
   Typical set, adapt as needed:
   - `<Away full name> injury report week <W> <season>` and the same for the home team
   - `<Team> <QB name> status` only if the QB is on the report or the slate shows a change
   - `<Team> news` for each team (beat writers: coaching changes, locker-room stories, motivation)
   - `<Away> vs <Home> week <W> preview`
   - `<Away> <Home> public betting percentages` (Action Network, Covers, VSiN consensus pages)
   - `<Stadium city> weather <game date>` for outdoor games only
3. Fill one record per game. Field guide:
   - `qb_status`: 0 healthy named starter; 1 questionable, limited in practice, playing hurt, or a
     starter in his first few starts for the team; 2 backup starting, or unknown.
   - `injury_impact`: 0 nothing notable; 1 a rotational starter or two; 2 a key starter (OT, CB1,
     WR1, EDGE) out; 3 multiple key starters or the QB out.
   - `sentiment` −1..1: tone of the week's coverage about the team (not about the matchup).
   - `hype` 0..1: how much national coverage the team is getting this week.
   - `coaching_turmoil` 0..1: hot seat, coordinator fired, public criticism of play-calling.
   - `motivation` −1..1: −1 eliminated/tanking, 0 ordinary, +1 must-win/playoff clincher/rivalry.
   - `revenge` / `lookahead`: true only when coverage explicitly frames it that way.
   - `upset_buzz` 0..1: how much the coverage is talking about the underdog winning.
   - `public_pick`, `public_bet_pct_home`: from a consensus page; null when not found.
   - `weather_concern` 0..1: 0 dome/mild; 0.5 wind 15+ mph or rain; 1 severe.
4. Write each record to the scratchpad as `<game_id>.json` and run
   `uv run nfl narrative ingest <path>`. Fix validation errors (dates, ranges, team codes) and
   re-run until it stores. Then `uv run nfl features --families narrative`.
5. Report: games done, claims per game, anything you could not establish, and total searches.
   Note any source that looked unreliable.

## Scope

Development and testing only. The production path is the API job (`nfl.llm` M6.2) on the Console
key; never wire this skill into a scheduled run.
