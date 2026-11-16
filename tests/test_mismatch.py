"""The game's Health board (Austin 2026-11-15): rooms that face each other, full strength and now."""

from nfl.players import mismatch as M


def _room(grp, rank, now=None, label="good"):
    now = rank if now is None else now
    return {
        "grp": grp,
        "rank": rank,
        "label": label,
        "now_rank": now,
        "now_label": label,
        "health": 1.0,
    }


def _team(rooms, starters=()):
    return {"rooms": rooms, "now": {"starters": list(starters)}}


def _st(grp, name, p_play, status, key=False):
    return {
        "grp": grp,
        "player": name,
        "p_play": p_play,
        "status": status,
        "key": key,
        "doubt": False,
    }


FULL = ("WR", "TE", "RB", "OL", "EDGE", "DL", "LB", "CB", "S", "QB")


def _all(rank=16, **over):
    return [over.get(g, _room(g, rank)) for g in FULL]


def test_a_good_room_against_one_usually_good_but_hurt_now():
    """Austin's example: good receivers against corners that are usually good but weak now."""
    away = _team(_all(WR=_room("WR", 7)))
    home = _team(
        _all(CB=_room("CB", 12, 29, "good")),
        [
            _st("CB", "Jaycee Horn", 0.0, "IR", key=True),
            _st("CB", "Will Lee III", 0.7, "Questionable"),
        ],
    )
    b = M.board("CAR", "BAL", home, away)
    wr = b["sides"][0]["rows"][0]
    assert (wr["offense"]["grp"], wr["defense"]["grp"], wr["favours"], wr["moved"], wr["flag"]) == (
        "WR", "CB", "BAL", True, True,
    )  # fmt: skip
    assert wr["sentence"] == (
        "BAL's receivers (#7, good) face CAR's corners, usually good (#12) but about #29 now "
        "with Jaycee Horn out and Will Lee III questionable."
    )
    assert b["lede"] == wr["sentence"] and b["lede_kind"] == "moved"
    assert b["sides"][0]["offense"] == "BAL" and b["sides"][1]["offense"] == "CAR"


def test_close_rooms_read_even_and_unflagged():
    b = M.board("H", "A", _team(_all(16)), _team(_all(18)))
    rows = [r for s in b["sides"] for r in s["rows"]]
    assert all(r["favours"] is None and not r["flag"] and r["sentence"] is None for r in rows)
    assert b["lede"] is None and b["notes"] == []


def test_a_wide_gap_without_injuries_is_flagged_plainly_and_the_line_is_singular():
    b = M.board("H", "A", _team(_all(EDGE=_room("EDGE", 28, label="weak"))), _team(_all(OL=_room("OL", 4, label="elite"))))  # fmt: skip
    ol = next(r for r in b["sides"][0]["rows"] if r["defense"]["grp"] == "EDGE")
    assert ol["sentence"] == "A's offensive line (#4, elite) faces H's edge rushers (#28, weak)."
    assert ol["favours"] == "A" and not ol["moved"]


def test_quarterback_note_and_no_board_without_both_teams():
    away = _team(_all(QB=_room("QB", 7, 30)), [_st("QB", "Lamar Jackson", 0.0, "IR", key=True)])
    b = M.board("H", "A", _team(_all()), away)
    assert b["notes"] == ["A's quarterback room goes from #7 to about #30 with Lamar Jackson out."]
    assert M.board("H", "A", _team(_all()), None) is None
    assert M.board("H", "A", _team([]), away) is None
