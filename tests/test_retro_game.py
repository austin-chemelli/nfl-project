"""M9.4: game retros from a synthetic curated tree (games + plays + predictions)."""

import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import pytest

from nfl.config import Paths
from nfl.features.groups import FEATURE_GROUP
from nfl.predict import PRED_SCHEMA
from nfl.retro.game import (
    _drives,
    _league_bands,
    _load_plays,
    _metric_exprs,
    _metrics,
    _phases,
    _wp_series,
    build,
    build_games,
    plays_hash,
    retro_path,
)
from nfl.retro.schema import SCHEMA_VERSION, Expectations, RetroGame, TeamRetro, WpSeries

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
    assert read(tree, "g2")["schema_version"] == SCHEMA_VERSION
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


def test_swing_sentence_hurt_both_helped_both_and_mixed():
    from nfl.retro.game import _swing_sentence

    tail = "."
    assert _swing_sentence("Green Bay", -9.6, "Carolina", -2.0, tail) == (
        "Swing plays hurt both teams, Green Bay more: 9.6 points lost against 2.0 for Carolina, "
        "a net 7.6 toward Carolina."
    )
    assert _swing_sentence("Green Bay", 1.0, "Carolina", 6.5, tail) == (
        "Swing plays helped both teams, Carolina more: 6.5 points gained against 1.0 for Green "
        "Bay, a net 5.5 toward Carolina."
    )
    assert _swing_sentence("Green Bay", -9.6, "Carolina", 5.3, tail) == (
        "Swing plays helped Carolina by 5.3 points and cost Green Bay 9.6, a net 14.9 toward "
        "Carolina."
    )
    # a team at exactly zero isn't helped or hurt (2026_01_BAL_IND, 2026_06_ARI_LA)
    assert _swing_sentence("Indianapolis", -4.6, "Baltimore", 0.0, tail) == (
        "Swing plays cost Indianapolis 4.6 points and left Baltimore even, a net 4.6 toward "
        "Baltimore."
    )
    assert _swing_sentence("Los Angeles", 0.0, "Arizona", 3.3, tail) == (
        "Swing plays helped Arizona by 3.3 points and left Los Angeles even, a net 3.3 toward "
        "Arizona."
    )


# ------------------------------------------------------------- win probability series and drives

NEW_COLS = ["qtr", "game_seconds_remaining", "desc", "vegas_home_wp", "vegas_home_wpa", "fixed_drive",
            "fixed_drive_result", "drive_start_yard_line", "drive_end_yard_line", "drive_play_count"]  # fmt: skip
NEW_STR = {"desc", "fixed_drive_result", "drive_start_yard_line", "drive_end_yard_line"}
ALL_COLS = PLAY_COLS + NEW_COLS
WG = {"game_id": "w1", "home_team": "HOM", "away_team": "AWY", "home_score": 24, "away_score": 17}


def wf(*rows):
    """A planted game's plays with every column the series and drives read."""
    schema = {c: pl.Utf8 if c in STR | NEW_STR else pl.Float64 for c in ALL_COLS}
    out = []
    for i, r in enumerate(rows, 1):
        out.append(dict.fromkeys(ALL_COLS) | {"game_id": "w1", "play_id": float(i), "qtr": 1.0,
                   "season_type": "REG", "posteam": "HOM", "defteam": "AWY", "play_type": "pass",
                   "epa": 0.1, "game_seconds_remaining": 3600.0} | r)  # fmt: skip
    return pl.DataFrame(out, schema=schema)


def wp(p, wpa, gsr, qtr=1.0, **kw):
    return {
        "vegas_home_wp": p,
        "vegas_home_wpa": wpa,
        "game_seconds_remaining": gsr,
        "qtr": qtr,
    } | kw


def ts(s):
    return [t for t, _ in s.points]


def test_wp_time_mapping_quarters_and_regular_overtime():
    rows = [wp(0.5, 0.01, 3600.0), wp(0.51, 0.01, 2700.0, 2.0), wp(0.52, 0.01, 1800.0, 3.0),
            wp(0.53, 0.01, 1.0, 4.0), wp(0.54, 0.01, 500.0, 5.0), wp(0.55, 0.01, 100.0, 5.0)]  # fmt: skip
    s = _wp_series(wf(*rows), WG | {"home_score": 20, "away_score": 20})
    assert ts(s) == [0, 0, 900, 1800, 3599, 3700, 4100, 4100]  # opening, five plays, the end
    assert s.ot and s.end_t == 4100


