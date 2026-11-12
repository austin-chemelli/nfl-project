# ADR 0029: Visitor picks live in the browser, and one set of picks drives the slate and the playoff what-if

Status: accepted 2026-11-12 (Austin: idea (d) of `.notes/hub/plans/ideas-2026-11-10.md`, staged picks first; browser-only storage is the default taken for v1, decision 2 of that plan). Extends ADR 0015 (data published independently of the site), ADR 0019 (the league simulation).

## Context
Austin wants visitors to pick games next to the approaches (a reason to come back weekly) and, later, to decide games on the League page and watch playoff odds move. The site is static: Firebase Hosting plus JSON in a public bucket, no server and no accounts. Both features need the same thing, a winner per game chosen by the visitor, so they should share one store.

## Options
1. **Storage.** (a) `localStorage` in the visitor's browser: free, private, nothing sent anywhere; lost on another device or a cleared browser. (b) Accounts (Firebase Auth + Firestore): picks follow the visitor, a leaderboard becomes possible; brings sign-in, personal data, privacy and moderation work.
2. **What a pick is.** (a) The straight-up winner. (b) A side against the spread.
3. **Order.** (a) Picks first, the what-if after (it needs a TypeScript port of the simulation and tiebreaks). (b) Both in one round.

## Decision
1(a), 2(a), 3(a).

- One store, `web/src/lib/picks.ts`, key `nfl-picks-v1`: `{ [game_id]: { team, at } }`. A pick can be made, changed or cleared until kickoff and never after; a pick stamped at or after kickoff is never scored.
- The record compares the visitor with the headline approach and the market's favorite on exactly the finished games the visitor picked (ties count for nobody). Everything is computed in the browser from the published slates; no new data contract.
- The playoff what-if (M26.2+) reads the same store: a picked game is decided that way in the simulation, the rest are drawn from a chosen source (Student, market).

## Consequences
- No personal data, cost or moderation. Picks don't move between devices; the page says so.
- Accounts can come later without throwing this away: the stored shape can be uploaded once.
- Against the spread is left out: it needs a line frozen at the moment of the pick, and the what-if needs winners anyway.
- The what-if commits us to a TypeScript copy of `simulate.py`, `tiebreak.py` and `standings.py` (about 820 lines of Python) kept in parity by fixtures generated from the Python.
