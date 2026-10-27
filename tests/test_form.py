"""Form builder tests on a hand-built schedule, plus one real-data guard."""

from datetime import datetime, timedelta

import polars as pl

from nfl.features import form, store
from tests.conftest import DATA, requires_data

BUILD = datetime(2030, 1, 1)
T0 = datetime(2018, 9, 9, 17, 0)


def _games(rows, **extra):
    """rows: (game_id, season, week, day_offset, home, away, home_score, away_score); `day_offset`
    may also be a datetime. `extra` maps game_id -> dict of column overrides."""
    recs = []
    for gid, season, week, off, h, a, hs, as_ in rows:
        recs.append(
            {
                "game_id": gid,
                "season": season,
                "week": week,
                "game_type": "REG",
                "location": "Home",
                "div_game": 0,
                "spread_line": None,
                "kickoff_utc": off if isinstance(off, datetime) else T0 + timedelta(days=off),
                "home_team": h,
                "away_team": a,
                "home_score": hs,
                "away_score": as_,
                "result": None if hs is None else hs - as_,
                **extra.get(gid, {}),
            }
        )
    return pl.DataFrame(
        recs,
        schema_overrides={
            "home_score": pl.Int64,
            "away_score": pl.Int64,
            "result": pl.Int64,
            "spread_line": pl.Float64,
            "div_game": pl.Int64,
        },
    )


# AAA results: W, W, L, T, W ; then a season boundary; SD (2018) -> LAC (2019) relocation.
SCHED = _games(
    [
        ("g1", 2018, 1, 0, "AAA", "BBB", 20, 10),  # AAA W +10
        ("g2", 2018, 2, 7, "CCC", "AAA", 13, 24),  # AAA W +11
        ("g3", 2018, 3, 14, "AAA", "BBB", 10, 17),  # AAA L -7
        ("g4", 2018, 4, 21, "BBB", "AAA", 14, 14),  # AAA T 0
        ("g5", 2018, 5, 28, "AAA", "CCC", 30, 3),  # AAA W +27
        ("g6", 2018, 6, 35, "SD", "BBB", 17, 20),  # SD L -3
        ("g7", 2018, 7, 42, "SD", "CCC", 6, 27),  # SD L -21
        ("g8", 2019, 1, 365, "LAC", "AAA", 10, 3),  # LAC (ex-SD) L? no: W +7 ; AAA L -7
        ("g9", 2019, 2, 372, "LAC", "BBB", None, None),  # unplayed
        ("g10", 2019, 3, 379, "AAA", "LAC", 1, 0),
    ]
)


NO_PLAYS = pl.DataFrame(
    schema={"game_id": pl.Utf8, "posteam": pl.Utf8, "defteam": pl.Utf8, "epa": pl.Float64}
)


def feats(games=SCHED, plays=NO_PLAYS):
    values = form.compute(games, plays)
    df = store.from_team_values(values, games, source="schedules", version="2", build_ts=BUILD)
    out = {}
    for r in df.iter_rows(named=True):
        out[(r["game_id"], r["side"], r["feature"])] = r["value"]
    return out


def v(f, gid, side, name):
    return f[(gid, side, f"form.{name}")]


def test_first_ever_game():
    f = feats()
    for side in ("home", "away"):
        assert v(f, "g1", side, "last3_win_pct") is None
        assert v(f, "g1", side, "last3_margin") is None
        assert v(f, "g1", side, "streak") == 0


def test_short_history_and_streaks():
    f = feats()
    # g2: AAA has only g1 (W +10)
    assert v(f, "g2", "away", "last3_win_pct") == 1.0
    assert v(f, "g2", "away", "last3_margin") == 10.0
    assert v(f, "g2", "away", "streak") == 1
    # g3: AAA W, W
    assert v(f, "g3", "home", "streak") == 2
    assert v(f, "g3", "home", "last3_margin") == 10.5
    # g4: AAA W, W, L -> streak -1, mean win 2/3
    assert v(f, "g4", "away", "streak") == -1
    assert abs(v(f, "g4", "away", "last3_win_pct") - 2 / 3) < 1e-12
    # g5: last 3 = W, L, T -> (1+0+.5)/3 ; streak 0 after tie
    assert abs(v(f, "g5", "home", "last3_win_pct") - 0.5) < 1e-12
    assert abs(v(f, "g5", "home", "last3_margin") - (11 - 7 + 0) / 3) < 1e-12
    assert v(f, "g5", "home", "streak") == 0


