You extract facts from one web page for an NFL game preview.

Game: $away_full ($away) at $home_full ($home), $season week $week, kickoff $kickoff_date (UTC). Today is $today.

List every fact on the page that matters for THIS game:
- injuries and practice or game status, with the status word exactly as written (out, doubtful, questionable, limited, did not practice, full participant, expected to start, ...)
- who starts at quarterback, and any doubt about it
- coaching news, quotes, locker-room mood, motivation and stakes
- recent form and results
- scheme: what an offense or defense has been doing lately and whether it is working
- matchup analysis: how the two teams match up, what analysts expect
- public betting percentages and line movement
- weather for the game

Rules:
- Use only what the page says. Never add knowledge of your own.
- One fact per item: a single plain sentence under 250 characters that names the player, unit or team.
- Copy numbers exactly as the page writes them. Never compute new numbers.
- `team` is the abbreviation of the team the fact is about ($away or $home), or "game" for the matchup, betting, weather or both teams.
- Skip other games, other teams, ads, navigation, and old news the page doesn't present as current.
- `confidence`: high = stated as fact (official injury report, a direct quote); medium = reported or expected; low = speculation or rumor.
- If the page has nothing about this game or these two teams, return an empty list.
