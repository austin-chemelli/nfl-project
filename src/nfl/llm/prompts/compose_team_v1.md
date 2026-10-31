You write one team's block of a neutral NFL game preview record, using only the numbered facts below.

Game: $away_full ($away) at $home_full ($home), $season week $week, kickoff $kickoff_date (UTC).
Home team: $home_full ($home). Away team: $away_full ($away).
This block is for: $team_full ($team), the $side team. Opponent: $opp_full ($opp).
Quarterback who started $team's most recent game (schedule data; may be a backup who filled in): $qb_name.

Facts (id [category] (site, published date) text):
$facts

Fill the fields:
- `notes` (3 to 8): one concrete item each about $team this week. `kind` is injury, coaching, scheme, form or other. `impact` is the effect on $team: -2 hurts a lot, -1 hurts, 0 neutral, +1 helps, +2 helps a lot. `fact_ids` lists the ids of the facts it rests on (at least one).
- `scheme_trends` (0 to 4): what $team's offense or defense has been doing lately, in plain words, with `working` true or false when the facts say whether it produces results, else null. Only from facts about scheme or tactics. Cite `fact_ids`.
- `key_absences`: players out or doubtful, as "Name (POS, Status)".
- `qb_name`: the quarterback the facts say will start THIS game (a starter returning from injury counts). Only if no fact says, use the most recent starter above.
- `qb_status`, for that quarterback: 0 healthy starter, 1 questionable, limited, or returning from injury, 2 a backup starts or the starter is unknown. `qb_name`, `qb_status`, `injury_impact` and the notes must agree with each other.
- `injury_impact`: 0 nothing notable, 1 a role player or two, 2 a key starter out (OT, CB1, WR1, EDGE), 3 several key starters or the QB.
- `sentiment` (-1 to 1): the tone of the coverage. `hype` (0 to 1): how much national attention. `coaching_turmoil` (0 to 1). `motivation` (-1 nothing to play for, 1 must-win).
- `revenge` and `lookahead`: true only if a fact says so.
- `summary`: 3 to 5 neutral sentences on where $team stands this week: results, who is missing and what it changes, what the coach said, the mood.

Rules:
- Use only these facts. If something isn't in them, leave it out (empty lists are fine).
- Every number you write must appear in a fact you cite. Never compute new numbers.
- Neutral description of the coverage: no picks, no predictions of your own.
- Cite facts by their exact id, e.g. "F12".
