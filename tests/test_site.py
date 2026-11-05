"""Site JSON contract: statuses, structure, and the rule that previews never override locks."""

import json
from datetime import datetime

import polars as pl
import pytest

from nfl import site
from nfl.config import Paths
from nfl.predict import PRED_SCHEMA
from tests.conftest import DATA

GAMES = pl.DataFrame(
    {
        "game_id": ["A", "B"],
        "season": [2026, 2026],
        "week": [8, 8],
        "kickoff_utc": [datetime(2026, 10, 25, 17), datetime(2026, 11, 1, 18)],
    }
)


def pred(gid, mid, lock, backfill, p):
    return {"game_id": gid, "season": 2026, "week": 8, "model_id": mid, "model_version": "x",
            "lock_ts": lock, "data_snapshot_ts": "s", "p_home": p, "spread_home": 1.0, "total": 44.0,
            "sd_margin": 13.5, "is_backfill": backfill, "slot": None if backfill else "sat",
            "contributions": None}  # fmt: skip


def test_best_rows_prefers_last_lock_before_kickoff_over_backfill(tmp_path):
    paths = Paths(tmp_path)
    paths.marts.mkdir(parents=True)
    rows = [
        pred("A", "m", datetime(2026, 10, 25, 16), True, 0.50),  # backfill
        pred("A", "m", datetime(2026, 10, 24, 16), False, 0.60),  # a real lock: wins
        pred("A", "m", datetime(2026, 10, 25, 18), False, 0.70),  # after kickoff: ignored
        pred("B", "m", datetime(2026, 11, 1, 17), True, 0.40),
    ]
    pl.DataFrame(rows, schema=PRED_SCHEMA).write_parquet(paths.marts / "predictions.parquet")
    best = {
        r["game_id"]: r
        for r in site.best_rows(paths, GAMES, datetime(2026, 10, 26)).iter_rows(named=True)
    }
    assert best["A"]["status"] == site.LOCKED and best["A"]["p_home"] == 0.60
    assert best["B"]["status"] == site.BACKFILL


