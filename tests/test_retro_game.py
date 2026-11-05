"""M9.4: game retros from a synthetic curated tree (games + plays + predictions)."""

import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from nfl.config import Paths
from nfl.features.groups import FEATURE_GROUP
from nfl.predict import PRED_SCHEMA
from nfl.retro.game import (
    _league_bands,
    _metric_exprs,
    _metrics,
    _phases,
    build,
    build_games,
    retro_path,
)
from nfl.retro.schema import SCHEMA_VERSION, Expectations, RetroGame, TeamRetro

EXP = Path(__file__).parent / "fixtures" / "retro" / "expectations.json"
PLAY_COLS = [
    "game_id", "play_id", "aborted_play", "raw_snapshot_ts", "posteam", "defteam", "play_type", "epa", "success",
    "qb_dropback", "sack", "yards_gained", "pass_oe", "interception", "fumble", "fumble_lost",
    "special_teams_play", "down", "ydstogo", "third_down_converted", "third_down_failed",
    "fourth_down_converted", "fourth_down_failed", "field_goal_attempt", "field_goal_result",
    "kick_distance", "extra_point_attempt", "extra_point_result", "penalty_team", "penalty_yards",
    "return_touchdown", "td_team", "punt_blocked", "season_type", "drive", "yardline_100", "touchdown",
]  # fmt: skip
STR = {"game_id", "raw_snapshot_ts", "posteam", "defteam", "play_type", "field_goal_result",
       "extra_point_result", "penalty_team", "td_team", "season_type"}  # fmt: skip
SNAP = "20261001T000000Z"

_feats = {}
for _f, _g in FEATURE_GROUP.items():
    _feats.setdefault(_g, _f)
FEAT_A, FEAT_B = list(_feats.values())[:2]


_ids = [0]


def play(gid, pos, de, ptype="pass", epa=0.1, **kw):
    d = dict.fromkeys(PLAY_COLS)
    _ids[0] += 1
    d |= {"game_id": gid, "posteam": pos, "defteam": de, "play_type": ptype, "epa": epa,
          "success": float(epa > 0), "play_id": float(_ids[0]), "qb_dropback": float(ptype == "pass"), "sack": 0.0,
          "yards_gained": 5.0, "pass_oe": 0.0, "raw_snapshot_ts": SNAP, "season_type": "REG"}  # fmt: skip
    return d | kw


def game_row(gid, week, kick, hs, as_, home="HOM", away="AWY"):
    return {"game_id": gid, "season": 2026, "week": week, "kickoff_utc": kick,
            "home_team": home, "away_team": away, "home_score": hs, "away_score": as_,
            "result": None if hs is None else hs - as_, "raw_snapshot_ts": "x",
            "game_type": "REG"}  # fmt: skip


def base_plays(gid):
    out = []
    for i in range(20):
        out.append(play(gid, "HOM", "AWY", "pass" if i % 2 else "run", 0.2, yards_gained=6.0))
        out.append(play(gid, "AWY", "HOM", "pass" if i % 2 else "run", -0.1, yards_gained=4.0))
    return out


def write_tree(tmp_path, games, plays, preds=True):
    paths = Paths(tmp_path)
    d = paths.curated_table("plays") / "season=2026"
    d.mkdir(parents=True, exist_ok=True)
    schema = {c: (pl.Utf8 if c in STR else pl.Float64) for c in PLAY_COLS}
    pl.DataFrame(plays, schema=schema).write_parquet(d / "p.parquet")
    d = paths.curated_table("games") / "season=2026"
    d.mkdir(parents=True, exist_ok=True)
    gdf = pl.DataFrame(
        [{k: v for k, v in g.items() if k != "season"} for g in games],
        schema_overrides={"kickoff_utc": pl.Datetime("us"), "home_score": pl.Int32,
                          "away_score": pl.Int32, "result": pl.Int32, "week": pl.Int32},
    )  # fmt: skip
    gdf.write_parquet(d / "g.parquet")
    paths.marts.mkdir(parents=True, exist_ok=True)
    rows = []
    for g in games:
        for mid, p, contrib in (
            ("traditionalist", 0.7, {"home_field": 0.2, FEAT_A: 1.0, FEAT_B: -0.6}),
            ("ensemble", 0.65, {"home_field": 0.1, FEAT_A: 0.8, FEAT_B: -0.5}),
            ("market_baseline", 0.6, None),
        ):
            rows.append({
                "game_id": g["game_id"], "season": 2026, "week": g["week"], "model_id": mid,
                "model_version": "x", "lock_ts": g["kickoff_utc"] - timedelta(hours=2),
                "data_snapshot_ts": "s", "p_home": p, "spread_home": 3.0, "total": 44.0,
                "sd_margin": 13.5, "is_backfill": True, "slot": None,
                "contributions": None if contrib is None else json.dumps(contrib),
            })  # fmt: skip
    if preds:
        pl.DataFrame(rows, schema=PRED_SCHEMA).write_parquet(paths.marts / "predictions.parquet")
    (paths.marts / "retro").mkdir(parents=True, exist_ok=True)
    shutil.copy(EXP, paths.marts / "retro" / "expectations.json")
    return paths