def test_wp_time_mapping_playoff_overtime():
    rows = [wp(0.5, 0.01, 3600.0), wp(0.6, 0.01, 500.0, 5.0), wp(0.7, 0.02, 800.0, 6.0)]
    s = _wp_series(wf(*[r | {"season_type": "POST"} for r in rows]), WG)
    assert ts(s)[2] == 3600 + 900 - 500  # 15-minute overtime periods
    assert ts(s)[3] == 3600 + 900 + (900 - 800)  # the second period starts at 4500
    assert s.end_t == 4600


def test_wp_time_never_runs_backwards_and_fills_null_clocks():
    rows = [wp(0.5, 0.01, 3000.0), wp(0.6, 0.1, 3100.0), wp(0.7, 0.1, None)]
    assert ts(_wp_series(wf(*rows), WG))[1:-1] == [600, 600, 600]


@pytest.mark.parametrize(("gsr", "qtr", "clock"), [
    (3600.0, 1.0, "15:00"), (2710.0, 2.0, "15:10"), (1810.0, 3.0, "15:10"), (900.0, 4.0, "15:00"),
    (10.0, 4.0, "0:10"), (125.0, 5.0, "2:05"),
])  # fmt: skip
def test_wp_clock_is_time_left_in_the_quarter(gsr, qtr, clock):
    assert _wp_series(wf(wp(0.2, 0.3, gsr, qtr)), WG).plays[0].clock == clock


def test_wp_repeats_dropped_and_last_point_is_result():
    rows = [wp(0.5, 0.0, 3600.0), wp(0.5, 0.02, 3500.0), wp(0.52, 0.0001, 3400.0),
            wp(0.52, 0.0, 3300.0), wp(0.53, 0.01, 3200.0)]  # fmt: skip
    s = _wp_series(wf(*rows), WG)
    assert s.points == [(0, 0.5), (100, 0.52), (400, 0.54), (3600, 1.0)]
    assert not s.ot and s.end_t == 3600
    assert _wp_series(wf(*rows), WG | {"home_score": 3, "away_score": 9}).points[-1] == (3600, 0.0)
    assert _wp_series(wf(*rows), WG | {"home_score": 9, "away_score": 9}).points[-1] == (3600, 0.5)
    end = _wp_series(wf(wp(0.9, 0.1, 100.0, 4.0)), WG)  # the result point stays when p repeats
    assert end.points[-2][1] == 1.0 and end.points[-1] == (3600, 1.0)


def test_wp_stale_timeout_row_does_not_bounce_the_curve():
    rows = [wp(0.5, 0.0, 3600.0),
            wp(0.138, -0.138, 178.0, 4.0, play_type="field_goal", field_goal_attempt=1.0,
               field_goal_result="made", kick_distance=40.0),
            wp(0.138, 0.0, 175.0, 4.0, play_type="no_play"),  # icing timeout repeats the stale value
            wp(0.0, 0.0, 173.0, 4.0, play_type=None, desc="END GAME")]  # fmt: skip
    s = _wp_series(wf(*rows), WG | {"home_score": 3, "away_score": 9})
    assert [p for _, p in s.points] == [0.5, 0.0, 0.0]
    assert [m.play_id for m in s.plays] == [2]


def test_wp_penalty_stays_on_curve_but_is_never_marked():
    rows = [wp(0.5, 0.0, 3600.0),
            wp(0.5, 0.2, 3000.0, play_type="no_play", penalty_team="AWY"),
            wp(0.7, -0.2, 2000.0, 2.0, play_type="qb_kneel"),
            wp(0.5, 0.2, 1500.0, 3.0, play_type=None),
            wp(0.7, 0.01, 1000.0, 3.0)]  # fmt: skip
    s = _wp_series(wf(*rows), WG)
    assert [p for _, p in s.points] == [0.5, 0.7, 0.5, 0.7, 0.71, 1.0]
    assert s.plays == []


def test_wp_marks_top_five_largest_first_all_on_the_curve():
    rows, p = [wp(0.5, 0.0, 3600.0)], 0.5
    for i, w in enumerate([0.06, -0.3, 0.2, -0.07, 0.05, 0.049, 0.4, -0.1]):
        rows.append(wp(p, w, 3500.0 - 100 * i))
        p += w
    s = _wp_series(wf(*rows), WG)
    assert [abs(m.wpa) for m in s.plays] == [0.4, 0.3, 0.2, 0.1, 0.07]
    assert {(m.t, m.p_after) for m in s.plays} <= set(s.points)
    assert all(m.wpa == round(m.p_after - m.p_before, 3) for m in s.plays)


