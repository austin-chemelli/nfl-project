You write the game-level block of a neutral NFL game preview record, using only the numbered facts below.

Game: $away_full ($away) at $home_full ($home), $season week $week, kickoff $kickoff_date (UTC), $venue.
Home team: $home_full ($home), playing at $venue. Away team: $away_full ($away), the visitors.

Team summaries already written:
- $away: $away_summary
- $home: $home_summary

Facts (id [category] (site, published date) text):
$facts

Fill the fields:
- `matchup_notes` (0 to 5): what analysts say about how these two teams match up ("their pass rush against a backup tackle", "expected shootout"). Cite `fact_ids` for each. Prefer points that several facts from different sites make.
- `consensus_narrative`: 2 or 3 neutral sentences on the week's story for this game.
- `public_pick`: "home" or "away" if a fact says most public bets are on that side, "none" if a fact says the public is split, null if no fact covers it.
- `public_bet_pct_home`: the share of bets on $home ($home_full) as a number from 0 to 1, only when a fact states that percentage; then put that fact's id in `public_bet_fact_id`. Otherwise both null.
- `upset_buzz` (0 to 1): how much the coverage talks about an upset.
- `weather_concern` (0 to 1): 0 dome or mild, 0.5 wind 15+ mph or rain, 1 severe. Base it on weather facts; 0 if there are none.

Rules:
- Use only these facts. Every number you write must appear in a fact you cite.
- Neutral description of the coverage: no picks, no predictions of your own.
- Get home and away right: $home_full is at home, $away_full is visiting.
- Cite facts by their exact id, e.g. "F12".
