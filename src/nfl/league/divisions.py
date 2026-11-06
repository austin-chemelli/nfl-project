"""The 32 current teams by conference and division (ADR 0019).

A static map: nothing else in the pipeline carries it (only the `div_game` flag, which the tests
check this against). Historical codes (OAK, SD, STL) resolve through TEAM_ALIASES; the web app reads
conference and division from teams.json, never from its own copy.
"""

from __future__ import annotations

from nfl.models.elo import TEAM_ALIASES

DIVISION_TEAMS: dict[str, tuple[str, ...]] = {
    "AFC East": ("BUF", "MIA", "NE", "NYJ"),
    "AFC North": ("BAL", "CIN", "CLE", "PIT"),
    "AFC South": ("HOU", "IND", "JAX", "TEN"),
    "AFC West": ("DEN", "KC", "LAC", "LV"),
    "NFC East": ("DAL", "NYG", "PHI", "WAS"),
    "NFC North": ("CHI", "DET", "GB", "MIN"),
    "NFC South": ("ATL", "CAR", "NO", "TB"),
    "NFC West": ("ARI", "LA", "SEA", "SF"),
}

# code -> (conference, division)
DIVISIONS: dict[str, tuple[str, str]] = {
    code: (name.split()[0], name) for name, codes in DIVISION_TEAMS.items() for code in codes
}


def _canon(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


def conference_of(team: str) -> str | None:
    d = DIVISIONS.get(_canon(team))
    return d[0] if d else None


def division_of(team: str) -> str | None:
    d = DIVISIONS.get(_canon(team))
    return d[1] if d else None
