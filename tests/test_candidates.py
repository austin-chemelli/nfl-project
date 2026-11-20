import dataclasses

import numpy as np
import polars as pl
import pytest

from nfl import candidate_screen as cs
from nfl import candidates as cand
from nfl import catalog
from nfl.config import Paths
from nfl.sql import runner

from .synth import league, play, write_games, write_participation, write_plays

STUDENT_FIELDS = ("resid_st", "resid_mk")


def prepare(root, **kw):
    paths = Paths(root)
    plays, games = league(paths, **kw)
    write_participation(paths, [{"game_id": "x", "play_id": 1.0, "was_pressure": None,
                                 "time_to_throw": None, "season": 2020}])  # fmt: skip
    runner.build(paths, "team_week")
    return paths, plays, games


def asof_values(paths, candidate_id="net_epa"):
    con = catalog.connect(paths)
    tw = con.sql("select * from team_week where season_type = 'REG'").pl()
    games = con.sql("select * from games").pl()
    a = cs.asof_frame(cs.team_games(tw, games))
    c = cand.BY_ID[candidate_id]
    return a.select("game_id", "team", c.value().alias("v")).sort("game_id", "team")


# ---- leakage


def test_mutation_leakage_week_w_plays_never_change_week_w_values(tmp_path):
    """Changing every week-5 play moves week 6's value and leaves weeks 1-5 as they were."""
    base, plays, games = prepare(tmp_path / "a")
    mut = Paths(tmp_path / "b")
    changed = [
        p | {"epa": p["epa"] + 5.0, "success": 1.0, "sack": 1.0} if p["week"] == 5 else p
        for p in plays
    ]
    write_plays(mut, changed)
    write_games(mut, games)
    write_participation(mut, [{"game_id": "x", "play_id": 1.0, "was_pressure": None,
                               "time_to_throw": None, "season": 2020}])  # fmt: skip
    (tmp_path / "b" / "marts").mkdir(exist_ok=True)
    (tmp_path / "b" / "marts" / "predictions.parquet").write_bytes(
        (tmp_path / "a" / "marts" / "predictions.parquet").read_bytes()
    )
    runner.build(mut, "team_week")
    for cid in ("net_epa", "success_off", "sack_off", "net_wepa", "fum_luck"):
        a, b = asof_values(base, cid), asof_values(mut, cid)
        wk = pl.col("game_id").str.split("_").list.get(1).cast(pl.Int32)
        early, early_b = a.filter(wk <= 5), b.filter(wk <= 5)
        assert early.equals(early_b), cid
        late = a.filter(pl.col("game_id").str.contains("_06_"))
        late_b = b.filter(pl.col("game_id").str.contains("_06_"))
        if cid in ("net_epa", "success_off", "sack_off", "net_wepa"):
            assert not late.equals(late_b), cid


def test_asof_frame_has_no_row_for_a_teams_first_game(tmp_path):
    paths, _, _ = prepare(tmp_path)
    a = asof_values(paths)
    assert a.filter(pl.col("game_id").str.contains("_01_")).is_empty()


# ---- verdicts


def v(sh, luck=False, kind="spread", fp=None, st=None, mk=None):
    return cs.verdict(sh, luck=luck, kind=kind, future_partial_lo=fp, resid_st=st, resid_mk=mk)


def test_verdict_rules():
    assert v(0.0, luck=True) == "luck"
    assert v(0.05, luck=True, fp=0.1) == "luck"  # luck wins over a gate
    assert v(0.2) == "none"  # unstable
    assert v(0.2, fp=0.2, mk=(0.1, 0.5)) == "none"  # unstable even if a gate passes
    assert v(0.1, luck=True) == "none"  # a luck measure that is stable-ish but not stable enough
    assert v(0.3) == "context"
    assert v(0.6, fp=-0.01, st=(-0.2, 0.3), mk=(-0.1, 0.4)) == "context"
    assert v(0.6, fp=0.01) == "use"
    assert v(0.6, mk=(0.1, 0.9)) == "use"
    assert v(0.6, mk=(-0.9, -0.1)) == "use"  # the market's residual in either direction
    assert v(0.6, st=(0.1, 0.9)) == "use"
    assert v(0.6, st=(-0.9, -0.1)) == "context"  # the Student over-weights it: not a feature
    assert v(0.6, kind="total", st=(-0.9, -0.1)) == "use"
    assert v(None) == "none"  # no stability gate and no residual
    assert v(None, mk=(0.2, 0.9)) == "use"