G1 = game_row("g1", 1, datetime(2026, 9, 10, 17), 20, 10)
G2 = game_row("g2", 2, datetime(2026, 9, 17, 17), 17, 24)
G3 = game_row("g3", 3, datetime(2026, 9, 24, 17), 30, 3)


def target_plays():
    ps = base_plays("g2")
    for _ in range(3):  # HOM loses 3 of 3 fumbles
        ps.append(play("g2", "HOM", "AWY", epa=-2.0, fumble=1.0, fumble_lost=1.0))
    for _ in range(4):  # AWY converts 3rd-and-1 four times (league rate .71)
        ps.append(play("g2", "AWY", "HOM", "run", 0.5, down=3.0, ydstogo=1.0,
                       third_down_converted=1.0, third_down_failed=0.0))  # fmt: skip
    return ps


@pytest.fixture
def tree(tmp_path):
    return write_tree(tmp_path, [G1, G2], base_plays("g1") + target_plays())


def read(paths, gid):
    return json.loads(retro_path(paths, 2026, gid).read_text())


def test_validates_and_basics(tree):
    assert sorted(build_games(tree, 2026)) == ["g1", "g2"]
    rec = RetroGame.model_validate(read(tree, "g2"))
    assert rec.result.margin == -7 and rec.teams["home"].team == "HOM"
    assert 1 <= len(rec.headlines) <= 6
    assert [p.kind for p in rec.predictions][:2] == ["approach", "ensemble"]
    assert rec.best_model in ("traditionalist", "ensemble")
    assert rec.predictions[0].right is False  # picked home, away won


def test_expectations_missing_raises(tmp_path):
    paths = write_tree(tmp_path, [G1], base_plays("g1"))
    (paths.marts / "retro" / "expectations.json").unlink()
    with pytest.raises(FileNotFoundError, match="nfl retro expectations"):
        build_games(paths, 2026)


def test_point_in_time(tmp_path):
    paths = write_tree(tmp_path, [G1, G2], base_plays("g1") + target_plays())
    build_games(paths, 2026)
    before = read(paths, "g2")
    later = [play("g3", "HOM", "AWY", epa=9.0, yards_gained=50.0) for _ in range(30)]
    write_tree(tmp_path, [G1, G2, G3], base_plays("g1") + target_plays() + later)
    build_games(paths, 2026, game_ids=["g2"], force=True)
    after = read(paths, "g2")
    for side in ("home", "away"):
        assert before["teams"][side]["efficiency"] == after["teams"][side]["efficiency"]
        assert before["teams"][side]["luck"] == after["teams"][side]["luck"]
    eff = {e["metric"]: e for e in after["teams"]["home"]["efficiency"]}
    assert eff["off_epa_play"]["season_games"] == 1
    assert eff["off_epa_play"]["season"] == pytest.approx(0.2)
    assert eff["off_epa_play"]["league"] == pytest.approx(0.05)  # (0.2 + -0.1) / 2


def test_first_game_has_no_season(tree):
    build_games(tree, 2026)
    eff = read(tree, "g1")["teams"]["home"]["efficiency"]
    assert all(e["season"] is None and e["season_games"] == 0 for e in eff)