def test_loss_streak_and_window_drops_old_games():
    f = feats()
    assert v(f, "g7", "home", "streak") == -1  # SD lost g6
    # BBB: g1 L(-10), g3 W(+7), g4 T -> before g6: last3 = L, W, T
    assert abs(v(f, "g6", "away", "last3_win_pct") - 0.5) < 1e-12
    # AAA before g8: games g1,g2,g3,g4,g5 -> last 3 = L, T, W
    assert abs(v(f, "g8", "away", "last3_margin") - (-7 + 0 + 27) / 3) < 1e-12
    assert v(f, "g8", "away", "streak") == 1


def test_season_boundary_and_relocation():
    f = feats()
    # LAC in 2019 week 1 inherits SD's two losses; keyed by the code in the game.
    assert v(f, "g8", "home", "streak") == -2
    assert v(f, "g8", "home", "last3_margin") == -12.0
    assert v(f, "g8", "home", "last3_win_pct") == 0.0
    # g9 is unplayed: still gets features from history (LAC won g8)
    assert v(f, "g9", "home", "streak") == 1
    # g10: LAC as away team; unplayed g9 does not count
    assert v(f, "g10", "away", "streak") == 1
    assert v(f, "g10", "home", "streak") == -1  # AAA lost g8


def test_leakage_target_and_later_results_ignored():
    base = feats()
    order = [f"g{i}" for i in range(1, 11)]
    for changed in ("g4", "g5", "g8"):
        mod = SCHED.with_columns(
            pl.when(pl.col("game_id") == changed)
            .then(pl.col("home_score") + 50)
            .otherwise(pl.col("home_score"))
            .alias("home_score")
        ).with_columns((pl.col("home_score") - pl.col("away_score")).alias("result"))
        new = feats(mod)
        upto = set(order[: order.index(changed) + 1])  # the game itself and everything earlier
        checked = 0
        for key, val in base.items():
            if key[0] in upto:
                assert new[key] == val, (changed, key)
                checked += 1
        assert checked > 0
        assert any(new[k] != base[k] for k in base if k[0] not in upto)  # later games do react


def test_row_shape():
    values = form.compute(SCHED, NO_PLAYS)
    df = store.from_team_values(values, SCHED, source="schedules", version="2", build_ts=BUILD)
    assert df.height == SCHED.height * 2 * len(form.FEATURES)
    assert set(df["feature"]) == set(form.FEATURES)
    assert df["source"].unique().to_list() == ["schedules"]
    assert df["version"].unique().to_list() == ["2"]


# ------------------------------------------------------------------ schedule-context features


def _et(y, m, d, h=13, mi=0):
    """A kickoff given in US Eastern time (EDT, Sept-Oct) as the naive-UTC the store holds."""
    return datetime(y, m, d, h, mi) + timedelta(hours=4)


def test_bye_and_short_week_boundaries():
    # AAA: Sun 9/9, Thu 9/13 (4d: short), Sun 9/23 (10d), Sun 10/7 (14d: bye), Mon 10/15 (8d),
    # Sun 10/21 (6d), Sat 11/3 (13d: bye, boundary), Sun 11/11 (8d)
    rows = [
        ("a1", 2018, 1, _et(2018, 9, 9), "AAA", "BBB", 1, 0),
        ("a2", 2018, 2, _et(2018, 9, 13, 20, 20), "AAA", "BBB", 1, 0),
        ("a3", 2018, 3, _et(2018, 9, 23), "AAA", "BBB", 1, 0),
        ("a4", 2018, 5, _et(2018, 10, 7), "AAA", "BBB", 1, 0),
        ("a5", 2018, 6, _et(2018, 10, 15, 20, 15), "AAA", "BBB", 1, 0),
        ("a6", 2018, 7, _et(2018, 10, 21), "AAA", "BBB", 1, 0),
        ("a7", 2018, 9, _et(2018, 11, 3, 13), "AAA", "BBB", 1, 0),
        ("a8", 2018, 10, _et(2018, 11, 11), "AAA", "BBB", 1, 0),
        ("a9", 2019, 1, _et(2019, 9, 8), "AAA", "BBB", 1, 0),
    ]
    f = feats(_games(rows))
    exp = {
        "a1": (0, 0), "a2": (0, 1), "a3": (0, 0), "a4": (1, 0), "a5": (0, 0),
        "a6": (0, 0), "a7": (1, 0), "a8": (0, 0), "a9": (0, 0),
    }  # fmt: skip
    for gid, (bye, short) in exp.items():
        assert v(f, gid, "home", "off_bye") == bye, gid
        assert v(f, gid, "home", "short_week") == short, gid
        assert v(f, gid, "away", "off_bye") == bye, gid  # BBB plays the same dates


