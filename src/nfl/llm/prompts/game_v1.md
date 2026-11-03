You write the game-level block of a neutral NFL game preview record, using only the numbered facts below.

Game: $away_full ($away) at $home_full ($home), $season week $week, kickoff $kickoff_date (UTC), $venue.
Home team: $home_full ($home), playing at $venue. Away team: $away_full ($away), the visitors.

Team summaries already written:
- $away: $away_summary
- $home: $home_summary

Facts about scheme, matchups, betting action, form and the game (id [category, team] (site, published date) text):
$facts

Fill the fields:
- `consensus` (2 or 3 sentences, each with the `fact_ids` it rests on): the week's story for this game as the coverage tells it: where each team stands and the one or two storylines previews return to. Each sentence must make sense on its own.
- `public_pick`: "home" or "away" if a fact says most public bets are on that side, "none" if a fact says the public is split, null if no fact covers it.
- `public_bet_pct_home`: the share of bets on $home ($home_full) as a number from 0 to 1, only when a fact states that percentage; then put that fact's id in `public_bet_fact_id`. Otherwise both null.
- `upset_buzz` (0 to 1): how much the coverage talks about an upset.
- `weather_concern` (0 to 1): 0 dome or mild, 0.5 wind 15+ mph or rain, 1 severe. Base it on weather facts; 0 if there are none.

Example consensus (another game, invented; form only):
[{"text": "Detroit (5-2) visits Green Bay (4-3) in a game that could decide the NFC North lead.", "fact_ids": ["F3", "F9"]},
 {"text": "Previews focus on Detroit's rookie left tackle against the Packers' pass rush.", "fact_ids": ["F4", "F31"]}]

Rules:
- Use only these facts and the team summaries. Every player, condition and number must be in a fact you cite (or in a team summary). Never compute new numbers.
- Each sentence is complete and under 220 characters.
- Never state the point spread, the total, a moneyline, or who is favored. Where the public or sharp money is going is fine.
- Plain, neutral wording: no slang, no picks or predictions of your own.
- Get home and away right: $home_full is at home, $away_full is visiting.
- Cite facts by their exact id, e.g. "F12".