def _band_inputs(n_teams: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Two weeks of `n_teams` teams, paired off; team i's week-2 value is i."""
    known = datetime(2026, 10, 1)
    games, feats = [], []
    for week, kick in ((1, datetime(2026, 10, 2)), (2, datetime(2026, 10, 9))):
        for i in range(0, n_teams, 2):
            gid = f"{week}_{i}"
            games.append({"game_id": gid, "kickoff_utc": kick, "home_team": f"T{i}", "away_team": f"T{i + 1}"})  # fmt: skip
            for side, v in (("home", i), ("away", i + 1)):
                value = float(v) if week == 2 else -100.0  # week 1 must lose to the later game
                feats.append({"game_id": gid, "feature": "f.x", "side": side, "value": value, "known_as_of": known})  # fmt: skip
    feats.append({"game_id": "2_0", "feature": "f.game", "side": "game", "value": 1.0, "known_as_of": known})  # fmt: skip
    return pl.DataFrame(games), pl.DataFrame(feats)


def test_feature_bands_use_each_teams_latest_value_and_skip_game_features():
    games, feats = _band_inputs(32)
    bands = site.feature_bands(feats, games, datetime(2026, 10, 20))
    assert list(bands) == ["f.x"]
    assert bands["f.x"] == {
        "lo": 3.1,
        "q1": 7.75,
        "med": 15.5,
        "q3": 23.25,
        "hi": 27.9,
    }  # teams 0..31


def test_feature_bands_ignore_rows_not_known_yet_and_thin_features():
    games, feats = _band_inputs(32)
    assert site.feature_bands(feats, games, datetime(2026, 9, 1)) == {}
    games, feats = _band_inputs(10)
    assert site.feature_bands(feats, games, datetime(2026, 10, 20)) == {}


@pytest.mark.skipif(
    not (DATA.site / "meta.json").exists(), reason="needs marts/site (run nfl site)"
)
def test_real_contract_shape():
    meta = json.loads((DATA.site / "meta.json").read_text())
    assert meta["schema_version"] == site.SCHEMA_VERSION
    assert {"models", "approaches", "groups", "weeks", "current_week"} <= set(meta)
    sl = json.loads(
        (DATA.site / f"slate_{meta['season']}_{meta['current_week']:02d}.json").read_text()
    )
    for g in sl["games"]:
        for m in g["models"].values():
            assert m["status"] in (site.LOCKED, site.BACKFILL, site.PREVIEW, site.PREGAME)
            assert 0 < m["p_home"] < 1
        detail = json.loads((DATA.site / "game" / f"{g['game_id']}.json").read_text())
        assert {"contributions", "features", "tendencies", "injuries", "narrative"} <= set(detail)


def test_write_retro_publishes_only_2026_and_validates(tmp_path):
    import shutil
    from pathlib import Path

    from nfl import publish
    from nfl.retro.schema import RetroGame, WeekRecap

    fix = Path(__file__).parent / "fixtures" / "retro"
    paths = Paths(tmp_path)
    for season in (2025, 2026):
        d = paths.marts / "retro" / f"season={season}"
        d.mkdir(parents=True)
        shutil.copy(fix / "game_2026_08_CAR_GB.json", d / "2026_08_CAR_GB.json")
        shutil.copy(fix / "recap_2026_08.json", d / "recap_08.json")
    (paths.marts / "retro" / "season=2026" / "bad.json").write_text("{}")
    assert site.write_retro(paths, 2025) == []
    assert not paths.site.exists()
    names = site.write_retro(paths, 2026)
    assert sorted(names) == ["recap_2026_08.json", "retro/2026_08_CAR_GB.json"]
    RetroGame.model_validate_json((paths.site / "retro" / "2026_08_CAR_GB.json").read_text())
    WeekRecap.model_validate_json((paths.site / "recap_2026_08.json").read_text())
    planned = publish.plan(paths, repo=tmp_path)
    assert any(k.endswith("/retro/2026_08_CAR_GB.json") for k in planned)
    assert any(k.endswith("/recap_2026_08.json") for k in planned)


# ------------------------------------------------------------------------------------ slate card


def _g(gid, kick, home, away, hq=None, aq=None, week=8):
    return {"game_id": gid, "season": 2026, "week": week, "kickoff_utc": kick,
            "home_team": home, "away_team": away, "home_qb_name": hq, "away_qb_name": aq}  # fmt: skip


def _starts(rows):
    return site._qb_starts(pl.DataFrame(rows))


def test_usual_qb_most_frequent_wins_and_both_home_and_away_count():
    rows = [
        _g("1", datetime(2026, 9, 10), "BAL", "KC", "Lamar", "Mahomes"),
        _g("2", datetime(2026, 9, 17), "KC", "BAL", "Mahomes", "Lamar"),
        _g("3", datetime(2026, 9, 24), "BAL", "KC", "Backup", "Mahomes"),
    ]
    st = _starts(rows)
    assert site._usual_qb(st, "BAL", datetime(2026, 10, 1)) == "Lamar"  # 1 home + 1 away vs 1
    assert site._usual_qb(st, "KC", datetime(2026, 10, 1)) == "Mahomes"


def test_usual_qb_tie_goes_to_most_recent():
    rows = [
        _g("1", datetime(2026, 9, 10), "BAL", "KC", "A", "X"),
        _g("2", datetime(2026, 9, 17), "KC", "BAL", "X", "B"),
    ]
    assert site._usual_qb(_starts(rows), "BAL", datetime(2026, 10, 1)) == "B"


def test_usual_qb_ignores_the_game_itself_later_games_and_missing_names():
    k = datetime(2026, 9, 24)
    rows = [
        _g("1", datetime(2026, 9, 10), "BAL", "KC", None, "X"),
        _g("2", k, "BAL", "KC", "Now", "X"),
        _g("3", datetime(2026, 10, 1), "BAL", "KC", "Later", "X"),
    ]
    st = _starts(rows)
    assert site._usual_qb(st, "BAL", k) is None
    assert site._usual_qb(st, "BAL", datetime(2026, 9, 25)) == "Now"
    assert site._usual_qb(st, "NYJ", k) is None


def _tend(overrides: dict, n=32, season=2026, situation="all"):
    """n teams T00.. with rate = index/100 for every metric used by CONTRASTS, side-wise;
    `overrides` maps (side, metric, team) -> rate."""
    metrics = {("off", m) for m, *_ in site.CONTRASTS} | {("def", d) for *_, d, _ in site.CONTRASTS}
    rows = []
    for side, metric in sorted(metrics):
        for i in range(n):
            team = f"T{i:02d}"
            rate = overrides.get((side, metric, team), 0.30 + i / 1000)
            rows.append({"season": season, "situation": situation, "team": team, "side": side,
                         "metric": metric, "rate": rate})  # fmt: skip
    return pl.DataFrame(rows)


GAME = {"away_team": "T00", "home_team": "T01"}


def test_contrast_finds_stark_pair_pass_heavy_vs_blitz_heavy():
    tend = _tend({("off", "pass_rate", "T00"): 0.9, ("def", "blitz_rate", "T01"): 0.9})
    c = site._contrast(site._contrast_ranks(tend, 2026), GAME)
    assert c == {"offense": "T00", "defense": "T01", "off_label": "pass-heavy",
                 "def_label": "blitz-heavy", "off_rank": 1, "def_rank": 1}  # fmt: skip


def test_contrast_run_heavy_uses_low_pass_rate_as_extreme():
    tend = _tend({("off", "pass_rate", "T01"): 0.01, ("def", "box_8plus_vs_run_rate", "T00"): 0.9})
    c = site._contrast(site._contrast_ranks(tend, 2026), GAME)
    assert c["offense"] == "T01" and c["defense"] == "T00"
    assert (c["off_label"], c["def_label"], c["off_rank"], c["def_rank"]) == ("run-heavy", "stacked-box", 1, 1)  # fmt: skip


def test_contrast_none_when_one_side_outside_top_five():
    # T00's pass_rate is rank 1, T01's blitz_rate is only 6th (five teams are higher)
    ov = {("off", "pass_rate", "T00"): 0.9, ("def", "blitz_rate", "T01"): 0.5}
    for i in range(10, 15):
        ov[("def", "blitz_rate", f"T{i}")] = 0.6
    assert site._contrast(site._contrast_ranks(_tend(ov), 2026), GAME) is None
    ov[("def", "blitz_rate", "T14")] = 0.4  # now T01 is 5th
    assert site._contrast(site._contrast_ranks(_tend(ov), 2026), GAME)["def_rank"] == 5


def test_contrast_lowest_rank_sum_wins_then_earlier_entry_then_away_first():
    # pass-heavy sums 2+3, screen-heavy sums 1+3: the lower sum wins despite the later entry
    ov = {("off", "pass_rate", "T00"): 0.9, ("off", "pass_rate", "T22"): 0.95,
          ("off", "screen_rate", "T00"): 0.9, ("def", "blitz_rate", "T01"): 0.9,
          ("def", "blitz_rate", "T21"): 0.95, ("def", "blitz_rate", "T22"): 0.92}  # fmt: skip
    c = site._contrast(site._contrast_ranks(_tend(ov), 2026), GAME)
    assert (c["off_label"], c["off_rank"], c["def_rank"]) == ("screen-heavy", 1, 3)
    # exact tie on sums: pass-heavy (entry 0) vs screen-heavy (entry 1), both 1+1
    ov = {("off", "pass_rate", "T00"): 0.9, ("off", "screen_rate", "T00"): 0.9,
          ("def", "blitz_rate", "T01"): 0.9}  # fmt: skip
    assert site._contrast(site._contrast_ranks(_tend(ov), 2026), GAME)["off_label"] == "pass-heavy"
    # same entry, both directions 1+1: away offense first
    ov = {("off", "pass_rate", "T00"): 0.9, ("off", "pass_rate", "T01"): 0.9,
          ("def", "blitz_rate", "T00"): 0.9, ("def", "blitz_rate", "T01"): 0.9}  # fmt: skip
    ranks = site._contrast_ranks(_tend({k: v + (0.01 if k[2] == "T00" else 0) for k, v in ov.items()}), 2026)  # fmt: skip
    # all four are top-2; away offense (T00) vs home defense (T01): 1+2; reverse: 2+1 -> away first
    assert site._contrast(ranks, GAME)["offense"] == "T00"


def test_contrast_skips_thin_metrics_other_seasons_and_situations():
    ov = {("off", "pass_rate", "T00"): 0.9, ("def", "blitz_rate", "T01"): 0.9}
    assert site._contrast(site._contrast_ranks(_tend(ov, n=23), 2026), GAME) is None
    assert site._contrast(site._contrast_ranks(_tend(ov, season=2025), 2026), GAME) is None
    assert site._contrast(site._contrast_ranks(_tend(ov, situation="3rd"), 2026), GAME) is None
    assert site._contrast_ranks(pl.DataFrame(), 2026) == {}


def test_contrast_maps_aliased_codes_back_to_the_games_codes():
    # tendencies print LV for every season; this game still uses OAK
    tend = _tend({("off", "pass_rate", "T05"): 0.9, ("def", "blitz_rate", "T06"): 0.9})
    tend = tend.with_columns(pl.col("team").replace({"T05": "LV", "T06": "LA"}))
    from nfl.models import elo

    assert elo.TEAM_ALIASES.get("OAK") == "LV" and elo.TEAM_ALIASES.get("STL") == "LA"
    c = site._contrast(site._contrast_ranks(tend, 2026), {"away_team": "OAK", "home_team": "STL"})
    assert (c["offense"], c["defense"], c["off_rank"], c["def_rank"]) == ("OAK", "STL", 1, 1)


def test_card_injuries_keep_out_and_doubtful_for_this_week_and_teams_only():
    def inj(team, status, week=8, player="P"):
        return {"week": week, "team": team, "player": player, "pos": "WR", "status": status,
                "practice": None, "injury": "knee"}  # fmt: skip

    injuries = [inj("BAL", "Out", player="a"), inj("KC", "DOUBTFUL", player="b"),
                inj("BAL", "Questionable"), inj("BAL", "Out", week=7), inj("NYJ", "Out"),
                inj("KC", None)]  # fmt: skip
    g = _g("G", datetime(2026, 10, 25, 17), "BAL", "KC")
    card = site._card(g, {}, injuries, datetime(2026, 10, 20), {}, {}, pl.DataFrame())
    assert card["injuries"] == [
        {"team": "BAL", "player": "a", "pos": "WR", "status": "Out"},
        {"team": "KC", "player": "b", "pos": "WR", "status": "DOUBTFUL"},
    ]


def test_card_with_no_data_has_empty_values():
    g = _g("G", datetime(2026, 10, 25, 17), "BAL", "KC")
    card = site._card(g, {}, [], datetime(2026, 10, 20), {}, {}, pl.DataFrame())
    assert card == {"edges": {}, "injuries": [], "usual_qb": {"home": None, "away": None},
                    "weather_concern": None, "contrast": None}  # fmt: skip


def test_card_weather_concern_is_cut_at_min_kickoff_now():
    wx = pl.DataFrame({
        "game_id": ["G", "G", "G"], "feature": [site.WEATHER_FEATURE] * 3, "side": ["game"] * 3,
        "value": [0.0, 0.5, 1.0],
        "known_as_of": [datetime(2026, 10, 1), datetime(2026, 10, 18), datetime(2026, 10, 24)],
    })  # fmt: skip
    g = _g("G", datetime(2026, 10, 25, 17), "BAL", "KC")
    assert site._card(g, {}, [], datetime(2026, 10, 20), {}, {}, wx)["weather_concern"] == 0.5  # fmt: skip
    assert site._card(g, {}, [], datetime(2026, 11, 20), {}, {}, wx)["weather_concern"] == 1.0
    assert site._card(g, {}, [], datetime(2026, 9, 20), {}, {}, wx)["weather_concern"] is None
