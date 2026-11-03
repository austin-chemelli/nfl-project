You write the scheme trends for one team in a neutral NFL game preview record: what its offense and defense have been doing this season and how well, using only the numbered facts below.

Game: $away_full ($away) at $home_full ($home), $season week $week.
This block is for: $team_full ($team). Opponent: $opp_full ($opp).

Facts about scheme, matchups and form (id [category, team] (site, published date) text):
$facts

Fill `scheme_trends` (0 to 4, at most 2 per unit): `unit` offense or defense, the `trend` in plain words, `working` true or false when the facts say whether it produces results (else null), `fact_ids` (1 to 4).
- A trend is about how a unit plays: tendencies (run rate, blitz rate, coverage, play-action), efficiency and rankings (EPA per play, yards per play, pressure rate, explosive plays allowed), and how that changed lately. Combine facts from different sites about the same unit into one trend and cite them all.
- Only $team's units, this season. Not a newly acquired player's numbers from his old team, not one player's stat line.
- Prefer [scheme] and [matchup] facts; a [form] fact may support a trend but not be its only source.

Examples (another game, invented; form and depth only, never reuse their content):
Good: {"unit": "defense", "trend": "Blitzes on 38% of dropbacks, third most, but ranks 25th in EPA per dropback because the blitzes leave cornerbacks alone deep.", "working": false, "fact_ids": ["F12", "F40"]}
Good: {"unit": "offense", "trend": "Leans on the run (52% of plays, most in the league) and play-action off it, and is 4th in EPA per play.", "working": true, "fact_ids": ["F7", "F22", "F23"]}
Bad: {"unit": "defense", "trend": "Aidan Hutchinson has 9 sacks.", ...} (one player's stat line, not how the unit plays)

Rules:
- Use only these facts. Every number and name must be in a fact you cite. Never compute new numbers.
- Each trend is one complete sentence under 220 characters.
- Cite facts by their exact id, e.g. "F12". Empty is fine if the facts say nothing about how a unit plays.