# ---- gates and the ledger


def test_planted_strong_candidate_has_a_positive_residual_slope(tmp_path):
    paths, _, _ = prepare(tmp_path, weeks=18)
    (row,) = cs.screen(catalog.connect(paths), season_from=2020, only="net_epa")
    assert row["resid_st"] > 0.5 and row["resid_st_lo"] > 0  # the Student predicts 0: all signal
    assert row["split_half"] is not None and row["future_n"] > 0
    assert row["verdict"] in ("use", "context")


def test_slope_ci_recovers_a_planted_slope():
    rng = np.random.default_rng(0)
    x = rng.normal(size=2000)
    seasons = np.repeat(np.arange(2006, 2026), 100)
    slope, lo, hi, n = cs.slope_ci(
        x, 2.0 * x.std() * (x / x.std()) + rng.normal(size=2000), seasons
    )
    assert n == 2000 and lo < slope < hi and 1.5 < slope < 2.5 and lo > 0


def test_full_screen_runs_every_candidate_on_synthetic_data(tmp_path):
    paths, _, _ = prepare(tmp_path)
    rows = cs.screen(catalog.connect(paths), season_from=2020)
    # without the team_split_week model a full run screens everything but the split candidates
    assert [r["candidate"] for r in rows] == [
        c.id for c in cand.CANDIDATES if c.frame == "team_week"
    ]
    assert {r["verdict"] for r in rows} <= {"use", "context", "luck", "none"}


def test_unchanged_rerun_appends_nothing_and_the_ledger_is_append_only(tmp_path, monkeypatch):
    paths, _, _ = prepare(tmp_path)
    assert cs.run(paths, only="net_epa", season_from=2020) == 1
    first = pl.read_parquet(cs.ledger_path(paths))
    assert cs.run(paths, only="net_epa", season_from=2020) == 0
    assert pl.read_parquet(cs.ledger_path(paths)).equals(first)
    # a changed note is a new row; the old one is untouched
    changed = dataclasses.replace(cand.BY_ID["net_epa"], note="a new note")
    monkeypatch.setitem(cand.BY_ID, "net_epa", changed)
    assert cs.run(paths, only="net_epa", season_from=2020) == 1
    both = pl.read_parquet(cs.ledger_path(paths))
    assert both.height == 2 and both.head(1).equals(first)
    assert cs.latest(paths)["note"].to_list() == ["a new note"]
    # a new screen version appends too
    monkeypatch.setattr(cs, "SCREEN_VERSION", "2")
    assert cs.run(paths, only="net_epa", season_from=2020) == 1
    assert pl.read_parquet(cs.ledger_path(paths)).height == 3


def test_run_needs_the_team_week_model(tmp_path):
    paths = Paths(tmp_path)
    write_plays(paths, [play(season=2022)])
    write_games(
        paths, [{"game_id": "g", "season": 2022, "week": 1, "home_team": "A", "away_team": "B"}]
    )
    with pytest.raises(ValueError, match="models build"):
        cs.run(paths)


def test_unknown_candidate_is_an_error(tmp_path):
    paths, _, _ = prepare(tmp_path)
    with pytest.raises(ValueError):
        cs.run(paths, only="nope", season_from=2020)


def test_registry_is_consistent():
    ids = [c.id for c in cand.CANDIDATES]
    assert len(ids) == len(set(ids))
    for c in cand.CANDIDATES:
        assert c.kind in ("spread", "total") and c.sentence and c.label
        assert c.replaces == "" or c.replaces in cand.BASE
        assert c.outcome in (None, "off", "def", "net")
    assert {c.id for c in cand.CANDIDATES if c.interesting} == {
        "net_epa_noto", "fum_luck", "success_off", "net_wepa", "wind_15", "one_score_luck",
        "split_blitz_gap", "split_box_light_gap", "split_box_heavy_gap", "split_play_action_gap",
        "split_vs_top10_def_gap", "split_vs_top10_off_gap",
        *(c.id for c in cand.FEATURE_CANDIDATES if c.interesting),
    }  # fmt: skip