def test_wp_mark_fields_clip_team_and_trimmed_text():
    long = " ".join(["word"] * 50)
    m = _wp_series(wf(wp(0.9, 0.3, 100.0, 4.0, posteam="AWY", desc=long)), WG).plays[0]
    assert (m.p_before, m.p_after, m.wpa, m.team, m.qtr) == (0.9, 1.0, 0.1, "AWY", 4)
    assert len(m.text) <= 160 and m.text.endswith("word") and long.startswith(m.text)
    short = _wp_series(wf(wp(0.5, 0.2, 100.0, 4.0, posteam=None, desc="1-A.B pass")), WG).plays[0]
    assert short.team is None and short.text == "1-A.B pass"


def spec(**k):
    return k


def test_wp_factor_tags():
    cases = {
        "interceptions": spec(play_type="pass", qb_dropback=1.0, interception=1.0),
        "fumbles": spec(play_type="pass", qb_dropback=1.0, fumble=1.0, fumble_lost=1.0),
        "fumble beats third_down": spec(play_type="run", down=3.0, ydstogo=2.0, third_down_failed=1.0,
                                        fumble=1.0, fumble_lost=1.0),
        "third_down": spec(play_type="run", down=3.0, ydstogo=2.0, third_down_failed=1.0,
                           fumble=1.0, fumble_lost=0.0),
        "fourth_down": spec(play_type="run", down=4.0, ydstogo=1.0, fourth_down_converted=1.0),
        "special_teams blocked": spec(play_type="field_goal", field_goal_attempt=1.0,
                                      field_goal_result="blocked", kick_distance=40.0, defteam="HOM"),
        "special_teams return": spec(play_type="punt", return_touchdown=1.0, special_teams_play=1.0,
                                     td_team="HOM"),
        "kicking fg": spec(play_type="field_goal", field_goal_attempt=1.0,
                           field_goal_result="missed", kick_distance=40.0),
        "kicking xp": spec(play_type="extra_point", extra_point_attempt=1.0,
                           extra_point_result="failed"),
        "aborted third": spec(play_type="run", down=3.0, ydstogo=2.0, third_down_failed=1.0,
                              aborted_play=1.0),
        "penalty": spec(play_type="run", penalty_team="HOM", penalty_yards=10.0),
    }  # fmt: skip
    want = {"fumble beats third_down": "fumbles", "special_teams blocked": "special_teams",
            "special_teams return": "special_teams", "kicking fg": "kicking",
            "kicking xp": "kicking", "aborted third": None, "penalty": None}  # fmt: skip
    for name, kw in cases.items():
        m = _wp_series(wf(wp(0.5, 0.0, 3600.0), wp(0.5, 0.3, 3000.0, **kw)), WG).plays
        assert [x.factor for x in m] == [want.get(name, name)], name


def test_wp_winner_low_comeback_and_tie():
    rows = [wp(0.5, 0.0, 3600.0), wp(0.5, -0.4, 3000.0), wp(0.1, -0.05, 2400.0),
            wp(0.05, 0.0, 2000.0), wp(0.05, 0.6, 1500.0, 3.0)]  # fmt: skip
    assert _wp_series(wf(*rows), WG).winner_low == (1200, 0.05)  # home wins from 5%
    away = WG | {"home_score": 3, "away_score": 10}
    assert _wp_series(wf(*rows), away).winner_low == (2100, 0.35)  # away's view of 0.65
    assert _wp_series(wf(*rows), WG | {"home_score": 7, "away_score": 7}).winner_low is None


def test_wp_model_and_schema():
    s = _wp_series(wf(wp(0.5, 0.2, 100.0, 4.0)), WG)
    assert s.model == "nflfastr_vegas"
    WpSeries.model_validate(s.model_dump())


def test_wp_and_drives_none_without_the_columns_or_probabilities():
    old = pl.DataFrame([play("w1", "HOM", "AWY")])
    assert _wp_series(old, WG) is None and _drives(old, WG) is None
    assert _wp_series(wf(wp(None, None, 100.0)), WG) is None
    assert _drives(wf(wp(None, None, 100.0)), WG) is None
    assert isinstance(plays_hash(old), str)  # the hash works on a frame lacking the new columns


DRV = {"game_seconds_remaining": 3600.0, "fixed_drive_result": "Touchdown",
       "drive_start_yard_line": "HOM 25", "drive_end_yard_line": "50", "drive_play_count": 6.0}  # fmt: skip