def test_road_streak_with_neutral_sites():
    rows = [
        ("r1", 2018, 1, 0, "XXX", "AAA", 1, 0),  # away
        ("r2", 2018, 2, 7, "YYY", "AAA", 1, 0),  # away
        ("r3", 2018, 3, 14, "AAA", "ZZZ", 1, 0),  # home
        ("r4", 2018, 4, 21, "WWW", "AAA", 1, 0),  # away
        ("r5", 2018, 5, 28, "AAA", "UUU", 1, 0),  # neutral: AAA nominal home
        ("r6", 2018, 6, 35, "VVV", "AAA", 1, 0),  # away
    ]
    f = feats(_games(rows, r5={"location": "Neutral"}))
    assert [v(f, g, s, "road_streak") for g, s in
            [("r1", "away"), ("r2", "away"), ("r3", "home"), ("r4", "away"),
             ("r5", "home"), ("r6", "away")]] == [1, 2, 0, 1, 2, 3]  # fmt: skip
    assert v(f, "r5", "away", "road_streak") == 1  # UUU: neutral counts for both teams
    assert v(f, "r1", "home", "road_streak") == 0


def test_ats_with_pushes_and_away_cover():
    # AAA: home -3 (won by 3: push), away +7 line? spread_line is +home-favored: home -> -7
    # means away AAA favored by 7; AAA wins by 10 -> cover; home +4 lost by 1 -> cover (home
    # underdog +... spread_line=-4 means AAA home underdog by 4) ; then home fav 6 win by 3 -> no.
    rows = [
        ("t1", 2018, 1, 0, "AAA", "BBB", 20, 17),  # line +3, margin +3 -> push (0.5)
        ("t2", 2018, 2, 7, "CCC", "AAA", 10, 20),  # line -7: away fav; margin +10 -> cover (1)
        ("t3", 2018, 3, 14, "AAA", "BBB", 10, 11),  # line -4: home dog, lost by 1 -> cover (1)
        ("t4", 2018, 4, 21, "AAA", "BBB", 13, 10),  # line +6: won by 3 -> miss (0)
        ("t5", 2018, 5, 28, "AAA", "BBB", None, None),
    ]
    g = _games(
        rows,
        t1={"spread_line": 3.0},
        t2={"spread_line": -7.0},
        t3={"spread_line": -4.0},
        t4={"spread_line": 6.0},
    )
    f = feats(g)
    assert v(f, "t1", "home", "ats_l3") is None
    assert v(f, "t2", "away", "ats_l3") == 0.5
    assert abs(v(f, "t3", "home", "ats_l3") - 0.75) < 1e-12
    assert abs(v(f, "t4", "home", "ats_l3") - (0.5 + 1 + 1) / 3) < 1e-12
    assert abs(v(f, "t5", "home", "ats_l3") - (1 + 1 + 0) / 3) < 1e-12  # window drops the push
    # BBB mirrors: t1 BBB lost by 3 vs line (BBB +3) -> push
    assert v(f, "t2", "home", "ats_l3") is None  # CCC's first game


def _tri_games():
    """AAA beats everyone early (rating rises); lookahead: AAA plays BBB then the strong CCC."""
    rows = []
    for w in range(1, 7):  # CCC wins every week against filler => high Elo
        rows.append((f"c{w}", 2018, w, (w - 1) * 7, "CCC", f"F{w}", 40, 0))
        rows.append((f"b{w}", 2018, w, (w - 1) * 7, "F9", "BBB", 20, 14))  # BBB loses each week
    rows.append(("la1", 2018, 7, 42, "AAA", "BBB", None, None))
    rows.append(("la2", 2018, 8, 49, "AAA", "CCC", None, None))
    return _games(rows)


def test_lookahead_uses_next_opponent_elo_but_not_future_results():
    g = _tri_games()
    f = feats(g)
    la = v(f, "la1", "home", "lookahead")
    assert la > 100  # next opp (CCC, 6-0 blowouts) far above this opp (BBB, 0-6)
    assert v(f, "la2", "home", "lookahead") == 0  # last game of the season
    # the *result* of the next game (la2) must not move the lookahead; only the schedule does
    g2 = g.with_columns(
        pl.when(pl.col("game_id") == "la2")
        .then(7)
        .otherwise(pl.col("home_score"))
        .alias("home_score"),
        pl.when(pl.col("game_id") == "la2")
        .then(0)
        .otherwise(pl.col("away_score"))
        .alias("away_score"),
        pl.when(pl.col("game_id") == "la2").then(7).otherwise(pl.col("result")).alias("result"),
    )
    assert feats(g2)[("la1", "home", "form.lookahead")] == la