def test_postgame_candidates_never_reach_use():
    """Observed wind and the game's actual passer can't be known at a lock (ADR 0026)."""
    clear = (0.5, 1.2)
    assert cs.verdict(None, luck=False, kind="total", future_partial_lo=None,
                      resid_st=clear, resid_mk=clear, pregame=False) == "context"  # fmt: skip
    assert cs.verdict(None, luck=False, kind="total", future_partial_lo=None,
                      resid_st=clear, resid_mk=clear) == "use"  # fmt: skip
    from nfl import candidates as cand

    assert not cand.BY_ID["wind_15"].pregame and not cand.BY_ID["qb_sack_rate"].pregame
    assert {c.id for c in cand.CANDIDATES if c.in_model} == {
        "net_epa",
        "success_off",
        "sack_off",
        "sack_def",
    }


# ---- split candidates (ADR 0028, M25.2)


def test_every_split_has_a_candidate_on_the_unit_that_does_not_choose():
    from nfl import splits

    for sp in splits.SPLITS:
        c = cand.BY_ID[f"split_{sp.id}_gap"]
        assert c.frame == "team_split_week" and c.split == sp.id
        assert (c.kind, c.level, c.pregame, c.halves) == ("spread", "team", True, True)
        assert c.side == ("def" if sp.chooser == "offense" or sp.id == "vs_top10_off" else "off")
        assert c.outcome == c.side and c.good == (1 if c.side == "off" else -1)
    assert sum(c.frame == "team_split_week" for c in cand.CANDIDATES) == len(splits.SPLITS)


def _planted(n_with=50, n_without=100):
    """Two teams over weeks 1-8 of 2022; plays are per game so a half-season has 4 games of each."""
    tg_rows, tsw_rows = [], []
    for team, base in (("AAA", 0.0), ("BBB", 1.0)):
        for week in range(1, 9):
            gid = f"2022_{week:02d}_{team}"
            tg_rows.append({"game_id": gid, "season": 2022, "week": week, "team": team,
                            "games": 1.0, **{c: 0.0 for c in cs.SUM_COLS if c != "games"}})  # fmt: skip
            # the gap is `base` in odd weeks and `base + 0.5 * base` in even weeks, so teams rank the same
            gap = base * (1.0 if week % 2 else 1.5)
            for flag, n, epa in ((True, n_with, 0.1 + gap), (False, n_without, 0.1)):
                tsw_rows.append({"game_id": gid, "team": team, "side": "off", "split": "blitz",
                                 "flag": flag, "plays": n, "epa_sum": n * epa})  # fmt: skip
    return pl.DataFrame(tg_rows), pl.DataFrame(tsw_rows)


def test_split_frame_gap_is_hand_computed_and_split_half_runs_per_unit():
    tg, tsw = _planted()
    ctg = cs.split_team_games(tsw, tg, "blitz", "off")
    c = cand.BY_ID["split_blitz_gap"]
    cols = cs.SUM_COLS + cs.SPLIT_COLS
    odd = cs._agg_weeks(ctg.filter(pl.col("week") % 2 == 1), 1, 30, cols)
    g = odd.select("team", c.value().alias("g")).sort("team")
    # 4 odd games of 50 / 100 plays: sums 200 / 400, EPA (0.1 + base) * 200 and 0.1 * 400
    assert g["g"].to_list() == pytest.approx([0.0, 1.0])
    # the as-of frame carries the split columns and only earlier weeks
    a = cs.asof_frame(ctg, cols).filter(pl.col("week") == 3).sort("team")
    assert a["s_n"].to_list() == [100.0, 100.0] and a["games"].to_list() == [2.0, 2.0]
    # too few plays: the gap is null, not a noisy number
    thin = odd.with_columns(pl.lit(cand.MIN_SPLIT_PLAYS - 1.0).alias("s_n"))
    assert thin.select(c.value()).to_series().null_count() == 2
    # two teams are too few for a split-half r; the numbers come back as None, not an error
    out = cs.team_gates(c, ctg, cols)
    assert out["split_n"] == 2 and out["split_half"] is None


