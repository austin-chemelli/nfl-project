"""Game JSON `matchups`, `paths`, `paths_outcome` and `meta.split_defs` (ADR 0028, M25.3)."""

import inspect
import json
import re

import numpy as np
import polars as pl
import pytest

from nfl import matchups as M
from nfl import site, splits, weekly

from .test_matchups import SEASON, blitz_frame, frame, unit_rows
from .test_paths import build as build_conditions
from .test_paths import game as paths_game
from .test_paths import planted_plays


def game_dict(week, home="O1", away="D1", **kw):
    return {"game_id": f"{SEASON}_{week:02d}_{away}_{home}", "season": SEASON, "week": week,
            "home_team": home, "away_team": away, "result": None, "spread_line": None} | kw  # fmt: skip


def ctx(df=None, ledger=None):
    return M.Engine(df if df is not None else blitz_frame()), ledger if ledger is not None else pl.DataFrame()  # fmt: skip


def edge_rows(m):
    return {(sd["offense"], r["split"]): r for sd in m["sides"] for r in sd["rows"]}


def test_shape_rounding_and_the_registry_rows():
    m = site.game_matchups(ctx(), game_dict(4))
    assert set(m) == {"as_of_week", "sides", "lede"} and m["as_of_week"] == 4
    assert [(s["offense"], s["defense"]) for s in m["sides"]] == [("O1", "D1"), ("D1", "O1")]
    row = edge_rows(m)[("O1", "blitz")]
    assert set(row) == {
        "split", "label", "chooser", "has_edge", "opp_rate", "opp_rate_lo", "opp_rate_q1",
        "opp_rate_med", "opp_rate_q3", "opp_rate_hi", "rate_faced", "n_with", "n_without",
        "epa_with", "epa_without", "shrunk_gap", "league_gap", "edge_pts_pg", "favours",
        "reliability", "note",
    }  # fmt: skip
    assert row["has_edge"] and row["reliability"] == "noise"  # no ledger: every badge is noise
    assert row["edge_pts_pg"] == round(row["edge_pts_pg"], 2)
    assert row["opp_rate"] == round(row["opp_rate"], 3)
    # rows without an edge are gone (Austin, 2026-11-12); without the conditions model, no face-off
    assert ("O1", "shotgun") not in edge_rows(m)
    assert all(r["has_edge"] for sd in m["sides"] for r in sd["rows"])
    assert all(sd["face_off"] == [] for sd in m["sides"])
    json.dumps(m)


def test_null_before_week_3_and_when_the_model_is_missing():
    assert site.game_matchups(ctx(), game_dict(2)) is None
    assert site.game_matchups(ctx(), game_dict(3)) is not None
    assert site.game_matchups(None, game_dict(5)) is None


def test_missing_split_model_gives_a_null_section_through_the_build_guard(tmp_path):
    from nfl.config import Paths

    # no data at all: the context fails behind _safe and every game's section is null
    assert site._safe(site._matchup_ctx, None, Paths(tmp_path)) is None
    assert site._safe(site._conditions_frame, None, Paths(tmp_path)) is None
    assert site.game_paths(None, game_dict(5, spread_line=3.0)) is None
    assert site.game_paths_outcome(None, game_dict(5, result=3)) is None


def test_only_splits_with_an_edge_are_kept():
    def ids(week):
        m = site.game_matchups(ctx(), game_dict(week))
        return {r["split"] for sd in m["sides"] for r in sd["rows"]}

    edged = {s.id for s in splits.SPLITS if s.chooser != "neither" and not s.no_edge}
    assert ids(3) == ids(4) == edged


def fo_row(cid, label, off_noun, def_noun, off_rank, def_rank):
    return {"id": cid, "label": label, "off_noun": off_noun, "def_noun": def_noun,
            "off_rank": off_rank, "def_rank": def_rank, "n_teams": 32, "edge": "even"}  # fmt: skip


