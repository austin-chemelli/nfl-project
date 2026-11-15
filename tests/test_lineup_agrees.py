"""The game page's lineups and its injury list never disagree (Austin 2026-11-15)."""

import json

import pytest

from nfl.config import get_paths
from nfl.site import lineup_conflicts


def _starter(slot, gid, name, status=None, depth=(), reserve=False, doubt=False):
    return {"slot": slot, "gsis_id": gid, "player": name, "status": status, "reserve": reserve,
            "doubt": doubt, "depth": list(depth)}  # fmt: skip


def _game(starters, injuries, spots=()):
    return {
        "injuries": injuries,
        "health": {"home": {"starters": starters}, "away": None},
        "lineups": {"home": {"offense": list(spots), "defense": []}, "away": None},
    }


INJ = [{"gsis_id": "a", "player": "A", "status": "Out"}, {"gsis_id": "b", "player": "B", "status": "Questionable"}]  # fmt: skip


def test_agreeing_lineup_has_no_conflicts():
    g = _game(
        [
            _starter(
                "SS",
                "a",
                "A",
                "Out",
                depth=[{"gsis_id": "b", "player": "B", "status": "Questionable"}],
            ),
            _starter("FS", "c", "C", "IR", reserve=True),  # a reserve list isn't on the report
            _starter(
                "CB", "d", "D", "Did not practice", doubt=True
            ),  # a practice doubt isn't either
        ],
        INJ,
        spots=[{"slot": "QB", "gsis_id": "e", "player": "E", "status": None}],
    )
    assert lineup_conflicts(g) == []


def test_a_starter_listed_out_but_drawn_healthy_is_a_conflict():
    g = _game([_starter("SS", "a", "A", None)], INJ)
    assert lineup_conflicts(g) == ["home SS: A shown None, report 'Out'"]


def test_a_backup_or_map_spot_with_the_wrong_status_is_a_conflict():
    g = _game(
        [_starter("SS", "x", "X", None, depth=[{"gsis_id": "a", "player": "A", "status": None}])],
        INJ,
        spots=[{"slot": "WR1", "gsis_id": "b", "player": "B", "status": "Out"}],
    )
    assert lineup_conflicts(g) == [
        "home SS depth: A shown None, report 'Out'",
        "home map WR1: B shown 'Out', report 'Questionable'",
    ]


def test_built_game_files_agree():
    """Leakage-guard style: runs over the local site files, skips without them."""
    files = sorted((get_paths().site / "game").glob("*.json"))
    if not files:
        pytest.skip("no local site files")
    bad = {f.name: c for f in files if (c := lineup_conflicts(json.loads(f.read_text())))}
    assert bad == {}
