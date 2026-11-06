"""The static division map (ADR 0019)."""

import polars as pl
import pytest

from nfl.features import store
from nfl.league.divisions import DIVISION_TEAMS, DIVISIONS, conference_of, division_of
from tests.conftest import DATA


def test_map_shape():
    assert len(DIVISIONS) == 32
    assert len(DIVISION_TEAMS) == 8 and all(len(v) == 4 for v in DIVISION_TEAMS.values())
    assert {c for c, _ in DIVISIONS.values()} == {"AFC", "NFC"}
    assert sum(c == "AFC" for c, _ in DIVISIONS.values()) == 16


def test_lookups_and_aliases():
    assert conference_of("KC") == "AFC" and division_of("KC") == "AFC West"
    assert division_of("OAK") == "AFC West" and division_of("SD") == "AFC West"
    assert division_of("STL") == "NFC West" and conference_of("STL") == "NFC"
    assert conference_of("XXX") is None and division_of("XXX") is None


@pytest.mark.skipif(
    not (DATA.curated_table("games")).exists(), reason="needs curated games (run nfl run-all)"
)
def test_matches_2026_div_game_groups():
    g = store.games_frame(DATA).filter((pl.col("season") == 2026) & (pl.col("div_game") == 1))
    if g.is_empty():
        pytest.skip("no 2026 schedule")
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    for h, a in g.select("home_team", "away_team").iter_rows():
        parent[find(h)] = find(a)
    groups: dict[str, set[str]] = {}
    for t in parent:
        groups.setdefault(find(t), set()).add(t)
    assert sorted(map(sorted, groups.values())) == sorted(map(sorted, DIVISION_TEAMS.values()))