def test_face_off_lede_names_the_biggest_mismatch_and_strength_on_strength():
    sides = [
        {"offense": "NE", "defense": "GB", "rows": [], "face_off": [
            fo_row("early_down", "Early downs", "early-down offense", "early-down defense", 2, 1),
            fo_row("turnovers", "Turnovers", "ball security", "takeaways", 28, 1),
        ]},
        {"offense": "GB", "defense": "NE", "rows": [], "face_off": [
            fo_row("pass_game", "Passing", "passing offense", "pass defense", 2, 17),
        ]},
    ]  # fmt: skip
    lede = site.matchups_lede(sides)
    assert lede == (
        "The biggest mismatch: GB's takeaways (1st) against NE's ball security (28th). "
        "Strength on strength: NE's early-down offense (2nd) into GB's early-down defense (1st)."
    )
    record = {str(r[k]) for sd in sides for r in sd["face_off"] for k in ("off_rank", "def_rank")}
    assert set(re.findall(r"\d+", lede)) <= record


def test_face_off_lede_without_a_mismatch():
    sides = [{"offense": "A", "defense": "B", "rows": [], "face_off": [
        fo_row("sacks", "Sacks", "pass protection", "pass rush", 12, 15)]}]  # fmt: skip
    assert site.matchups_lede(sides) == "No unit here ranks far above the one it meets."


def test_face_off_rows_from_the_conditions_model():
    from nfl import paths as P

    rng = np.random.default_rng(5)
    teams = [f"T{i:02d}" for i in range(20)]
    rows = []
    for w in range(1, 6):
        order = rng.permutation(teams)
        for h, a in zip(order[::2], order[1::2], strict=True):
            for team, opp in ((h, a), (a, h)):
                r = {
                    "season": 2026,
                    "week": w,
                    "game_id": f"{w}_{h}",
                    "team": team,
                    "opponent": opp,
                }
                for c in P.CONDITIONS:
                    r[c.stat], r[c.stat_opp] = rng.normal(), rng.normal()
                rows.append(r)
    cond = pl.DataFrame(rows)
    site._RANKS_CACHE.clear()
    fo = site.face_off(cond, 2026, 5, "T01", "T02")
    assert [r["id"] for r in fo] == [cid for cid, _ in site.FACE_OFF]
    ranks = P.team_ranks(cond, 2026, 5)
    for r in fo:
        assert r["off_rank"] == ranks["T01"][r["id"]].off_rank
        assert r["def_rank"] == ranks["T02"][r["id"]].def_rank
        gap = r["def_rank"] - r["off_rank"]
        assert r["edge"] == ("offense" if gap >= 8 else "defense" if gap <= -8 else "even")
    assert site.face_off(cond, 2026, 3, "T01", "T02") == []  # before MIN_RANK_WEEK
    assert site.face_off(None, 2026, 5, "T01", "T02") == []


def test_a_past_game_reads_only_earlier_weeks():
    df = blitz_frame()
    # week 4 differs wildly: a game in week 4 must not see it, a game in week 5 must
    extra = frame(
        unit_rows(SEASON, 4, "g4_1", "O1", "off", "blitz", 40, 30.0, 10, -5.0)
        + unit_rows(SEASON, 4, "g4_1", "D1", "def", "blitz", 40, 30.0, 10, -5.0)
    )
    both = pl.concat([df, extra])
    at4 = site.game_matchups(ctx(both), game_dict(4))
    at4_clean = site.game_matchups(ctx(df), game_dict(4))
    at5 = site.game_matchups(ctx(both), game_dict(5))
    assert at4 == at4_clean  # week 4's own plays (and later) never enter
    assert at5["as_of_week"] == 5
    assert edge_rows(at5)[("O1", "blitz")] != edge_rows(at4)[("O1", "blitz")]
    assert edge_rows(at5)[("O1", "blitz")]["n_with"] > edge_rows(at4)[("O1", "blitz")]["n_with"]


def test_the_lede_names_the_largest_edge_and_every_number_is_in_the_record():
    m = site.game_matchups(ctx(), game_dict(4))
    rows = [(sd, r) for sd in m["sides"] for r in sd["rows"] if r["has_edge"]]
    sd, top = max(rows, key=lambda x: abs(x[1]["edge_pts_pg"] or 0))
    lede = m["lede"]
    assert lede.startswith("The matchup that matters most: ")
    assert top["label"].lower() in lede and sd["defense"] in lede and sd["offense"] in lede
    assert "least reliable" in lede  # no ledger: noise
    nums = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", lede)
    assert nums == [str(abs(top["edge_pts_pg"]))]
    record = [x.lstrip("-") for x in re.findall(r"-?\d+\.?\d*", json.dumps(m["sides"]))]
    assert all(n in record or str(float(n)) in record for n in nums)


