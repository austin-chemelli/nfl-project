# ADR 0017: Site information architecture: one answer first, detail behind tabs

Status: accepted 2026-11-03 (plan; tasks M10.x). Decided with Austin after clicking through the site with the retrospective added.

## Context
The site has the data but reads as a wall. A finished game's page stacks 21 sections, each with an intro paragraph, hover help, a chart and a table; the slate is a 10-column grid; the tracker is seven sections under a three-sentence lede. Nothing answers "what's the one thing about this game?" before the detail starts, and charts auto-scale to their own values, so a small gap can fill a row and nothing says whether a number is good. Austin wants less text and more visuals, gradual clicking rather than everything on one screen, and numbers that carry their own context. The content of the sections is right and stays; this is about arrangement and framing. The Streamlit UI is disposable (ADR 0009) and is not changed.

## Options
1. **Tabs with a summary strip (chosen).** Every page opens with 3–5 tiles that each state one thing; the detail lives behind URL-addressable tabs, one on screen at a time.
2. **Guided story.** Each page is a sequence of full-width frames, one visual and one sentence each, with next/prev. Calmest, but linear (finding the injuries means stepping through), highest effort, and scroll-driven pages are a known trap on phones.
3. **Dashboard tiles with drill-down panels.** A grid of small charts; clicking one opens a side panel. Good for scanning, but a grid of tiny charts reads as a wall again, which is what the slate already is.

## Decision
- **One answer first.** Every page and every tab starts with a *summary strip*: 3–5 tiles, each a number or a two-word verdict with a short sub-line, linking to the tab that explains it. Amended 2026-11-03 after Austin's first look (the first tile sets restated numbers instead of answering questions): a finished game's strip is result (upset, favorite won, or toss-up within 5 points of even), approaches right (with the best read), played like ("about even" within 5 points), swing plays (net, with the pure-luck part), and the biggest surprise (the unit furthest from its season level, measured against the league band). A pregame strip is the pick, versus the market ("other side", "in line", or points apart), the approaches' split, the biggest factor behind the pick, and the key absence (out or doubtful this week, ranked by position; long-term lists left out), or the biggest edge when no one is out.
- **Tabs, synced to the URL** (`?tab=`), so the back button and shared links work. Game page: Retro (default when the game is final) · Forecast (default otherwise) · Matchup · Injuries & news. Tracker: This season · Backtest · Calibration · Disagreements · Paper bets. Nothing is removed, only regrouped.
- **Text budget.** Per section: a title, at most one sentence of lede, method help on hover, legends once per chart kind. Caveats go into one collapsed fine-print block per page, not a footnote per section.
- **Every number gets a frame.** Where a league distribution exists, a value is drawn on a band (the league's 10th to 90th percentile of team season-to-date values) with the league average as a tick, and the value is printed at the row end, so nothing requires hover. Good/bad color only when the direction is unambiguous (not for style measures like pass rate over expected). The retro contract gains `league_lo`/`league_hi` per efficiency metric (additive; ADR 0015).
- **Visual before table.** Tables live behind "show the numbers"; the injury report is the one table that stays primary.
- **Quiet meta.** Kickoff, stadium, QBs and lock status become one muted line under the title; a finished game's score is the only loud header element.
- **Team colors as a thin accent only.** ADR 0011 bans logos, not colors. A thin bar in each team's primary color marks the team in headers and cards; charts keep the approach colors, and references stay gray. The 32 colors are a static map in the web app, not pipeline data.
- **Slate as matchup cards** on every screen size, each with the compressed approaches-vs-market strip (the same visual as the game page, so it is learned once) and one computed sentence; sortable by kickoff, disagreement or upset; the table remains as a `?view=table` option. The week recap is the page's summary strip.
- **Phone first for the slate and the game page**; tracker and build may stay desktop-leaning.

## Consequences
- New shared pieces: `Tabs`, `SummaryStrip`/`Tile`, `FinePrint`, a `RangeRow` chart, `ProbStrip`, a team-color accent. Pages compose these; chart kit and tokens are unchanged.
- The pattern is set on one game page first and reviewed with Austin before the slate and tracker follow (M10.3 before M10.4–5).
- Adding fields to retros needs a rebuild: `SCHEMA_VERSION` becomes "2" and the builder treats a different stored schema version as stale, the same as a changed play hash.
- The tendencies dumbbells get the same league band later (from `tendencies.parquet`); not in this milestone.
- Risk: a tab can still be busy. The text budget is the guard, and the review step after M10.3 is where it is checked.

## Amendment 2026-11-04: color follows the team, and the site gets some color

Austin, after a day with the round 2 game page: the red and blue bars made him check the legend to know who was who, and in dark mode the site read as bland. This replaces "team colors appear as a thin accent bar only".

- On a page about two teams, color means the team: bars, dots, a wash in the banner, tile edges. Approach colors stay on everything about approaches. Red and blue stay where they mean better and worse or helped and hurt, not a team.
- Brand colors don't work directly as chart marks: the Ravens' purple disappears on a dark page and four teams share one navy. `web/src/lib/teamColors.ts` fits each color to each theme and picks a pair per matchup, keeping a team's main color where it can (a lightness step first, a secondary color after). A test holds all 992 matchups to 3:1 on the page and to a separation floor for normal and for red-green colorblind vision.
- The surfaces take a slight cool tint and one brand gradient sits under the header, so pages that aren't about teams have some color too. Text stays in the text tokens, never a team's color.
- Logos stay banned (ADR 0011).