def test_lookahead_zero_for_postseason_and_before_it():
    rows = [
        ("p1", 2018, 17, 0, "AAA", "BBB", 10, 3),
        ("p2", 2018, 19, 14, "AAA", "CCC", 10, 3),
        ("p3", 2018, 20, 21, "AAA", "DDD", 10, 3),
    ]
    g = _games(rows, p2={"game_type": "DIV"}, p3={"game_type": "CON"})
    f = feats(g)
    for gid in ("p1", "p2", "p3"):
        assert v(f, gid, "home", "lookahead") == 0
    # postseason bye: 14 days after week 17 -> off_bye by the date rule
    assert v(f, "p2", "home", "off_bye") == 1


def test_letdown_triggers():
    # Two triggers: (1) win over a top-8 Elo team, (2) division win in primetime.
    # Build a league of 10 teams so the "top 8" cut is meaningful: T0..T9; T9 is the worst.
    rows = []
    teams = [f"T{i}" for i in range(10)]
    wk = 0
    for _ in range(4):  # round-robin-ish: lower index always wins => T0 strongest
        wk += 1
        for i in range(0, 10, 2):
            rows.append((f"w{wk}_{i}", 2018, wk, (wk - 1) * 7, teams[i], teams[i + 1], 30, 10))
        wk += 1
        for i in range(1, 9, 2):
            rows.append((f"w{wk}_{i}", 2018, wk, (wk - 1) * 7, teams[i], teams[i + 1], 30, 10))
    # Z beats T0 (top-8 opponent) then Y beats T9 (bottom-2); both then play next week
    base = wk
    rows += [
        ("z1", 2018, base + 1, base * 7, "ZZZ", "T0", 24, 20),
        ("z2", 2018, base + 2, (base + 1) * 7, "ZZZ", "T5", 10, 3),
        ("y1", 2018, base + 1, base * 7, "YYY", "T9", 24, 20),
        ("y2", 2018, base + 2, (base + 1) * 7, "YYY", "T5", 10, 3),
        # division win in primetime (SNF 8:20pm ET) over a weak team, then next game
        ("d1", 2018, base + 1, _et(2018, 12, 2, 20, 20) - timedelta(weeks=0), "DDD", "T9", 24, 20),
        ("d2", 2018, base + 2, _et(2018, 12, 9), "DDD", "T5", 10, 3),
        # the same division win in a Sunday 1pm slot: no trigger
        ("e1", 2018, base + 1, _et(2018, 12, 2, 13), "EEE", "T9", 24, 20),
        ("e2", 2018, base + 2, _et(2018, 12, 9), "EEE", "T5", 10, 3),
    ]
    g = _games(rows, d1={"div_game": 1}, e1={"div_game": 1})
    # keep z/y games after the T games chronologically
    f = feats(g)
    assert v(f, "z2", "home", "letdown") == 1  # beat a top-8 team
    assert v(f, "y2", "home", "letdown") == 0  # beat a bottom team, not division primetime
    assert v(f, "d2", "home", "letdown") == 1  # division primetime win
    assert v(f, "e2", "home", "letdown") == 0  # division win at 1pm Sunday
    assert v(f, "z1", "home", "letdown") == 0  # no previous game


def test_eliminated_and_clinched_thresholds():
    def season(wins, week=13):
        rows = []
        for i in range(12):  # 12 games before week 13, wins of them won
            hs, as_ = (7, 0) if i < wins else (0, 7)
            rows.append((f"s{i}", 2018, i + 1, i * 7, "AAA", f"O{i}", hs, as_))
        rows.append(("last", 2018, week, 12 * 7, "AAA", "OXX", 7, 0))
        return _games(rows)

    for wins, elim, clinch in [(4, 1, 0), (5, 0, 0), (10, 0, 1), (9, 0, 0), (0, 1, 0), (12, 0, 1)]:
        f = feats(season(wins))
        assert v(f, "last", "home", "eliminated") == elim, wins  # 4/12=.333<.35; 5/12=.417
        assert v(f, "last", "home", "clinched") == clinch, wins  # 10/12=.833>.8; 9/12=.75
    f = feats(season(0, week=12))
    assert v(f, "last", "home", "eliminated") == 0  # before week 13
    # ties count half
    assert v(f, "s0", "home", "eliminated") == 0


