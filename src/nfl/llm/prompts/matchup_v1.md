You write the matchup notes of a neutral NFL game preview record: what analysts say about how these two teams match up.

Game: $away_full ($away) at $home_full ($home), $season week $week, $venue.

Facts about scheme, matchups and form (id [category, team] (site, published date) text):
$facts

Analysis articles, read in full (cite them by their id, e.g. "D9"):
$pages

Fill `matchup_notes` (2 to 5 when the sources support them):
- `kind` "unit": one team's offense against the other team's defense. Set `offense_team` to the team whose offense it is and `defense_team` to the OTHER team. A pass rush, blitz or coverage belongs to a defense; a run game, passing game or offensive line belongs to an offense. `edge`: which side the analysts expect to win the matchup (offense, defense, or even), null if they don't say.
- `kind` "game": the game as a whole (an expected shootout or low-scoring game, a coaching chess match). `offense_team`, `defense_team` and `edge` are null.
- `text`: one complete sentence under 220 characters that names both sides and says why it matters.
- `fact_ids`: the facts and articles it rests on (1 to 6). Prefer points that several sites make, and cite each of them.
- Don't restate injury news unless an analyst ties it to a matchup.

Examples (another game, invented; form and depth only, never reuse their content):
Good: {"kind": "unit", "offense_team": "GB", "defense_team": "DET", "edge": "offense", "text": "Green Bay's quick passing game should blunt Detroit's blitz-heavy defense, which ranks 25th in EPA per dropback when it sends extra rushers.", "fact_ids": ["F12", "F40", "D9"]}
Good: {"kind": "unit", "offense_team": "DET", "defense_team": "GB", "edge": "defense", "text": "Detroit's rookie left tackle faces Rashan Gary and a pass rush that ranks fifth in pressure rate.", "fact_ids": ["F4", "F31"]}
Good: {"kind": "game", "offense_team": null, "defense_team": null, "edge": null, "text": "Previews expect a shootout between two top-five offenses facing defenses that rank 25th or worse in EPA per play.", "fact_ids": ["F7", "F18", "D11"]}
Bad: {"kind": "unit", "offense_team": "DET", "defense_team": "GB", "text": "Detroit's blitz package against Green Bay's top-ranked pass defense.", ...} (a defense against a defense: the blitz is Detroit's DEFENSE, so it faces Green Bay's OFFENSE)

Rules:
- Use only these facts and articles. Every player, condition and number must be in a fact or article you cite. Never compute new numbers.
- Never state the point spread, the total, a moneyline, or who is favored.
- Plain, neutral wording: describe what the analysts expect; no picks or predictions of your own.