def test_fumbles(tree):
    build_games(tree, 2026)
    E = Expectations.model_validate_json(EXP.read_text())
    f = next(x for x in read(tree, "g2")["teams"]["home"]["luck"] if x["factor"] == "fumbles")
    assert f["actual"] == 3 and f["attempts"] == 3
    assert f["swing_pts"] == pytest.approx(
        -(3 - 3 * E.fumble_lost_share) * E.value_fumble_lost, abs=0.06
    )


def test_third_down_positive(tree):
    build_games(tree, 2026)
    f = next(x for x in read(tree, "g2")["teams"]["away"]["luck"] if x["factor"] == "third_down")
    assert f["actual"] == 4 and f["expected"] == pytest.approx(4 * 0.71)
    assert f["swing_pts"] > 0


def test_drop_one_value_signs(tree):
    build_games(tree, 2026)
    rec = read(tree, "g1")  # home won: FEAT_A pushed home, FEAT_B pushed away
    at = next(a for a in rec["attribution"] if a["model_id"] == "traditionalist")
    vals = {g["group"]: g["value"] for g in at["groups"]}
    assert vals[FEATURE_GROUP[FEAT_A]] > 0 > vals[FEATURE_GROUP[FEAT_B]]
    assert at["most_valuable"] == FEATURE_GROUP[FEAT_A]
    assert [g["value"] for g in at["groups"]] == sorted(
        (g["value"] for g in at["groups"]), reverse=True
    )
    rec2 = read(tree, "g2")  # away won: the reverse
    vals2 = {g["group"]: g["value"] for g in next(
        a for a in rec2["attribution"] if a["model_id"] == "traditionalist")["groups"]}  # fmt: skip
    assert vals2[FEATURE_GROUP[FEAT_A]] < 0 < vals2[FEATURE_GROUP[FEAT_B]]


def _formats(v):
    out = set()
    if isinstance(v, bool) or v is None:
        return out
    if isinstance(v, (int, float)):
        a = abs(v)
        out |= {f"{a:.0f}", f"{a:.1f}", f"{a:.2f}", f"{a * 100:.0f}"}
    return out


def _walk(o, acc):
    if isinstance(o, dict):
        for v in o.values():
            _walk(v, acc)
    elif isinstance(o, list):
        for v in o:
            _walk(v, acc)
    else:
        acc |= _formats(o)


def test_headline_numbers_in_record(tree):
    build_games(tree, 2026)
    for gid in ("g1", "g2"):
        rec = read(tree, gid)
        allowed: set[str] = set()
        _walk(
            {k: v for k, v in rec.items() if k not in ("headlines", "built_at", "kickoff_utc")},
            allowed,
        )
        nets = [t["luck_net"] for t in rec["teams"].values()]
        allowed |= _formats(nets[0] - nets[1])  # the headline's derived net difference
        for t in rec["teams"].values():  # and the pure-luck sums
            allowed |= _formats(sum(f["swing_pts"] for f in t["luck"] if not f["partly_skill"]))
        for h in rec["headlines"]:
            text = re.sub(r"\d{1,2}% ", lambda m: m.group(0), h)
            for num in re.findall(r"\d+(?:\.\d+)?", text):
                assert num in allowed, (h, num)


def test_idempotent_force_and_staleness(tmp_path):
    plays = base_plays("g1") + target_plays()
    tree = write_tree(tmp_path, [G1, G2], plays)
    assert len(build_games(tree, 2026)) == 2
    assert build_games(tree, 2026) == []
    assert sorted(build_games(tree, 2026, force=True)) == ["g1", "g2"]

    # a newer snapshot with identical plays rewrites nothing
    same = [dict(p, raw_snapshot_ts="20261002T000000Z") for p in plays]
    write_tree(tree.root, [G1, G2], same)
    assert build_games(tree, 2026) == []

    # a changed play in g2 rewrites g2 only, and the stamp moves
    changed = [dict(p) for p in same]
    next(p for p in changed if p["game_id"] == "g2" and p["posteam"] == "HOM")["epa"] = 0.9
    write_tree(tree.root, [G1, G2], changed)
    assert build_games(tree, 2026) == ["g2"]
    assert read(tree, "g2")["pbp_snapshot_ts"] == "20261002T000000Z"
    assert read(tree, "g2")["pbp_hash"] != read(tree, "g1")["pbp_hash"]

    # a new expectations version rewrites everything
    f = tree.marts / "retro" / "expectations.json"
    f.write_text(f.read_text().replace('"retro_exp_v1"', '"retro_exp_v9"'))
    assert sorted(build_games(tree, 2026)) == ["g1", "g2"]
    assert read(tree, "g1")["expectations_version"] == "retro_exp_v9"