def test_postseason_zeros():
    rows = [(f"s{i}", 2018, i + 1, i * 7, "AAA", f"O{i}", 7, 0) for i in range(17)]
    rows.append(("po", 2018, 19, 17 * 7, "AAA", "OZZ", 7, 0))
    f = feats(_games(rows, po={"game_type": "DIV"}))
    for name in ("eliminated", "clinched", "lookahead"):
        assert v(f, "po", "home", name) == 0, name
    assert v(f, "s16", "home", "clinched") == 1  # the regular season does flag it


def test_epa_trend():
    # AAA net EPA per game: g1..g5 = 0, 0, 0, 0, 1  (offense epa - defense epa allowed)
    rows = [(f"e{i}", 2018, i + 1, i * 7, "AAA", f"O{i}", 7, 0) for i in range(7)]
    plays = []
    nets = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0]
    for i, net in enumerate(nets):
        plays.append((f"e{i}", "AAA", f"O{i}", net))  # AAA offense
        plays.append((f"e{i}", f"O{i}", "AAA", 0.0))  # AAA defense allowed 0
    plays = pl.DataFrame(plays, schema=NO_PLAYS.schema, orient="row")
    f = feats(_games(rows), plays)
    assert v(f, "e0", "home", "epa_trend") == 0.0
    assert v(f, "e1", "home", "epa_trend") == 0.0  # one prior game
    assert v(f, "e2", "home", "epa_trend") == 0.0  # two prior, all zero
    # before e5: priors 0,0,0,0,1 -> last4 = (0,0,0,1)=.25 ; season-to-date = .2
    assert abs(v(f, "e5", "home", "epa_trend") - 0.05) < 1e-12
    # before e6: priors 0,0,0,0,1,1 -> last4 = .5 ; std = 1/3
    assert abs(v(f, "e6", "home", "epa_trend") - (0.5 - 2 / 6)) < 1e-12
    # season reset: a new season's first game is 0
    rows2 = rows + [("n0", 2019, 1, 400, "AAA", "OZ", 7, 0)]
    assert v(feats(_games(rows2), plays), "n0", "home", "epa_trend") == 0.0


def test_new_features_leakage():
    """This game's result and later results never move this game's features."""
    g = _tri_games().with_columns(pl.lit(None, dtype=pl.Float64).alias("spread_line"))
    order = g.sort("kickoff_utc", "game_id")["game_id"].to_list()
    base = feats(g)
    for changed in ("c3", "b4", "b6"):
        mod = g.with_columns(
            pl.when(pl.col("game_id") == changed)
            .then(pl.col("home_score") + 21)
            .otherwise(pl.col("home_score"))
            .alias("home_score")
        ).with_columns((pl.col("home_score") - pl.col("away_score")).alias("result"))
        new = feats(mod)
        # same-kickoff games run in parallel; only strictly-earlier kickoffs are protected
        k = g.filter(pl.col("game_id") == changed)["kickoff_utc"][0]
        safe = set(g.filter(pl.col("kickoff_utc") <= k)["game_id"])
        n = 0
        for key, val in base.items():
            if key[0] in safe:
                assert new[key] == val, (changed, key)
                n += 1
        assert n > 0 and order


def test_relocation_folds_into_one_franchise():
    f = feats()
    # g8 LAC (ex-SD) home after two SD losses; road streak keyed by franchise, home -> 0
    assert v(f, "g8", "home", "road_streak") == 0
    assert v(f, "g8", "home", "off_bye") == 0  # new season
    # g7: SD plays 7 days after g6; earlier SD game counted once
    assert v(f, "g7", "home", "short_week") == 0


@requires_data
def test_real_data_builds():
    games = store.games_frame(DATA).filter(pl.col("season") >= 2010)
    df = form.build(DATA, games, datetime.now())
    j = df.join(games.select("game_id", "kickoff_utc", "game_type"), on="game_id")
    kick = pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    assert j.filter(pl.col("known_as_of") >= kick).is_empty()
    assert set(df["feature"]) == set(form.FEATURES)
    bye = j.filter((pl.col("feature") == "form.off_bye") & (pl.col("game_type") == "REG"))
    share = bye["value"].mean()
    assert 1 / 17 - 0.005 <= share <= 1 / 14 + 0.005, share
