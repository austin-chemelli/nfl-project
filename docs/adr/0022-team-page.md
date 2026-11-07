# ADR 0022: The team page

Status: accepted 2026-11-06 (Austin). Builds on ADR 0021 (the staff table, the study, `site/team/<code>.json`), ADR 0017 (one answer first, tabs) and ADR 0019 (League). Tasks: M18.

## Context
Austin wants one place for the state of a team: how it's doing, who coaches it and who really calls plays, what its tendencies are and what to expect from them, reached from any game preview. PR #26 writes the staff and tendency data; nothing reads it. A reader today has to assemble a team from the League panel, the Similar tab and the game page.

What the data allows (ADR 0021): weekly tendencies give "so far vs expected"; charted measures (personnel, coverage, time to throw, pressure) are a prediction until the spring drop. Predictions are rough: a typical miss is 16 to 25 percentile points, and several situations are no better than guessing the league middle. The page has to show that, not hide it.

## Options
1. **Data.** (a) One new per-team file holding everything. (b) The small `team/<code>.json` for staff and tendencies, plus the `teams.json`, `league.json` and `similar.json` the League page already loads. (a) duplicates three files and their freshness; (b) costs nothing new in the pipeline, and those files total about 60 KB compressed.
2. **Tabs.** (a) Overview · Staff · Tendencies · Games. (b) One long page. ADR 0017 settles this for (a).
3. **Drawing a prediction.** (a) `RangeRow`, built for a season value and a game value on raw rates. (b) `Dumbbell`, built for two teams. (c) A new row on the percentile scale with an expected range. Neither (a) nor (b) has a range, and the range is the honest part.
4. **Reaching the page.** (a) A nav item. (b) No nav item, links only. Coaches and Build are hidden, so the live nav has five items and a sixth fits. Austin wants it there.
5. **Links on slate cards.** (a) Make each team code a link inside the card. (b) Leave cards alone. A card is one big link to its game, so (a) means nested links or a stretched-link rebuild, and a small target inside a large one on a phone. The game page is one tap away.

## Decision
- **`/team/:code`**, case-insensitive, old franchise codes go to the current one, an unknown code is the not-found page. A team picker in the header. **Nav item "Teams"** to `/team`, a list of all 32 by division. League's "Teams" tab becomes "Team charts" so two things don't share a name; `?tab=teams` stays.
- **Data 1(b).** Each file failing or missing only removes what needs it (ADR 0019's rule).
- **Tiles** (statements, pure functions in `pages/team/summary.ts`): playoff chance, who calls the offense, who calls the defense, furthest from expected, next game. A tile that can't be stated honestly is left out.
- **Tabs:** Overview (default) · Staff · Tendencies · Games, on `?tab=`.
- **`ExpectRow`**, a new chart row: the league's 0 to 100 percentile scale with its ends named ("less" and "more", or "shorter" and "longer"), the expected range as a band, a hollow dot at expected, a filled team-color dot at so far, and the value and rank printed at the row end. No red or green: a tendency isn't good or bad.
- **Verdicts are plain and bounded:** inside the range is "as expected"; outside is "more" or "less than expected". A `weak` row says "rough guess", gets no verdict, and sorts below the others. A row with no measured range shows the team's last season alone.
- **Charted measures** sit in their own block, "What to expect", as predictions. When the spring drop lands, the same rows gain the filled dot.
- **Staff evidence is visible:** a confirmed caller links to the source; an unconfirmed unit reads "Runs the offense · play-caller not confirmed". The rule stays in the data (ADR 0021), so the page can't break it.
- **Links** through one `TeamLink`: the game header, the game page's team-named sections, League's Odds, Standings, Panel, Similar and Compare. Slate cards stay as they are.
- **Ships in two PRs:** the page first, reachable by URL so Austin can judge it; the nav item and links after he's happy, since those are what launch it.

## Consequences
- The team page becomes the home for what the Coaches page's team view did. M17.9 cuts that view; the coach view stays for one person across teams.
- A new page to keep current: its data is rebuilt on every site build, but a staff change needs a person to confirm it (M17.4).
- The Overview depends on three League files, so a change to those contracts now reaches two pages.
- Risk: readers take "expected" as a forecast. The range, the "rough guess" label and a `FinePrint` are the guard, and the site walk checks it.
- Risk: the page grows. Not in v1: comparing two teams, a user's own line, past seasons of a team, charts of a caller across seasons (coach view), and news (review §12).

## Review changes (2026-11-06)
- A situation is a claim about the past, so "same play-caller as last season" and "has called plays before" need a confirmed earlier spell (ADR 0021's rule). The unconfirmed label still picks the blend.
- The band is the typical miss, not a likely range: about half of all rows land outside it. The tile and the line above a chart need 1.5 misses (`NOTABLE`).
- A unit that changed callers this season gets no verdicts, a line saying who called which weeks, and no tile.
- A row with no measured range shows the team's last season alone.
- A team's file, `teams.json` and `league.json` each only remove what needs them; the picker comes from the static team list.

## Revised after Austin's look (2026-11-07)
- **Tendencies show the inputs, not a blend.** The expected value and its typical-miss band read as abstract. Each row now draws this season (a dot), the play-caller's own past (a diamond) and the team's last season (a triangle) against the league average (a dashed line), with a tag saying which this season matches. Charted measures with no season yet carry "watch the caller" or "watch last year" where the study backs one. `ExpectRow` became `TendencyRow`; the "furthest from expected" tile became "biggest change" from last season.
- **Coach profiles on Staff.** "In the numbers" is computed: a habit shows when every past season sat on the same side of the league. "Known for" and the coaching tree come from reporting: research agents drafted them, a second pass kept only what each cited page says, and anything about who calls plays is left out so the staff table's evidence rule stays the only source of that claim. 86 current coaches have one.
- **Nav.** "Teams" sits after League; League's tab became "Team charts".