def test_unlocked_game_outside_the_window_keeps_approach_rows(tmp_path, monkeypatch):
    """pregame_rows' week window must not decide a rebuilt retro: the builder names the games."""
    from nfl import site

    paths = write_tree(tmp_path, [G1, G2], base_plays("g1") + target_plays(), preds=False)
    calls = []

    def fake(paths_, games, have, now, game_ids=None):
        calls.append(game_ids)
        ids = game_ids or []  # the default (windowed) call would return nothing for old weeks
        if not ids:
            return pl.DataFrame()
        return pl.DataFrame(
            [{"game_id": g, "model_id": "traditionalist", "p_home": 0.6, "spread_home": 2.0,
              "contributions": json.dumps({"home_field": 0.2, FEAT_A: 0.3}),
              "lock_ts": datetime(2026, 9, 1), "status": "pregame"} for g in ids]
        )  # fmt: skip

    monkeypatch.setattr(site, "pregame_rows", fake)
    build_games(paths, 2026)
    assert sorted(next(c for c in calls if c)) == ["g1", "g2"]
    for gid in ("g1", "g2"):
        rec = read(paths, gid)
        assert [p["model_id"] for p in rec["predictions"]] == ["traditionalist"]
        assert rec["predictions"][0]["status"] == "pregame" and rec["best_model"]


def test_same_kickoff_game_excluded_from_season_to_date(tmp_path):
    twin = game_row("g2b", 2, G2["kickoff_utc"], 10, 7, home="XXX", away="YYY")
    twin_plays = [play("g2b", "HOM", "AWY", epa=9.0) for _ in range(20)]
    paths = write_tree(tmp_path, [G1, G2, twin], base_plays("g1") + target_plays() + twin_plays)
    build_games(paths, 2026, game_ids=["g2"])
    eff = {e["metric"]: e for e in read(paths, "g2")["teams"]["home"]["efficiency"]}
    assert eff["off_epa_play"]["season_games"] == 1
    assert eff["off_epa_play"]["season"] == pytest.approx(0.2)
    assert eff["off_epa_play"]["league"] == pytest.approx(0.05)


def test_league_int_rate_switch_and_prior_season(tmp_path):
    from nfl.retro.game import _prior_league_int_rate, league_int_rate

    paths = Paths(tmp_path)
    d = paths.curated_table("plays")
    for season, rows in (
        (2025, [("REG", 1.0)] * 3 + [("REG", 0.0)] * 97 + [("POST", 1.0)] * 50),
        (2024, [("REG", 1.0)] * 50 + [("REG", 0.0)] * 50),
    ):
        (d / f"season={season}").mkdir(parents=True)
        pl.DataFrame(
            {"season_type": [r[0] for r in rows], "interception": [r[1] for r in rows],
             "qb_dropback": [1.0] * len(rows), "play_type": ["pass"] * len(rows),
             "epa": [0.0] * len(rows)}
        ).write_parquet(d / f"season={season}" / "p.parquet")  # fmt: skip
    # season - 1 = 2025, regular season only: 3 / 100 (the postseason picks and 2024 are ignored)
    assert _prior_league_int_rate(paths, 2026) == pytest.approx(0.03)
    assert _prior_league_int_rate(paths, 2030) == pytest.approx(0.023)  # no such season: default

    def off(n, ints):
        return pl.DataFrame(
            {"qb_dropback": [1.0] * n, "interception": [1.0] * ints + [0.0] * (n - ints)}
        )

    assert league_int_rate(off(299, 299), 0.03) == 0.03  # under 300 dropbacks: prior season
    assert league_int_rate(off(300, 30), 0.03) == pytest.approx(0.1)  # at 300: season to date