@pytest.mark.parametrize(
    "split,r,expect",
    [("play_action", 0.5, "more reliable"), ("play_action", 0.15, "moderately"), ("play_action", -0.2, "least")],
)  # fmt: skip
def test_lede_badge_follows_reliability(split, r, expect):
    sides = [{"offense": "NE", "defense": "GB", "rows": [{
        "split": split, "label": "Play action", "chooser": "offense", "has_edge": True,
        "edge_pts_pg": 0.4, "reliability": M.STABLE if r >= 0.3 else M.SOME if r >= 0.1 else M.NOISE,
    }]}]  # fmt: skip
    lede = site.matchups_lede(sides)
    assert "GB's defense against NE's play action" in lede and "0.4 points a game" in lede
    assert expect in lede


def test_lede_ignores_rows_without_an_edge_and_is_null_when_none_has_one():
    sides = [{"offense": "A", "defense": "B", "rows": [
        {"split": "shotgun", "label": "Shotgun", "chooser": "offense", "has_edge": False,
         "edge_pts_pg": 9.0, "reliability": "noise"},
        {"split": "blitz", "label": "Blitz", "chooser": "defense", "has_edge": True,
         "edge_pts_pg": None, "reliability": "noise"},
    ]}]  # fmt: skip
    assert site.matchups_lede(sides) is None


def test_paths_null_for_a_pickem_and_present_for_a_dog(tmp_path):
    _, cond = build_conditions(tmp_path, planted_plays(), [paths_game("g1", 3, "A", "B", -4)])
    g = paths_game("g9", 5, "A", "B", None, spread=3.0)
    p = site.game_paths(cond, g)
    assert p["dog"] == "B" and p["favorite"] == "A" and p["as_of_week"] == 5
    assert site.game_paths(cond, paths_game("g9", 5, "A", "B", None, spread=0.0)) is None
    assert site.game_paths(cond, paths_game("g9", 5, "A", "B", None, spread=None)) is None


def test_paths_outcome_only_for_finished_games(tmp_path):
    _, cond = build_conditions(tmp_path, planted_plays(), [paths_game("g1", 3, "A", "B", -4)])
    done = paths_game("g1", 3, "A", "B", -4)
    o = site.game_paths_outcome(cond, done)
    assert o["dog"] == "B" and o["dog_won"] and "turnovers" in o["met"]
    assert site.game_paths_outcome(cond, paths_game("g1", 3, "A", "B", None)) is None


def test_split_defs_cover_the_registry():
    d = site.split_defs()
    assert set(d) == set(splits.ids())
    assert set(d["blitz"]) == {"label", "definition", "chooser", "no_edge"}
    assert d["shotgun"]["no_edge"] and d["blitz"]["no_edge"] == ""
    json.dumps(d)


def test_weekly_builds_the_models_before_the_site():
    src = inspect.getsource(weekly.refresh)
    assert src.index('step("models"') < src.index('step("site"')
    assert src.index('step("features"') < src.index('step("models"')


def test_edge_cards_for_both_teams_and_null_without_a_line(tmp_path):
    _, cond = build_conditions(tmp_path, planted_plays(), [paths_game("g1", 3, "A", "B", -4)])
    g = paths_game("g9", 5, "A", "B", None, spread=3.0)
    cards = site.game_edge_cards(cond, g)
    assert [(c["team"], c["role"]) for c in cards] == [("B", "underdog"), ("A", "favorite")]
    assert set(cards[0]) >= {"levers", "chips", "base_rate_pct", "met"}
    assert [
        c["role"]
        for c in site.game_edge_cards(cond, paths_game("g9", 5, "A", "B", None, spread=0.0))
    ] == [
        "pick",
        "pick",
    ]
    assert site.game_edge_cards(cond, paths_game("g9", 5, "A", "B", None, spread=None)) is None
    assert site.game_edge_cards(None, g) is None
    json.dumps(cards)