def drive_rows():
    return [
        DRV | {"fixed_drive": 1.0, "play_type": "kickoff", "posteam": "AWY"},
        DRV | {"fixed_drive": 1.0, "play_type": "run", "game_seconds_remaining": 3500.0},
        DRV | {"fixed_drive": 1.0, "play_type": "pass", "game_seconds_remaining": 3300.0},
        {"fixed_drive": 2.0, "play_type": "punt", "posteam": "AWY", "qtr": 2.0,
         "game_seconds_remaining": 1700.0, "fixed_drive_result": "Punt",
         "drive_start_yard_line": "AWY 31", "drive_end_yard_line": "HOM 40"},
        {"fixed_drive": 3.0, "play_type": "pass", "qtr": 4.0, "game_seconds_remaining": 600.0,
         "fixed_drive_result": "End of half", "drive_play_count": 2.0},
        {"fixed_drive": 4.0, "play_type": None, "posteam": None, "qtr": 4.0,
         "game_seconds_remaining": 0.0},  # END GAME pseudo-drive
    ]  # fmt: skip


def test_drives_fields_numbering_and_end_game_dropped():
    d = _drives(wf(*drive_rows()), WG)
    assert [x.n for x in d] == [1, 2, 3]
    a, b, c = d
    assert (a.team, a.qtr, a.t0, a.t1, a.plays, a.result) == ("HOM", 1, 0, 300, 6, "Touchdown")
    assert (b.team, b.qtr, b.t0, b.plays, b.result) == ("AWY", 2, 1900, None, "Punt")
    assert (c.team, c.start_yl, c.end_yl, c.plays) == ("HOM", None, None, 2)
    assert _drives(wf(drive_rows()[5]), WG) is None


def test_drives_yard_lines_parse_from_both_sides():
    d = _drives(wf(*drive_rows()), WG)
    assert (d[0].start_yl, d[0].end_yl) == (25, 50)  # "HOM 25" for HOM, "50"
    assert (d[1].start_yl, d[1].end_yl) == (31, 60)  # "AWY 31" for AWY, "HOM 40" is its 60
    flip = {"HOM": "AWY", "AWY": "HOM"}
    rows = [r | {"posteam": flip.get(r.get("posteam", "HOM"))} for r in drive_rows()[:4]]
    d = _drives(wf(*rows), WG)
    assert (d[0].start_yl, d[0].end_yl) == (75, 50)  # AWY has the ball at "HOM 25"
    assert (d[1].start_yl, d[1].end_yl) == (69, 40)


def test_planted_partition_without_the_columns_builds_with_no_series(tree):
    build_games(tree, 2026)
    rec = RetroGame.model_validate(read(tree, "g2"))
    assert rec.wp_series is None and rec.drives is None


def _plays_dir(tmp_path, season):
    d = Paths(tmp_path).curated_table("plays") / f"season={season}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_load_plays_reads_only_its_season_when_an_older_one_lacks_columns(tmp_path):
    pl.DataFrame({"game_id": ["o"], "play_id": [1.0], "posteam": ["HOM"]}).write_parquet(
        _plays_dir(tmp_path, 2020) / "p.parquet"
    )
    pl.DataFrame({"game_id": ["n"], "play_id": [1.0], "posteam": ["OAK"], "vegas_home_wp": [0.4],
                  "fixed_drive": [1.0]}).write_parquet(_plays_dir(tmp_path, 2026) / "p.parquet")  # fmt: skip
    root = Paths(tmp_path).curated_table("plays").as_posix()
    with pytest.raises(duckdb.Error):  # the all-season glob binds to the first file's schema
        duckdb.sql(f"select vegas_home_wp from read_parquet('{root}/*/*.parquet', hive_partitioning=true)")  # fmt: skip
    df = _load_plays(Paths(tmp_path), 2026)
    assert df["game_id"].to_list() == ["n"] and df["vegas_home_wp"].to_list() == [0.4]
    assert df["posteam"].to_list() == ["LV"] and "season" not in df.columns  # canonical code
    assert df["fixed_drive_result"].dtype == pl.Utf8 and df["desc"].null_count() == 1


def test_load_plays_season_partition_predating_the_columns(tmp_path):
    paths = write_tree(tmp_path, [G1, G2], base_plays("g1") + base_plays("g2"))
    df = _load_plays(paths, 2026)
    assert set(PLAY_COLS) <= set(df.columns)
    assert df["vegas_home_wpa"].null_count() == df.height
    g2 = df.filter(pl.col("game_id") == "g2")
    assert _wp_series(g2, WG) is None and _drives(g2, WG) is None


def test_load_plays_missing_partition_is_empty_with_the_columns(tmp_path):
    df = _load_plays(Paths(tmp_path), 2026)
    assert df.is_empty() and {"vegas_home_wp", "posteam", "game_id"} <= set(df.columns)