def test_skips_games_without_plays_or_result(tmp_path):
    g4 = game_row("g4", 4, datetime(2026, 10, 1, 17), None, None)
    paths = write_tree(tmp_path, [G1, G3, g4], base_plays("g1"))
    rep = build(paths, 2026)
    assert rep.written == ["g1"] and rep.skipped == 1


def test_tie(tmp_path):
    tie = game_row("g5", 5, datetime(2026, 10, 8, 17), 17, 17)
    paths = write_tree(tmp_path, [G1, tie], base_plays("g1") + base_plays("g5"))
    build_games(paths, 2026)
    rec = RetroGame.model_validate(read(paths, "g5"))
    assert rec.played_like.matches_result is None
    assert all(p.right is None for p in rec.predictions)
    assert "tied" in rec.played_like.sentence


def _third(gid, pos, de, conv, n=1):
    return [
        play(gid, pos, de, "run", 0.5 if conv else -0.5, down=3.0, ydstogo=1.0,
             third_down_converted=float(conv), third_down_failed=float(not conv))
        for _ in range(n)
    ]  # fmt: skip


def _third_expected(tmp_path, g1_plays):
    plays = base_plays("g1") + g1_plays + base_plays("g2") + _third("g2", "HOM", "AWY", 1, 4)
    paths = write_tree(tmp_path, [G1, G2], plays)
    build_games(paths, 2026, game_ids=["g2"])
    rec = read(paths, "g2")
    f = next(x for x in rec["teams"]["home"]["luck"] if x["factor"] == "third_down")
    return f["expected"], rec


def test_third_down_expectation_uses_offense_form(tmp_path):
    league_only, _ = _third_expected(tmp_path / "a", [])
    strong, _ = _third_expected(tmp_path / "b", _third("g1", "HOM", "AWY", 1, 30))
    assert league_only == pytest.approx(4 * 0.71)
    assert strong > league_only


def test_third_down_expectation_uses_opponent_defense(tmp_path):
    base, _ = _third_expected(tmp_path / "a", [])
    # AWY's defense allowed 30 conversions in g1 (HOM was on offense), so HOM expects more
    weak_d, _ = _third_expected(tmp_path / "b", _third("g1", "HOM", "AWY", 1, 30))
    # HOM's own offense is the same, so isolate the defense with a different offense:
    other = _third("g1", "OTH", "AWY", 1, 30)
    only_def, _ = _third_expected(tmp_path / "c", other)
    assert only_def > base
    assert weak_d > only_def  # both effects add up


def test_third_down_adjustment_is_point_in_time(tmp_path):
    plays = base_plays("g1") + base_plays("g2") + _third("g2", "HOM", "AWY", 1, 4)
    paths = write_tree(tmp_path, [G1, G2], plays)
    build_games(paths, 2026)
    before = read(paths, "g2")["teams"]["home"]["luck"]
    later = base_plays("g3") + _third("g3", "HOM", "AWY", 1, 40)
    write_tree(tmp_path, [G1, G2, G3], plays + later)
    build_games(paths, 2026, game_ids=["g2"], force=True)
    assert read(paths, "g2")["teams"]["home"]["luck"] == before


def test_market_from_market_frame_when_no_prediction_row(tree, monkeypatch):
    from nfl import site

    def fake(paths, games, now):
        return pl.DataFrame(
            {"game_id": ["g1", "g2"], "p_home": [0.8, 0.3], "spread_home": [6.5, -3.0],
             "total": [44.0, 44.0], "as_of": [None, None], "source": ["odds_api", "schedules"]},
        )  # fmt: skip

    monkeypatch.setattr(site, "market_rows", fake)
    build_games(tree, 2026)
    for gid, p, src in (("g1", 0.8, "odds_api"), ("g2", 0.3, "schedules")):
        m = next(x for x in read(tree, gid)["predictions"] if x["model_id"] == "market_baseline")
        assert m["p_home"] == p and m["status"] == src and m["kind"] == "reference"
        assert m["label"] == "Market"
    g2 = next(x for x in read(tree, "g2")["predictions"] if x["model_id"] == "market_baseline")
    assert g2["pick"] == "AWY" and g2["right"] is True  # away won 24-17


