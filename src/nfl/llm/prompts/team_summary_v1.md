You write the summary paragraph for one team in a neutral NFL game preview record.

Game: $away_full ($away) at $home_full ($home), $season week $week.
This block is for: $team_full ($team), the $side team. Opponent: $opp_full ($opp).
Starting quarterback this week (take it as given): $qb_line

Already written for $team (the summary pulls these together; it adds nothing they and the facts don't say):
$written

Facts (id [category, team] (site, published date) text):
$facts

Fill `summary`: 3 to 5 sentences, each with the `fact_ids` it rests on (1 to 4). In order: the record and standing if a fact gives them; who is missing and what it changes; how the offense and defense have been playing; what the coach said, if anything notable.

Example (another game, invented; form and depth only, never reuse its content):
[{"text": "Detroit is 5-2 and first in the NFC North after beating Tampa Bay 27-20.", "fact_ids": ["F3"]},
 {"text": "Left tackle Penei Sewell is out, so a rookie starts against a top-five pass rush.", "fact_ids": ["F4", "F31"]},
 {"text": "The offense is fourth in EPA per play behind a run-first plan, while the run defense has slipped to 29th over the last three games.", "fact_ids": ["F7", "F18"]}]

Rules:
- Every player, injury, condition, standing and number must be in a fact the sentence cites. Never compute new numbers.
- Each sentence is complete and under 220 characters, and makes sense on its own.
- Never state the point spread, the total, a moneyline, or who is favored.
- Plain, neutral wording: state records and standings as facts; no slang, no picks or predictions.
- Cite facts by their exact id, e.g. "F12".
