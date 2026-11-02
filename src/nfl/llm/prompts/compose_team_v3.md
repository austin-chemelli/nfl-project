You write one team's block of a neutral NFL game preview record, using only the numbered facts below.

Game: $away_full ($away) at $home_full ($home), $season week $week, kickoff $kickoff_date (UTC).
Home team: $home_full ($home). Away team: $away_full ($away).
This block is for: $team_full ($team), the $side team. Opponent: $opp_full ($opp).
Starting quarterback this week, decided in an earlier step (take it as given): $qb_line

Facts (id [category, team] (site, published date) text):
$facts

Fill the fields:
- `notes` (3 to 8): one concrete item each about $team this week, in one sentence. Cover more than injuries: if there are scheme, matchup, coaching or form facts, at least half the notes come from them. `kind` is injury, coaching, scheme, form or other. `impact` is the effect on $team: -2 hurts a lot, -1 hurts, 0 neutral, +1 helps, +2 helps a lot. `fact_ids` lists the ids of the facts it rests on (at least one).
- `scheme_trends` (0 to 4): what $team's offense or defense has been doing lately and how well this season, in plain words; prefer unit rankings and efficiency (EPA, yards per play, pressure and blitz rates) over one player's numbers, and never a newly acquired player's numbers from his old team; with `working` true or false when the facts say whether it produces results, else null. Only from [scheme] or [matchup] facts; cite them in `fact_ids`.
- `key_absences`: players out or doubtful, as "Name (POS, Status)".
- The notes, `key_absences` and `injury_impact` must agree with the starting quarterback above; don't describe a backup as this week's starter unless that line says so.
- `injury_impact`: 0 nothing notable, 1 a role player or two, 2 a key starter out (OT, CB1, WR1, EDGE), 3 several key starters or the QB.
- `sentiment` (-1 to 1): the tone of the coverage. `hype` (0 to 1): how much national attention. `coaching_turmoil` (0 to 1). `motivation` (-1 to 1): 0 an ordinary game, 0.3 a division or playoff-race game the coverage calls important, 0.7 the coverage calls it must-win, 1 elimination; -1 nothing left to play for. Prime time alone is hype, not motivation.
- `revenge` and `lookahead`: true only if a fact says so.
- `summary` (3 to 5 sentences, each with the `fact_ids` it rests on): where $team stands this week. Start with the record and standing if a fact gives them, then who is missing and what it changes, how the offense and defense have been playing, what the coach said.

Rules:
- Use only these facts. Every player, injury, condition and number you write must be in a fact you cite for that sentence or note. If something isn't in the facts, leave it out (empty lists are fine).
- Never compute new numbers.
- Each note, trend and sentence is one complete sentence under 220 characters.
- Never state the point spread, the total, a moneyline, or who is favored: the site shows the betting market from its own data. Where the public or sharp money is going is fine.
- Plain, neutral wording: state records and standings as facts ("4-3, last in the AFC North"), no slang or colorful phrasing ("basement", "electric", "musical chairs"), no picks or predictions of your own.
- Cite facts by their exact id, e.g. "F12".