# ---------------------------------------------------------------------------------- league bands


def _team_plays(gid, n_teams, epas):
    """Team T{i} has `epas[i]` EPA on every one of its 4 offensive plays (2 pass, 2 run)."""
    ps = []
    for i in range(n_teams):
        for k in range(4):
            ps.append(
                play(gid, f"T{i}", f"T{(i + 1) % n_teams}", "pass" if k % 2 else "run", epas[i])
            )
    return ps


def _eff(tree, gid, metric):
    rec = read(tree, gid)
    return next(e for e in rec["teams"]["home"]["efficiency"] if e["metric"] == metric)


def test_league_band_percentiles(tmp_path):
    epas = [-0.3, -0.2, -0.1, 0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5]
    plays = _team_plays("g1", 10, epas) + base_plays("g2")
    tree = write_tree(tmp_path, [G1, G2], plays)
    build_games(tree, 2026)
    e = _eff(tree, "g2", "off_epa_play")
    lo, hi = np.percentile(epas, [10, 90])
    assert e["league_lo"] == round(lo, 3) and e["league_hi"] == round(hi, 3)
    # defense bands group by defteam; each team faces one offense, so the same ten values
    d = _eff(tree, "g2", "def_epa_play")
    assert d["league_lo"] == round(lo, 3) and d["league_hi"] == round(hi, 3)
    assert _eff(tree, "g1", "off_epa_play")["league_lo"] is None  # nothing before game 1


def test_league_band_needs_eight_teams(tmp_path):
    plays = _team_plays("g1", 7, [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]) + base_plays("g2")
    tree = write_tree(tmp_path, [G1, G2], plays)
    build_games(tree, 2026)
    e = _eff(tree, "g2", "off_epa_play")
    assert e["league_lo"] is None and e["league_hi"] is None
    assert e["league"] is not None  # the league mean is unaffected


def test_league_bands_match_metrics_per_team():
    plays = pl.DataFrame(
        base_plays("g1") + [play("g1", "AWY", "HOM", "run", 0.9, yards_gained=12.0, sack=1.0)],
        schema_overrides={"epa": pl.Float64},
    )
    per_team = {t: _metrics(plays.filter(pl.col("posteam") == t)) for t in ("HOM", "AWY")}
    grouped = plays.group_by("posteam").agg(*_metric_exprs())
    for row in grouped.iter_rows(named=True):
        for k, v in per_team[row["posteam"]].items():
            assert row[k] == pytest.approx(v) if v is not None else row[k] is None
    # two teams only: below the minimum, so no band
    assert _league_bands(plays, "posteam")["epa_play"] == (None, None)


def test_schema_version_staleness(tree):
    build_games(tree, 2026)
    assert read(tree, "g2")["schema_version"] == SCHEMA_VERSION == "3"
    assert build_games(tree, 2026) == []  # same hash, expectations and schema: up to date
    f = retro_path(tree, 2026, "g2")
    d = json.loads(f.read_text())
    d["schema_version"] = "1"
    f.write_text(json.dumps(d))
    assert build_games(tree, 2026) == ["g2"]
    assert read(tree, "g2")["schema_version"] == SCHEMA_VERSION


# ------------------------------------------------------------------------------------- phases


def _phase_frame(plays):
    schema = {c: (pl.Utf8 if c in STR else pl.Float64) for c in PLAY_COLS}
    return pl.DataFrame(plays, schema=schema)


def _team(code):
    rows = [
        {"metric": m, "unit_side": "off", "label": m, "unit": "epa", "higher_is_better": True,
         "game": v, "season": None, "league": None, "season_games": 0}
        for m, v in (("off_epa_dropback", 0.2), ("off_epa_rush", 0.0), ("off_explosive", 0.1))
    ]  # fmt: skip
    made, tries = (9.0, 14) if code == "HOM" else (5.0, 15)
    third = {"factor": "third_down", "label": "3rd", "actual": made, "expected": 6.0, "unit": "count",
             "attempts": tries, "swing_pts": 0.0, "sentence": ""}  # fmt: skip
    return TeamRetro(team=code, score=0, efficiency=rows, luck=[third], luck_net=0.0)


