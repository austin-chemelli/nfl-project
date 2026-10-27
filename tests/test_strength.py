"""Strength builder: shrinkage, week-1 prior, leakage, and the Elo pre-game walk."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from nfl.features import store, strength
from nfl.models.elo import Elo, pregame_ratings
from tests.conftest import DATA, requires_data

T0 = datetime(2023, 9, 10, 17, 0)
BUILD = datetime(2024, 9, 1)

# (id, season, week, days after T0, home, away, result)
SCHEDULE = [
    ("g1", 2023, 1, 0, "A", "B", 10.0),
    ("g2", 2023, 2, 7, "B", "A", -3.0),
    ("g3", 2024, 1, 365, "A", "B", 6.0),
    ("g4", 2024, 2, 372, "B", "A", 0.0),
    ("g5", 2024, 3, 379, "A", "C", None),  # upcoming
]


def games_frame():
    return pl.DataFrame(
        {
            "game_id": [s[0] for s in SCHEDULE],
            "season": [s[1] for s in SCHEDULE],
            "week": [s[2] for s in SCHEDULE],
            "kickoff_utc": [T0 + timedelta(days=s[3]) for s in SCHEDULE],
            "home_team": [s[4] for s in SCHEDULE],
            "away_team": [s[5] for s in SCHEDULE],
            "result": [s[6] for s in SCHEDULE],
            "home_score": [None if s[6] is None else 20.0 + max(s[6], 0.0) for s in SCHEDULE],
            "away_score": [None if s[6] is None else 20.0 + max(-s[6], 0.0) for s in SCHEDULE],
            "location": ["Home"] * len(SCHEDULE),
        }
    )


# (game_id, posteam, epas, successes)
PLAYS = {
    "g1": [("A", [0.5, 0.1, 0.3], [1, 0, 1]), ("B", [-0.2, -0.4], [0, 0])],
    "g2": [("B", [0.2, 0.0], [1, 0]), ("A", [0.4, 0.6, 0.2, 0.0], [1, 1, 0, 0])],
    "g3": [("A", [1.0, 0.0], [1, 0]), ("B", [0.5], [1])],
    "g4": [("B", [0.3, 0.3], [1, 1]), ("A", [-0.5], [0])],
    "g5": [("A", [9.0], [1]), ("C", [9.0], [1])],
}
OPP = {"g1": "AB", "g2": "BA", "g3": "AB", "g4": "BA", "g5": "AC"}


PLAY_SCHEMA = {
    "game_id": pl.Utf8, "posteam": pl.Utf8, "defteam": pl.Utf8, "play_type": pl.Utf8,
    "epa": pl.Float64, "success": pl.Float64, "down": pl.Float64, "wp": pl.Float64,
    "is_pass": pl.Float64, "sack": pl.Float64, "qb_dropback": pl.Float64,
    "special_teams_play": pl.Float64, "passer_player_id": pl.Utf8, "passer_player_name": pl.Utf8,
    "qb_epa": pl.Float64, "cpoe": pl.Float64,
}  # fmt: skip


def make_plays(rows: list[dict]) -> pl.DataFrame:
    """Rows are dicts with any subset of PLAY_SCHEMA; defaults describe a plain 1st-down pass."""
    default = {
        "play_type": "pass", "down": 1.0, "wp": 0.5, "is_pass": 1.0, "sack": 0.0,
        "qb_dropback": 1.0, "special_teams_play": 0.0, "success": 0.0,
    }  # fmt: skip
    return pl.DataFrame([{**default, **r} for r in rows], schema=PLAY_SCHEMA)


def plays_frame(override: dict | None = None):
    data = {**PLAYS, **(override or {})}
    rows = []
    for gid, sides in data.items():
        for team, epas, succ in sides:
            other = next(t for t in OPP[gid] if t != team)
            rows += [
                {"game_id": gid, "posteam": team, "defteam": other, "epa": e, "success": float(s)}
                for e, s in zip(epas, succ)
            ]
    return make_plays(rows)


def feat(vals: pl.DataFrame, gid: str, team: str, name: str) -> float:
    r = vals.filter(
        (pl.col("game_id") == gid) & (pl.col("team") == team) & (pl.col("feature") == name)
    )
    assert r.height == 1
    return r["value"][0]


def shrunk(sx, n, prior, n0=300.0):
    return (sx + n0 * prior) / (n + n0)


def test_shrinkage_and_week1_prior():
    vals = strength.compute(games_frame(), plays_frame())
    # 2023 (no previous season): epa prior 0, success prior 0.43; week 1 equals the prior exactly
    assert feat(vals, "g1", "A", "strength.epa_off") == pytest.approx(0.0)
    assert feat(vals, "g1", "B", "strength.success_def") == pytest.approx(0.43)
    assert feat(vals, "g1", "A", "strength.point_diff_pg") == pytest.approx(0.0)
    # g2: A offense has 3 plays (sum 0.9) from g1; B defense allowed those
    assert feat(vals, "g2", "A", "strength.epa_off") == pytest.approx(shrunk(0.9, 3, 0.0))
    assert feat(vals, "g2", "B", "strength.epa_def") == pytest.approx(shrunk(0.9, 3, 0.0))
    assert feat(vals, "g2", "A", "strength.success_off") == pytest.approx(shrunk(2, 3, 0.43))
    # point diff: A won g1 by 10, n0 = 4, prior 0
    assert feat(vals, "g2", "A", "strength.point_diff_pg") == pytest.approx(10 / 5)
    assert feat(vals, "g2", "B", "strength.point_diff_pg") == pytest.approx(-10 / 5)

    # 2024 week 1 = 0.7 * team's 2023 value + 0.3 * 2023 league mean
    a_23, a_n = 0.9 + 1.2, 7  # A off: g1 (0.9) + g2 (1.2)
    b_23, b_n = -0.6 + 0.2, 4
    league = (a_23 + b_23) / (a_n + b_n)
    prior_a = 0.7 * a_23 / a_n + 0.3 * league
    assert feat(vals, "g3", "A", "strength.epa_off") == pytest.approx(prior_a)
    # defense: A allowed B's plays (-0.6 in g1, 0.2 in g2) over 4 plays
    prior_a_def = 0.7 * (-0.4 / 4) + 0.3 * league
    assert feat(vals, "g3", "A", "strength.epa_def") == pytest.approx(prior_a_def)
    # point diff: A 2023 = (+10 +3)/2 = 6.5 per game, prior 0.5 * 6.5
    assert feat(vals, "g3", "A", "strength.point_diff_pg") == pytest.approx(3.25)
    # g4 for A: one 2024 game (sum 1.0, n 2) on top of the prior
    assert feat(vals, "g4", "A", "strength.epa_off") == pytest.approx(shrunk(1.0, 2, prior_a))
    # C has no previous season: prior falls back to the previous-season league mean
    assert feat(vals, "g5", "C", "strength.epa_off") == pytest.approx(league)
    assert feat(vals, "g5", "C", "strength.point_diff_pg") == pytest.approx(0.0)


def test_no_leakage_from_target_or_later_games():
    games = games_frame()
    base = strength.compute(games, plays_frame())
    mutated = strength.compute(
        games,
        plays_frame(
            {
                "g4": [("B", [50.0], [1]), ("A", [-50.0], [0])],
                "g5": [("A", [-9.0], [0]), ("C", [-9.0], [0])],
            }
        ),
    )
    names = base["feature"].unique().to_list()
    for gid in ("g1", "g2", "g3", "g4"):
        for team in ("A", "B"):
            for f in names:
                assert feat(base, gid, team, f) == feat(mutated, gid, team, f), (gid, team, f)
    # sanity: changing an earlier game does change later features
    earlier = strength.compute(games, plays_frame({"g3": [("A", [5.0], [1]), ("B", [0.5], [1])]}))
    assert feat(earlier, "g4", "A", "strength.epa_off") != feat(base, "g4", "A", "strength.epa_off")


def test_build_rows_through_store(tmp_path, monkeypatch):
    monkeypatch.setattr(strength, "load_plays_all", lambda paths, min_season: plays_frame())
    rows = strength.build(None, games_frame(), BUILD)  # type: ignore[arg-type]
    assert rows.height == 5 * 2 * 22
    assert set(rows["source"]) == {"pbp"} and set(rows["version"]) == {"2"}
    store.validate(rows)
    g5 = rows.filter(pl.col("game_id") == "g5")
    assert set(g5["known_as_of"]) == {BUILD}  # upcoming game stamped at build time
    g1 = rows.filter(pl.col("game_id") == "g1")
    assert set(g1["known_as_of"]) == {T0 - store.BACKTEST_ASOF_OFFSET}


def test_pregame_ratings_match_elo_predict():
    games = games_frame().with_columns(
        pl.when(pl.col("game_id") == "g2")
        .then(pl.lit("Neutral"))
        .otherwise(pl.lit("Home"))
        .alias("location")
    )
    out = pregame_ratings(games).sort("game_id")
    e = Elo()
    expected = {}
    for g in games.sort("kickoff_utc").iter_rows(named=True):
        e.new_season(g["season"])
        p = e.predict(g["home_team"], g["away_team"])
        expected[g["game_id"]] = (p["elo_home"], p["elo_away"])
        if g["result"] is not None:
            e.update(g["home_team"], g["away_team"], g["result"], g["location"] != "Home")
    for r in out.iter_rows(named=True):
        assert (r["home_elo"], r["away_elo"]) == pytest.approx(expected[r["game_id"]])
    assert out.filter(pl.col("game_id") == "g1")["home_elo"][0] == 1500.0


@requires_data
def test_elo_pre_matches_asof_walk_on_real_2024():
    games = store.games_frame(DATA).filter(pl.col("season") >= 2023)
    got = pregame_ratings(store.games_frame(DATA)).join(games.select("game_id"), on="game_id")
    sample = games.filter(pl.col("season") == 2024).sort("kickoff_utc", "game_id")
    targets = set(sample["game_id"].to_list()[::17])
    all_games = store.games_frame(DATA).sort("kickoff_utc", "game_id")
    e = Elo()
    want = {}
    for g in all_games.iter_rows(named=True):
        e.new_season(g["season"])
        if g["game_id"] in targets:
            want[g["game_id"]] = (e.rating(g["home_team"]), e.rating(g["away_team"]))
        if g["result"] is not None:
            e.update(
                g["home_team"], g["away_team"], g["result"], (g["location"] or "Home") != "Home"
            )
    assert len(want) >= 10
    for r in got.filter(pl.col("game_id").is_in(list(targets))).iter_rows(named=True):
        assert (r["home_elo"], r["away_elo"]) == pytest.approx(want[r["game_id"]])


@requires_data
def test_relocated_teams_get_their_plays():
    """pbp prints LA/LAC/LV for every season; STL/SD/OAK-era games must still see their plays."""
    import polars as pl

    from nfl.features import store

    f = store.read_features(DATA, seasons=(2012, 2012), families=["strength"])
    if f.is_empty():
        import pytest

        pytest.skip("feature store not built")
    late = f.filter((pl.col("feature") == "strength.epa_off") & (pl.col("week") >= 8))
    g = store.games_frame(DATA).select("game_id", "home_team", "away_team")
    team = late.join(g, on="game_id").with_columns(
        pl.when(pl.col("side") == "home").then("home_team").otherwise("away_team").alias("team")
    )
    vals = team.filter(pl.col("team").is_in(["STL", "SD", "OAK"]))
    assert vals.select(pl.col("value").n_unique()).item() > 3


# ---- M1.11 extras -------------------------------------------------------------------------------


def play(gid, off, deff, epa, **kw):
    return {"game_id": gid, "posteam": off, "defteam": deff, "epa": epa, **kw}


def test_pythag_luck_sos_and_week1_priors():
    games = games_frame()
    vals = strength.compute(games, plays_frame())
    elo = pregame_ratings(games)
    b_elo_g1 = elo.filter(pl.col("game_id") == "g1")["away_elo"][0]
    # week 1: pythag 0.5, luck 0, sos 1505 (the league prior), in every season
    for gid in ("g1", "g3"):
        assert feat(vals, gid, "A", "strength.pythag_win_pct") == pytest.approx(0.5)
        assert feat(vals, gid, "A", "strength.luck") == pytest.approx(0.0)
        assert feat(vals, gid, "A", "strength.sos") == pytest.approx(1505.0)
    # g2: A won g1 30-20 (n = 1)
    raw = 30**2.37 / (30**2.37 + 20**2.37)
    assert feat(vals, "g2", "A", "strength.pythag_win_pct") == pytest.approx((raw + 4 * 0.5) / 5)
    assert feat(vals, "g2", "A", "strength.luck") == pytest.approx(1 / 5 * (1.0 - raw))
    assert feat(vals, "g2", "B", "strength.luck") == pytest.approx(1 / 5 * (0.0 - (1 - raw)))
    assert feat(vals, "g2", "A", "strength.sos") == pytest.approx(b_elo_g1)
    # g5: A is 1-0-1 in 2024 (g3 won 26-20, g4 tied 20-20): ties count half
    pf, pa = 26 + 20, 20 + 20
    raw = pf**2.37 / (pf**2.37 + pa**2.37)
    assert feat(vals, "g5", "A", "strength.luck") == pytest.approx(2 / 6 * (0.75 - raw))
    assert feat(vals, "g5", "A", "strength.pythag_win_pct") == pytest.approx((2 * raw + 2) / 6)
    # sos at g5 = mean of B's pre-game Elo in g3 and g4 (A's opponents)
    b_elo = [
        elo.filter(pl.col("game_id") == "g3")["away_elo"][0],
        elo.filter(pl.col("game_id") == "g4")["home_elo"][0],
    ]
    assert feat(vals, "g5", "A", "strength.sos") == pytest.approx(sum(b_elo) / 2)


def test_pass_rush_splits_early_nongarbage_and_sack_rate():
    # game g1 (2023, no previous season -> priors are the defaults), A on offense, then g2 reads it
    rows = [
        play("g1", "A", "B", 0.5, down=1.0, wp=0.5),  # pass, early, in the wp band
        play("g1", "A", "B", 0.1, down=3.0, wp=0.95, sack=1.0),  # sack: a pass, garbage time
        play("g1", "A", "B", 0.3, down=2.0, wp=0.05, is_pass=0.0, qb_dropback=0.0, play_type="run"),
        play("g1", "B", "A", -0.2, down=1.0, wp=0.5),
        play("g2", "B", "A", 7.7),  # the target game itself: must not count
    ]
    vals = strength.compute(games_frame(), make_plays(rows))
    f = lambda team, name: feat(vals, "g2", team, name)
    assert f("A", "strength.epa_pass_off") == pytest.approx((0.5 + 0.1) / (2 + 180))
    assert f("A", "strength.epa_rush_off") == pytest.approx(0.3 / (1 + 120))
    assert f("B", "strength.epa_pass_def") == pytest.approx((0.5 + 0.1) / (2 + 180))
    assert f("B", "strength.epa_rush_def") == pytest.approx(0.3 / (1 + 120))
    assert f("A", "strength.epa_early_off") == pytest.approx((0.5 + 0.3) / (2 + 300))
    assert f("A", "strength.epa_nongarbage_off") == pytest.approx(0.5 / (1 + 300))
    # dropbacks = pass 1 + sack (2 for A); the run is not a dropback
    assert f("A", "strength.sack_rate_off") == pytest.approx((1 + 150 * 0.065) / (2 + 150))
    assert f("B", "strength.sack_rate_def") == pytest.approx((1 + 150 * 0.065) / (2 + 150))
    assert f("B", "strength.sack_rate_off") == pytest.approx((0 + 150 * 0.065) / (1 + 150))
    # splits are components of epa_off: with no previous season the plain feature uses n0 = 300
    assert f("A", "strength.epa_off") == pytest.approx(0.9 / (3 + 300))


def test_special_teams_epa_is_zero_sum_and_demeaned():
    kick = {"special_teams_play": 1.0, "is_pass": 0.0, "qb_dropback": 0.0}
    rows = [
        # kickoff: posteam = receiver. A kicks to B (B +0.4), B kicks to A (A +0.2)
        play("g1", "B", "A", 0.4, play_type="kickoff", **kick),
        play("g1", "A", "B", 0.2, play_type="kickoff", **kick),
        # field goals credit the kicker only; punt with a null flag still counts by play type
        play("g1", "A", "B", 1.0, play_type="field_goal", **kick),
        play("g1", "B", "A", -0.2, play_type="field_goal", **kick),
        play("g1", "A", "B", -0.1, play_type="punt", **{**kick, "special_teams_play": None}),
        play("g2", "A", "B", 5.0, play_type="kickoff", **kick),  # target game: ignored
    ]
    vals = strength.compute(games_frame(), make_plays(rows))
    f = lambda team: feat(vals, "g2", team, "strength.st_epa_pg")
    # league means at g2: kickoff 0.3, field_goal 0.4, punt -0.1 (posteam view)
    # A: kickoff -0.4 as the kicker (c = -1) and +0.2 as receiver (c = +1) -> -0.2 - 0.3 * 0
    #    FG +1.0 - 0.4 ; punt as the kicking team: (-0.1) - (-0.1) = 0
    expect_a = (-0.2 - 0.3 * 0.0) + (1.0 - 0.4) + 0.0
    assert f("A") == pytest.approx(expect_a / (1 + 4))
    # B: kickoff +0.4 recv, -0.2 kicker -> 0.2 - 0.3*0; FG -0.2 - 0.4; punt returner: +0.1 - (-0.1)*-1
    expect_b = (0.4 - 0.2) + (-0.2 - 0.4) + (0.1 - 0.1)
    assert f("B") == pytest.approx(expect_b / 5)
    # week 1: nothing earlier, so exactly 0
    assert feat(vals, "g1", "A", "strength.st_epa_pg") == pytest.approx(0.0)
    # special teams never leak into the offense / defense EPA
    assert feat(vals, "g2", "A", "strength.epa_off") == pytest.approx(0.0)


def toy_adjusted_inputs(seasons=(2024, 2025)):
    o = {"A": 0.10, "B": 0.05, "C": -0.05, "D": -0.10}
    d = {"A": -0.04, "B": 0.02, "C": 0.06, "D": -0.04}
    mu, h = 0.02, 0.05
    pairs = [[("A", "B"), ("C", "D")], [("A", "C"), ("B", "D")], [("A", "D"), ("B", "C")]]
    g_rows, p_rows = [], []
    for si, season in enumerate(seasons):
        t0 = datetime(season, 9, 7, 17, 0)
        for wk in range(1, 13):
            for k, (x, y) in enumerate(pairs[(wk - 1) % 3]):
                home, away = (x, y) if ((wk - 1) // 3) % 2 == 0 else (y, x)
                gid = f"{season}_{wk}_{k}"
                kick = t0 + timedelta(days=7 * wk)
                g_rows.append((gid, season, wk, kick, home, away, "Home", 3.0))
                for off, de, is_home in ((home, away, 1.0), (away, home, 0.0)):
                    epa = mu + h * is_home + o[off] + d[de]
                    p_rows.append(play(gid, off, de, epa))
        # week 13: the fit target (no plays yet)
        kick = t0 + timedelta(days=7 * 13)
        g_rows.append((f"{season}_13_0", season, 13, kick, "A", "B", "Home", None))
    games = pl.DataFrame(
        g_rows,
        schema=["game_id", "season", "week", "kickoff_utc", "home_team", "away_team", "location",
                "result"],
        orient="row",
    ).with_columns(
        pl.when(pl.col("result").is_null()).then(None).otherwise(pl.lit(24.0)).alias("home_score"),
        pl.when(pl.col("result").is_null()).then(None).otherwise(pl.lit(21.0)).alias("away_score"),
    )  # fmt: skip
    return games, make_plays(p_rows), o, d


def test_adjusted_epa_ridge_recovers_known_effects():
    games, plays, o, d = toy_adjusted_inputs()
    base = plays.filter(pl.col("play_type").is_in(["pass", "run"]))
    adj = strength._adjusted(games, base, lam=1e-8)
    wk13 = adj.filter((pl.col("season") == 2024) & (pl.col("week") == 13))
    for r in wk13.iter_rows(named=True):
        assert r["strength.epa_off_adj"] == pytest.approx(o[r["ckey"]], abs=1e-4)
        assert r["strength.epa_def_adj"] == pytest.approx(d[r["ckey"]], abs=1e-4)
    # week 1 of the next season is the prior: 0.7 * last season's final (centered) effect
    w1 = adj.filter((pl.col("season") == 2025) & (pl.col("week") == 1))
    for r in w1.iter_rows(named=True):
        assert r["strength.epa_off_adj"] == pytest.approx(0.7 * o[r["ckey"]], abs=1e-4)
        assert r["strength.epa_def_adj"] == pytest.approx(0.7 * d[r["ckey"]], abs=1e-4)
    # week 1 of the first season has no prior at all
    first = adj.filter((pl.col("season") == 2024) & (pl.col("week") == 1))
    assert first["strength.epa_off_adj"].abs().max() == pytest.approx(0.0, abs=1e-9)
    # a huge lambda keeps every week at the prior; the default lambda lands in between
    stiff = strength._adjusted(games, base, lam=1e9).filter(
        (pl.col("season") == 2024) & (pl.col("week") == 13)
    )
    assert stiff["strength.epa_off_adj"].abs().max() < 1e-4
    mid = strength._adjusted(games, base).filter(
        (pl.col("season") == 2024) & (pl.col("week") == 13)
    )
    a = mid.filter(pl.col("ckey") == "A")["strength.epa_off_adj"][0]
    assert 0.0 < a < o["A"]


def test_adjusted_features_flow_through_compute():
    games, plays, o, d = toy_adjusted_inputs(seasons=(2024,))
    vals = strength.compute(games, plays)
    # the week-13 game: A is the home team; the adjusted effect is positive and below the truth
    off = feat(vals, "2024_13_0", "A", "strength.epa_off_adj")
    dfn = feat(vals, "2024_13_0", "B", "strength.epa_def_adj")
    assert 0.0 < off < o["A"]
    assert 0.0 < dfn < d["B"]
    assert feat(vals, "2024_1_0", "A", "strength.epa_off_adj") == pytest.approx(0.0)


def test_leakage_of_every_new_feature():
    """Change everything numeric in the target game and later: no feature of that game moves."""
    games, plays, *_ = toy_adjusted_inputs(seasons=(2024,))
    keep = plays.with_columns(
        pl.lit("QX").alias("passer_player_id"),
        (pl.col("epa") * 1.0).alias("qb_epa"),
        pl.lit(1.5).alias("cpoe"),
        pl.when(pl.col("game_id").str.starts_with("2024_1_")).then(0.5).otherwise(0.95).alias("wp"),
    )
    target = "2024_9_0"
    late = pl.col("game_id").str.split("_").list.get(1).cast(pl.Int64) >= 9
    mutated = keep.with_columns(
        pl.when(late).then(pl.col("epa") + 3.0).otherwise(pl.col("epa")).alias("epa"),
        pl.when(late).then(pl.col("qb_epa") - 2.0).otherwise(pl.col("qb_epa")).alias("qb_epa"),
        pl.when(late).then(-9.0).otherwise(pl.col("cpoe")).alias("cpoe"),
        pl.when(late).then(1.0).otherwise(pl.col("sack")).alias("sack"),
        pl.when(late).then(0.05).otherwise(pl.col("wp")).alias("wp"),
    )
    a = strength.compute(games, keep)
    b = strength.compute(games, mutated)
    early = games.filter(pl.col("week") <= 9)["game_id"].to_list()
    ja = a.filter(pl.col("game_id").is_in(early)).sort("game_id", "team", "feature")
    jb = b.filter(pl.col("game_id").is_in(early)).sort("game_id", "team", "feature")
    assert ja.height == jb.height > 0
    # cumulative sums minus the own game differ in the last bit; anything real would be >> 1e-12
    assert ja["value"].to_list() == pytest.approx(jb["value"].to_list(), abs=1e-12), target


@requires_data
def test_2023_extras_are_finite_and_sensible():
    f = store.read_features(DATA, seasons=(2023, 2023), families=["strength"])
    if f.is_empty() or "strength.qb_epa" not in set(f["feature"]):
        pytest.skip("strength features not rebuilt with M1.11 (run nfl features)")
    assert f["value"].drop_nulls().is_finite().all()
    new = [
        "strength.epa_off_adj", "strength.epa_def_adj", "strength.epa_pass_off",
        "strength.epa_rush_def", "strength.epa_early_off", "strength.epa_nongarbage_off",
        "strength.pythag_win_pct", "strength.luck", "strength.sos", "strength.st_epa_pg",
        "strength.qb_epa", "strength.qb_cpoe",
    ]  # fmt: skip
    for name in new:
        assert f.filter(pl.col("feature") == name)["value"].null_count() == 0, name
    for name in ("strength.sack_rate_off", "strength.sack_rate_def"):
        v = f.filter((pl.col("feature") == name) & (pl.col("week") >= 8))["value"]
        assert v.min() > 0.0 and v.max() < 0.2, name
    games = store.games_frame(DATA).filter(pl.col("season") == 2023)
    kc = (
        f.filter(pl.col("feature") == "strength.qb_epa")
        .join(games.select("game_id", "home_team", "away_team"), on="game_id")
        .filter(
            ((pl.col("side") == "home") & (pl.col("home_team") == "KC"))
            | ((pl.col("side") == "away") & (pl.col("away_team") == "KC"))
        )
    )
    assert kc.height >= 17
    # Mahomes throws almost every game (week 18 was a backup start: one low value is expected)
    assert kc["value"].median() > -0.10  # well above replacement level (about -0.2)
