You decide who starts at quarterback for the $team_full ($team) in this game, using only the numbered facts below.

Game: $away_full ($away) at $home_full ($home), $season week $week, kickoff $kickoff_date (UTC). Today is $today.
Quarterback who started $team's most recent game (schedule data; may be a backup who filled in): $qb_name.

Facts about $team's quarterbacks, newest first (id [category, team] (site, published date) text):
$facts

Fill the fields:
- `qb_name`: the quarterback who will start THIS game according to the newest reports. A starter returning from injury who is cleared, a full participant, expected to play, or off the injury report is the starter. "X will start if Y can't play" does not make X the starter, and that a backup started recent games does not make him this week's starter. When reports conflict, the newest one wins. If no fact is about this week's starter, the most recent starter above starts. null only if the facts say the starter is undecided.
- `qb_status`: 0 a healthy starter with no injury this week; 1 the starter is questionable, limited, or returning from an injury; 2 a backup starts because the usual starter is out, or the starter is undecided.
- `fact_ids` (0 to 4): the ids of the facts that say who starts, newest first. Empty only when no fact is about this week's starter.

Rules:
- Use only these facts and the schedule line above.
- Cite facts by their exact id, e.g. "F12".