def _by_id(plays):
    teams = {"home": _team("HOM"), "away": _team("AWY")}
    return {p.phase: p for p in _phases(_phase_frame(plays), teams, "HOM", "AWY")}


def test_phases_red_zone_counts_trips_not_plays_and_only_your_own_touchdowns():
    plays = [
        play("g", "HOM", "AWY", drive=1.0, yardline_100=18.0),
        play("g", "HOM", "AWY", drive=1.0, yardline_100=9.0, touchdown=1.0, td_team="HOM"),
        play("g", "AWY", "HOM", drive=2.0, yardline_100=15.0),
        play("g", "HOM", "AWY", drive=3.0, yardline_100=12.0),
        # a pick-six on the trip: a touchdown, but not one this offense scored
        play("g", "HOM", "AWY", drive=3.0, yardline_100=8.0, touchdown=1.0, td_team="AWY"),
    ]
    p = _by_id(plays)["red_zone"]
    assert (p.home_text, p.away_text, p.leader) == ("1 of 2", "0 of 1", "home")


def test_phases_a_team_with_no_trips_is_not_compared():
    p = _by_id([play("g", "HOM", "AWY", drive=1.0, yardline_100=10.0)])["red_zone"]
    assert (p.away_text, p.away, p.leader) == ("no trips", None, None)


def test_phases_special_teams_counts_kickoffs_and_punts_both_ways_and_field_goals_once():
    plays = [
        play("g", "HOM", "AWY", "kickoff", -5.0, special_teams_play=1.0),  # HOM fumbles the return
        play("g", "AWY", "HOM", "punt", 0.5, special_teams_play=1.0),
        play("g", "HOM", "AWY", "field_goal", 1.5, special_teams_play=1.0),
        play("g", "AWY", "HOM", "extra_point", 0.1),  # flag or play type: either counts
        play("g", "HOM", "AWY", "pass", 3.0, special_teams_play=1.0),  # a fake is scrimmage
    ]
    p = _by_id(plays)["special_teams"]
    assert p.home == -5.0 - 0.5 + 1.5
    assert p.away == 5.0 + 0.5 + 0.1
    assert (p.home_text, p.away_text, p.leader) == ("−4.0", "+5.6", "away")


def test_phases_third_downs_read_the_swing_plays_count():
    p = _by_id([play("g", "HOM", "AWY", third_down_converted=1.0)])["third_down"]
    assert (p.home_text, p.away_text, p.leader) == ("9 of 14", "5 of 15", "home")


def test_phases_field_position_drops_the_drive_after_a_turnover():
    plays = [
        play("g", "HOM", "AWY", drive=1.0, yardline_100=75.0),
        play("g", "AWY", "HOM", drive=2.0, yardline_100=80.0, interception=1.0),
        play(
            "g", "HOM", "AWY", drive=3.0, yardline_100=20.0
        ),  # handed the ball at the 20: left out
        play("g", "AWY", "HOM", drive=4.0, yardline_100=80.0),
    ]
    p = _by_id(plays)["field_position"]
    assert (p.home, p.home_text) == (25.0, "own 25")
    assert (p.away, p.away_text) == (20.0, "own 20")
    assert p.leader == "home"


def test_phases_fewer_turnovers_wins_and_equal_text_is_even():
    plays = [play("g", "HOM", "AWY", interception=1.0), play("g", "AWY", "HOM")]
    ph = _by_id(plays)
    assert (ph["turnovers"].home_text, ph["turnovers"].away_text, ph["turnovers"].leader) == (
        "1",
        "0",
        "away",
    )
    assert ph["passing"].leader is None  # both +0.20
    assert [p for p in ph] == [
        "passing", "rushing", "explosive", "third_down", "red_zone", "special_teams", "field_position", "turnovers",
    ]  # fmt: skip
