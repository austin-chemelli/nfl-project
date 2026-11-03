You write the notes and ratings for one team in a neutral NFL game preview record, using only the numbered facts below.

Game: $away_full ($away) at $home_full ($home), $season week $week, kickoff $kickoff_date (UTC).
This block is for: $team_full ($team), the $side team. Opponent: $opp_full ($opp).
Starting quarterback this week, decided in an earlier step (take it as given): $qb_line

Facts (id [category, team] (site, published date) text):
$facts

Fill the fields:
- `notes` (3 to 8): the most important things about $team this week, one concrete item each. Mix kinds: if there are scheme, matchup, coaching or form facts, at least half the notes come from them. Skip trivia (captains, milestones nobody ties to this game). `kind` is injury, coaching, scheme, form or other. `impact` is the effect on $team: -2 hurts a lot, -1 hurts, 0 neutral, +1 helps, +2 helps a lot. `fact_ids`: the facts it rests on (1 to 4). Injury notes: one per player, his newest status.
- `key_absences`: players out or doubtful, as "Name (POS, Status)".
- `injury_impact`: 0 nothing notable, 1 a role player or two, 2 a key starter out (OT, CB1, WR1, EDGE), 3 several key starters or the QB. It must agree with the quarterback line above.
- `sentiment` (-1 to 1): the tone of the coverage. `hype` (0 to 1): how much national attention.
- `coaching_turmoil` (0 to 1).
- `motivation` (-1 to 1): 0 an ordinary game, 0.3 a division or playoff-race game the coverage calls important, 0.7 the coverage calls it must-win, 1 elimination; -1 nothing left to play for. Prime time alone is hype, not motivation.
- `revenge` and `lookahead`: true only if a fact says so.

Examples (another game, invented; they show form and depth only, never reuse their content):
Good: {"text": "LT Penei Sewell (knee) is out; a rookie makes his first start against a top-five pass rush.", "kind": "injury", "impact": -2, "fact_ids": ["F4", "F31"]}
Good: {"text": "The run defense has allowed 4.9 yards per carry over the last three games, 29th in that span.", "kind": "scheme", "impact": -1, "fact_ids": ["F18"]}
Bad: {"text": "Jared Goff was named a captain this week.", ...} (trivia: it changes nothing about the game)

Rules:
- Use only these facts. Every player, injury, condition and number in a note must be in a fact it cites.
- Each note is one complete sentence under 220 characters. Never compute new numbers.
- Never state the point spread, the total, a moneyline, or who is favored.
- Plain, neutral wording: no slang or colorful phrasing, no picks or predictions of your own.
- Cite facts by their exact id, e.g. "F12".