def test_split_half_r_on_a_planted_frame_matches_numpy():
    rng = np.random.default_rng(3)
    tg_rows, tsw_rows, truth = [], [], {}
    for k in range(40):
        team = f"T{k:02d}"
        gap = rng.normal()
        truth[team] = gap
        for week in range(1, 9):
            gid = f"2022_{week:02d}_{team}"
            tg_rows.append({"game_id": gid, "season": 2022, "week": week, "team": team,
                            "games": 1.0, **{c: 0.0 for c in cs.SUM_COLS if c != "games"}})  # fmt: skip
            noise = rng.normal(scale=0.3)
            for flag, n, epa in ((True, 40, gap + noise), (False, 80, 0.0)):
                tsw_rows.append({"game_id": gid, "team": team, "side": "off", "split": "blitz",
                                 "flag": flag, "plays": n, "epa_sum": n * epa})  # fmt: skip
    ctg = cs.split_team_games(pl.DataFrame(tsw_rows), pl.DataFrame(tg_rows), "blitz", "off")
    cols = cs.SUM_COLS + cs.SPLIT_COLS
    out = cs.team_gates(cand.BY_ID["split_blitz_gap"], ctg, cols)
    by = {}
    for r in ctg.iter_rows(named=True):
        d = by.setdefault((r["team"], r["week"] % 2), [0.0])
        d[0] += r["s_epa"] / r["s_n"] / 4
    odd = np.array([by[(f"T{k:02d}", 1)][0] for k in range(40)])
    even = np.array([by[(f"T{k:02d}", 0)][0] for k in range(40)])
    assert out["split_n"] == 40
    assert out["split_half"] == pytest.approx(np.corrcoef(odd, even)[0, 1], abs=1e-9)
    assert out["split_half"] > 0.5  # the planted gap repeats


def test_existing_candidates_are_screened_identically_with_split_candidates_registered(tmp_path):
    """The split candidates add their own frame; every earlier candidate's row is unchanged."""
    paths, _, _ = prepare(tmp_path)
    rows = cs.screen(catalog.connect(paths), season_from=2020, only="net_epa")
    assert len(rows) == 1 and rows[0]["split_n"] is not None
    with pytest.raises(ValueError, match="team_split_week"):
        cs.screen(catalog.connect(paths), season_from=2020, only="split_blitz_gap")


# ---- feature-store candidates and the shadow gate (ADR 0031)


def test_feature_candidates_are_registered_with_a_feature_and_group():
    from nfl.features.groups import GROUPS

    feats = [c for c in cand.CANDIDATES if c.frame == "features"]
    assert {c.id for c in feats} >= {"value_lost", "weather_wind", "edge_net", "edge_rpo"}
    for c in feats:
        assert c.feature and c.group in GROUPS and not c.halves and c.sentence
        assert c.good in (-1, 1)
    assert cand.BY_ID["success_off"].feature == "strength.success_off"
    assert not cand.BY_ID["weather_temp"].pregame and cand.BY_ID["weather_temp"].level == "game"


def _feature_world(tmp_path, signal=1.0, seed=4):
    """The synthetic league plus a home-minus-away feature that moves the market residual."""
    paths, _, _games = prepare(tmp_path, weeks=18)
    con = catalog.connect(paths)
    g = con.sql("select game_id, result, spread_line from games where game_type = 'REG'").pl()
    rng = np.random.default_rng(seed)
    x = rng.normal(size=g.height)
    resid = signal * x + rng.normal(size=g.height)
    g = g.with_columns(pl.Series("availability.value_lost", x))
    return paths, con, g.select("game_id", "availability.value_lost"), resid


def test_feature_candidate_residual_is_a_walk_forward_slope_on_the_stored_value(tmp_path):
    _paths, con, fdata, _ = _feature_world(tmp_path)
    c = cand.BY_ID["value_lost"]  # good = -1: a higher value lost hurts the home team
    games = cs.game_sample(con, 2020)
    # plant: the market misses -x (home loses when it loses more value), 1 point per SD
    rng = np.random.default_rng(1)
    games = games.join(fdata, on="game_id").with_columns(
        (pl.col("spread_line") - pl.col("availability.value_lost")
         + pl.Series(rng.normal(size=games.height) * 0.5)).alias("result")
    )  # fmt: skip
    out = cs.residual_gates(c, games, None, None, fdata)
    assert out["resid_n"] > 100
    assert out["resid_mk"] > 0.5 and out["resid_mk_lo"] > 0  # oriented by good: positive = helps


def test_screen_runs_a_feature_candidate_and_skips_them_without_a_store(tmp_path, monkeypatch):
    paths, con, fdata, _ = _feature_world(tmp_path)
    assert all(r["candidate"] != "value_lost" for r in cs.screen(con, season_from=2020))
    with pytest.raises(ValueError, match="feature"):
        cs.screen(con, season_from=2020, only="value_lost")
    monkeypatch.setattr(
        cs, "shadow_dataset", lambda p, ch: (None, fdata, {"availability.value_lost"})
    )
    monkeypatch.setattr(cs, "shadow_gate", lambda *a, **k: dict.fromkeys(cs.SHADOW_COLS))
    (row,) = cs.screen(con, season_from=2020, only="value_lost", paths=paths, shadow_on=False)
    assert row["resid_n"] > 0 and row["split_half"] is None and row["shadow_delta"] is None
    assert row["verdict"] in ("use", "context", "none")


def test_verdict_model_only_when_the_shadow_ci_is_below_zero():
    kw = {"luck": False, "kind": "spread", "future_partial_lo": None, "resid_st": None,
          "resid_mk": (0.2, 0.9)}  # fmt: skip
    assert cs.verdict(None, **kw, shadow=(-0.004, -0.001)) == "model"
    assert cs.verdict(None, **kw, shadow=(-0.004, 0.0005)) == "context"  # 'use' needs the shadow
    assert cs.verdict(None, **kw, shadow=(0.001, 0.004)) == "context"
    assert cs.verdict(None, **kw) == "use"  # no shadow run: the first three gates decide
    assert cs.verdict(None, **kw, shadow=(-0.004, -0.001), pregame=False) == "context"
    assert cs.verdict(0.0, **{**kw, "luck": True}, shadow=(0.0, 0.1)) == "luck"
    assert cs.verdict(0.2, **kw, shadow=(0.0, 0.1)) == "none"


def test_shadow_gate_pairs_the_student_with_and_without_a_member():
    from nfl.approaches import shadow
    from nfl.approaches.schema import load_all

    from .test_fit import toy_data

    st = load_all()["student"]
    data = toy_data(st, seasons=range(2012, 2026), per=200)
    rng = np.random.default_rng(5)
    data = data.with_columns(pl.Series("front.int_worthy_rate", rng.standard_normal(data.height)))
    base = shadow.backtest(st, data, scored=(2016, 2025), lam=100.0)
    c = cand.BY_ID["int_worthy_rate"]
    seen = {}
    real = shadow.backtest
    seen["calls"] = 0

    def counting(*a, **k):
        seen["calls"] += 1
        return real(*a, **k | {"scored": (2016, 2025), "lam": 100.0})

    import pytest as _p

    mp = _p.MonkeyPatch()
    mp.setattr(shadow, "backtest", counting)
    try:
        out = cs.shadow_gate(None, c, data, base, st)
    finally:
        mp.undo()
    assert seen["calls"] == 1  # only the variant; the base is the caller's
    assert out["shadow_lo"] <= out["shadow_delta"] <= out["shadow_hi"]
    assert out["shadow_from"] == 2022 and out["shadow_n"] > 0
    # a feature the data lacks (or that is all null) has no shadow
    nulled = data.with_columns(pl.lit(None, dtype=pl.Float64).alias("front.int_worthy_rate"))
    assert cs.shadow_gate(None, c, nulled, base, st)["shadow_delta"] is None


def test_unchanged_rerun_with_shadow_columns_appends_nothing(tmp_path, monkeypatch):
    paths, _con, fdata, _ = _feature_world(tmp_path)
    monkeypatch.setattr(
        cs, "shadow_dataset", lambda p, ch: (None, fdata, {"availability.value_lost"})
    )
    fake = {"shadow_delta": -0.002, "shadow_lo": -0.004, "shadow_hi": -0.0005,
            "shadow_n": 1000, "shadow_from": 2016}  # fmt: skip
    monkeypatch.setattr(cs, "shadow_gate", lambda *a, **k: dict(fake))
    import nfl.approaches.shadow as sh

    monkeypatch.setattr(sh, "backtest", lambda *a, **k: None)
    assert cs.run(paths, only="value_lost", season_from=2020) == 1
    assert cs.latest(paths)["verdict"].to_list() == ["model"]
    assert cs.run(paths, only="value_lost", season_from=2020) == 0
    # --no-shadow carries the last shadow numbers instead of nulling them (so no new row)
    assert cs.run(paths, only="value_lost", season_from=2020, shadow_on=False) == 0
    # old ledgers without the shadow columns read with nulls
    old = pl.read_parquet(cs.ledger_path(paths)).drop(cs.SHADOW_COLS)
    old.write_parquet(cs.ledger_path(paths))
    assert cs.latest(paths)["shadow_delta"].to_list() == [None]
