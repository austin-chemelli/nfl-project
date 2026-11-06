"""Similar seasons (M14.14): alignment by games played, exclusions, historical codes, determinism."""

import json
from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from nfl.config import get_paths
from nfl.league import build as lb
from nfl.league import similar as sm
from nfl.league.divisions import DIVISIONS

CODES = sorted(DIVISIONS)
SEASON = 2026
KICK = datetime(2026, 9, 8)
BUILD = KICK + timedelta(days=49, hours=12)  # after week 8, before week 9
NOW = BUILD + timedelta(days=1)


def _pairs(w):
    rot = CODES[(w * 3) % 32 :] + CODES[: (w * 3) % 32]
    return [(rot[i], rot[31 - i]) for i in range(16)]


def _synth(past=(2003, 2004, 2005), weeks=16, played=8, seed=1, build=BUILD):
    """32 teams, `weeks` games each a season, no byes. Past seasons are complete with a four-round
    postseason; the current one has `played` weeks done and features built at `build`. 2005 prints
    LAC as SD. Returns (games, feats)."""
    rng = np.random.default_rng(seed)
    rng_flags = np.random.default_rng(seed + 1000)  # own stream: the FEATURES draws don't move
    games, feats = [], []
    for s in (*past, SEASON):
        start = datetime(s, 9, 8)
        code = {"LAC": "SD"} if s == 2005 else {}
        for w in range(1, weeks + 1):
            for h, a in _pairs(w + s):
                h, a = code.get(h, h), code.get(a, a)
                done = s < SEASON or w <= played
                gid = f"{s}_{w:02d}_{a}_{h}"
                k = start + timedelta(days=7 * (w - 1))
                games.append({
                    "game_id": gid, "season": s, "week": w, "game_type": "REG", "kickoff_utc": k,
                    "home_team": h, "away_team": a,
                    "home_score": int(rng.integers(6, 38)) if done else None,
                    "away_score": int(rng.integers(6, 38)) if done else None,
                })  # fmt: skip
                for side in ("home", "away"):
                    for f in sm.FEATURES:
                        stamp = k - timedelta(hours=2) if s < SEASON or k <= build else build
                        feats.append((s, gid, side, f, float(rng.normal()), stamp))
                    for f in (x for x in sm.FLAG_FEATURES if x not in sm.FEATURES):
                        stamp = k - timedelta(hours=2) if s < SEASON or k <= build else build
                        feats.append((s, gid, side, f, float(rng_flags.normal()), stamp))
        if s < SEASON:  # postseason: 12 teams, each round halves what is left
            alive = [code.get(c, c) for c in rng.permutation(CODES)[:12]]
            for rnd, typ in enumerate(("WC", "DIV", "CON", "SB")):
                nxt = []
                pool = alive[4:] if rnd == 0 else alive  # the top four have a bye
                nxt += alive[:4] if rnd == 0 else []  # byes go straight to the next round
                for i in range(0, len(pool) - 1, 2):
                    h, a = pool[i], pool[i + 1]
                    hs, as_ = (30, 20) if rng.random() < 0.5 else (20, 30)
                    games.append({
                        "game_id": f"{s}_{typ}_{a}_{h}", "season": s, "week": 18 + rnd,
                        "game_type": typ, "kickoff_utc": start + timedelta(days=130 + rnd),
                        "home_team": h, "away_team": a, "home_score": hs, "away_score": as_,
                    })  # fmt: skip
                    nxt.append(h if hs > as_ else a)
                alive = nxt
    g = pl.DataFrame(games, schema_overrides={"kickoff_utc": pl.Datetime("us")})
    f = pl.DataFrame(
        feats, schema=sm.FEATURE_SCHEMA | {"known_as_of": pl.Datetime("us")}, orient="row"
    )
    return g, f


def _teams(g, f, season, now):
    return sm.similar_file(g, f, season, now)["teams"]


@pytest.fixture(scope="module")
def world():
    return _synth()


def test_alignment_is_by_games_played_across_a_bye():
    # AAA plays weeks 1-5, has a bye in week 6, then plays weeks 7-9: nine games' worth of weeks
    # but eight games. Vector n = 5 is the 6th game (week 7), record = the first five.
    wk = [1, 2, 3, 4, 5, 7, 8, 9]
    rows, fe = [], []
    for i, w in enumerate(wk):
        gid = f"2010_{w:02d}_O{i}_AAA"
        k = datetime(2010, 9, 5) + timedelta(days=7 * (w - 1))
        rows.append({
            "game_id": gid, "season": 2010, "week": w, "game_type": "REG", "kickoff_utc": k,
            "home_team": "AAA", "away_team": f"O{i}", "home_score": 20 if i % 2 else 10,
            "away_score": 14,
        })  # fmt: skip
        for f in sm.FEATURES:
            fe.append((2010, gid, "home", f, float(w), k - timedelta(hours=2)))
    g = pl.DataFrame(rows, schema_overrides={"kickoff_utc": pl.Datetime("us")})
    f = pl.DataFrame(fe, schema=sm.FEATURE_SCHEMA, orient="row")
    got = {c.n: c for c in sm.candidates(g, f, 2026) if c.team == "AAA"}
    assert sorted(got) == [4, 5, 6, 7]  # MIN_GAMES to the last count with a next game
    assert got[5].x[1] == 7.0  # the week-7 game is the 6th, not the "week 6" one
    assert got[5].rec == (2, 3, 0) and got[5].x[0] == pytest.approx(0.4)
    assert got[4].x[1] == 5.0


def test_past_vectors_come_from_the_next_games_row(world):
    g, f = world
    c = next(c for c in sm.candidates(g, f, SEASON) if c.season == 2004 and c.n == 8)
    gid = g.filter(
        (pl.col("season") == 2004) & (pl.col("game_type") == "REG")
        & ((pl.col("home_team") == c.team) | (pl.col("away_team") == c.team))
    ).sort("kickoff_utc")["game_id"][8]  # fmt: skip
    side = "home" if gid.endswith("_" + c.team) else "away"
    want = f.filter(
        (pl.col("game_id") == gid)
        & (pl.col("side") == side)
        & pl.col("feature").is_in(list(sm.FEATURES))
    ).sort("feature")
    order = sorted(sm.FEATURES)
    assert [x for _, x in sorted(zip(sm.FEATURES, c.x[1:], strict=True))] == want["value"].to_list()
    assert order == want["feature"].to_list()


def test_current_season_and_same_team_season_are_excluded(world):
    g, f = world
    assert {c.season for c in sm.candidates(g, f, SEASON)} == {2003, 2004, 2005}
    out = _teams(g, f, SEASON, NOW)
    for e in out.values():
        assert all(n["season"] < SEASON for n in e["nearest"])


def test_every_team_gets_an_entry_with_the_contract_shape(world):
    g, f = world
    out = _teams(g, f, SEASON, NOW)
    assert sorted(out) == CODES
    for e in out.values():
        lb.SimilarTeam.model_validate(e)
        assert e["games_played"] == 8 and e["k_summary"] == sm.K_SUMMARY
        d = [n["dist"] for n in e["nearest"]]
        assert len(d) == sm.K_SUMMARY and d == sorted(d)
        assert all(len(n["final"].split("-")) == 3 for n in e["nearest"])
    json.dumps(out, allow_nan=False)


def test_historical_codes_print_as_they_were(world):
    g, f = world
    shown = {
        n["team"]
        for e in _teams(g, f, SEASON, NOW).values()
        for n in e["nearest"]
        if n["season"] == 2005
    }
    pool = {c.team for c in sm.candidates(g, f, SEASON) if c.season == 2005}
    assert "SD" in pool and "LAC" not in pool
    assert "LAC" not in shown
    # and the key stays today's code, found through the current game's own printed code
    assert "LAC" in _teams(g, f, SEASON, NOW)


def test_summary_equals_a_brute_force_count(world):
    g, f = world
    out = _teams(g, f, SEASON, NOW)
    pool = [c for c in sm.candidates(g, f, SEASON) if c.n == 8]
    cur, _ = sm._current(g, f, SEASON, NOW)
    post = g.filter(pl.col("game_type") != "REG")
    rank = {"WC": 1, "DIV": 2, "CON": 3, "SB": 4}
    for team in ("KC", "CHI", "LAC"):
        near = sm._nearest(pool, cur[team].x, sm.K_SUMMARY)
        made = div = conf = sb = champ = 0
        for _, c in near:
            mine = post.filter((pl.col("season") == c.season) & ((pl.col("home_team") == c.team) | (pl.col("away_team") == c.team)))  # fmt: skip
            r = max((rank[t] for t in mine["game_type"]), default=0)
            won = [
                (h == c.team) == (hs > a_s)
                for t, h, hs, a_s in mine.select(
                    "game_type", "home_team", "home_score", "away_score"
                ).iter_rows()
                if t == "SB"
            ]
            made += r > 0
            div, conf, sb = div + (r >= 2), conf + (r >= 3), sb + (r >= 4)
            champ += any(won)
        e = out[team]
        assert e["made_playoffs"] == made
        assert e["rounds"] == {"div": div, "conf": conf, "sb": sb, "champ": champ}
        # the printed round is the furthest one, and a title is "champ"
        for n in e["nearest"]:
            assert (n["round"] is not None) == n["playoffs"]


def test_a_team_under_min_games_has_no_entry():
    two = KICK + timedelta(days=7 * 2 + 3)  # built after week 3's games, before week 4's
    g, f = _synth(played=3, build=two)
    assert _teams(g, f, SEASON, two + timedelta(days=1)) == {}
    four = KICK + timedelta(days=7 * 3 + 3)
    g, f = _synth(played=sm.MIN_GAMES, build=four)
    out = _teams(g, f, SEASON, four + timedelta(days=1))
    assert len(out) == 32 and {e["games_played"] for e in out.values()} == {sm.MIN_GAMES}


def test_a_missing_value_leaves_the_team_out_and_drops_candidates(world):
    g, f = world
    # CHI's next game is week 9; take away one feature's row there.
    nxt = g.filter(
        (pl.col("season") == SEASON) & (pl.col("week") == 9)
        & ((pl.col("home_team") == "CHI") | (pl.col("away_team") == "CHI"))
    )["game_id"][0]  # fmt: skip
    side = "home" if nxt.endswith("_CHI") else "away"
    cut = f.filter(~((pl.col("game_id") == nxt) & (pl.col("side") == side) & (pl.col("feature") == sm.FEATURES[3])))  # fmt: skip
    out = _teams(g, cut, SEASON, NOW)
    assert "CHI" not in out and len(out) == 31
    # a past candidate with a null at its n drops out
    n_all = sum(c.n == 8 for c in sm.candidates(g, f, SEASON))
    c0 = next(c for c in sm.candidates(g, f, SEASON) if c.n == 8)
    gid = (
        g.filter(
            (pl.col("season") == c0.season) & (pl.col("game_type") == "REG")
            & ((pl.col("home_team") == c0.team) | (pl.col("away_team") == c0.team))
        ).sort("kickoff_utc")["game_id"][8]
    )  # fmt: skip
    side = "home" if gid.endswith("_" + c0.team) else "away"
    nulled = f.with_columns(
        pl.when(
            (pl.col("game_id") == gid)
            & (pl.col("side") == side)
            & (pl.col("feature") == sm.FEATURES[0])
        )
        .then(None)
        .otherwise(pl.col("value"))
        .alias("value")
    )
    assert sum(c.n == 8 for c in sm.candidates(g, nulled, SEASON)) == n_all - 1


def test_after_the_last_game_the_last_row_is_used_with_n_before_it():
    # 16 weeks, all played, features built after the final game: no next row exists, so a team's
    # vector is its week-16 row and n = 15. That row doesn't contain the final game.
    end = KICK + timedelta(days=7 * 15 + 1)
    g, f = _synth(played=16, build=end)
    out = _teams(g, f, SEASON, end + timedelta(days=2))
    assert len(out) == 32 and {e["games_played"] for e in out.values()} == {15}


def test_rebuild_with_no_new_data_is_identical_and_a_new_build_moves_it(world):
    g, f = world
    a = _teams(g, f, SEASON, NOW)
    # a game kicks off (week 9, no new feature build): nothing moves
    late = BUILD + timedelta(days=3)
    assert json.dumps(_teams(g, f, SEASON, late)) == json.dumps(a)
    assert json.dumps(_teams(g, f, SEASON, NOW)) == json.dumps(a)
    # week 9 is played and features are rebuilt: n and the numbers move
    b9 = KICK + timedelta(days=56 + 1)
    g2, f2 = _synth(played=9, build=b9)
    b = _teams(g2, f2, SEASON, b9 + timedelta(hours=6))
    assert {e["games_played"] for e in b.values()} == {9}
    assert json.dumps(b) != json.dumps(a)


def test_the_file_validates_and_has_nothing_non_finite(world):
    g, f = world
    out = sm.similar_file(g, f, SEASON, NOW)
    lb.SimilarFile.model_validate(out)
    json.dumps(out, allow_nan=False)
    assert [m["id"] for m in out["measures"]] == ["record", *sm.FEATURES]
    assert [m["label"] for m in out["measures"]][:3] == ["Record", "Offense", "Defense"]
    e = out["teams"]["KC"]
    assert len(e["profile"]) == 7 and all(0 <= p <= 100 for p in e["profile"])
    assert e["pool"]["n"] == sum(c.n == 8 for c in sm.candidates(g, f, SEASON))
    assert e["pool"]["seasons"] == [2003, 2005]
    for n in e["nearest"]:
        assert len(n["profile"]) == 7 and len(n["closest"]) == 2 and len(n["furthest"]) == 1


# --- profile and gaps


def _x(*v):
    return np.array(v, dtype=float)


def test_profile_percentiles_are_oriented_and_defense_is_flipped():
    # five teams; column j = measure j. Everyone's value is the pool's maximum or minimum.
    pool = np.array([[0.1 * i, i, i, i, i, i, i] for i in range(5)], dtype=float)
    top = sm.profile(pool, pool[4])
    low = sm.profile(pool, pool[0])
    # offense (index 1): highest value is best; defense (index 2) is lower-is-better: highest is worst
    assert top[1] == 90 and low[1] == 10
    assert top[2] == 10 and low[2] == 90
    assert (
        top[0] == 90 and top[6] == 90
    )  # record up; schedule: 100 is the hardest, so the top is high
    assert sm.profile(pool, pool[2]) == [50] * 7  # the middle, ties count half


def test_closest_and_furthest_are_in_the_charts_percentile_points():
    pool = np.tile(np.arange(100.0)[:, None], (1, 7))
    me = np.full(7, 50.0)
    them = me + np.array([10, 10, 30, 1, 2, 45, 4.0])
    closest, furthest = sm.gaps(pool, me, them)
    assert closest == ["strength.point_diff_pg", "strength.pythag_win_pct"]
    assert furthest == ["strength.qb_epa"]
    # a wide spread in standard deviations doesn't change it: only the chart's distance counts
    pool[:, 5] *= 100
    wide = me.copy()
    wide[5] = 5000.0
    assert sm.gaps(pool, wide, wide + np.array([10, 10, 30, 1, 2, 4500, 4.0]))[1] == [
        "strength.qb_epa"
    ]


# --- current-season edge cases


def test_a_postseason_row_keeps_the_team():
    # Season over: features built after week 16, and the Wild Card games already have feature rows.
    # Passing those games to team_latest made the playoff teams' vector a postseason row at n = 16,
    # where there is no pool, and dropped them until August.
    end = KICK + timedelta(days=7 * 15 + 1)
    g, f = _synth(played=16, build=end)
    wc = end + timedelta(days=5)
    post = pl.DataFrame(
        [{
            "game_id": "2026_WC_KC_CHI", "season": SEASON, "week": 19, "game_type": "WC",
            "kickoff_utc": wc, "home_team": "CHI", "away_team": "KC", "home_score": None,
            "away_score": None,
        }],
        schema_overrides={"kickoff_utc": pl.Datetime("us"), "home_score": pl.Int64, "away_score": pl.Int64},
    )  # fmt: skip
    rows = [
        (SEASON, "2026_WC_KC_CHI", side, ft, 0.5, end + timedelta(hours=1))
        for side in ("home", "away")
        for ft in sm.FEATURES
    ]
    f2 = pl.concat([f, pl.DataFrame(rows, schema=sm.FEATURE_SCHEMA, orient="row")])
    g2 = pl.concat([g, post.select(g.columns)])
    out = _teams(g2, f2, SEASON, end + timedelta(days=2))
    assert len(out) == 32
    assert out["CHI"]["games_played"] == 15 and out["KC"]["games_played"] == 15


def test_a_kickoff_with_no_score_on_file_keeps_the_team():
    # CHI's week-8 game has kicked off but its score isn't on file; features were built after it.
    g, f = _synth(played=8)
    gid = g.filter(
        (pl.col("season") == SEASON) & (pl.col("week") == 8) & (pl.col("home_team") == "CHI")
    )["game_id"]
    if gid.is_empty():
        gid = g.filter(
            (pl.col("season") == SEASON) & (pl.col("week") == 8) & (pl.col("away_team") == "CHI")
        )["game_id"]
    cut = g.with_columns(
        pl.when(pl.col("game_id") == gid[0]).then(None).otherwise(pl.col("home_score")).alias("home_score"),
        pl.when(pl.col("game_id") == gid[0]).then(None).otherwise(pl.col("away_score")).alias("away_score"),
    )  # fmt: skip
    out = _teams(cut, f, SEASON, NOW)
    assert len(out) == 32
    # n counts scored games only: the team is one game behind its vector, others are not
    assert out["CHI"]["games_played"] == 7 and out["KC"]["games_played"] in (7, 8)


# --- flag rules, on hand-made histories


def _cand(i, v, made, conf, rec=(5, 3, 0), n=8, measures=None, season=2010):
    fv = {m: v for m in (measures or [])}
    oc = sm.Outcome(9, 8, 0, bool(made), 3 if conf else 1 if made else 0, False)
    return sm.Candidate(season, "T", n, rec, np.zeros(7), oc, fv)


def _spec(measure, end):
    return next(s for s in sm.FLAG_SPECS if s.measure == measure and s.end == end)


RED = _spec("strength.epa_off_adj", "lo")
OFF = "strength.epa_off_adj"


def _line(pool_fn, n_pool=100, **kw):
    """100 candidates with offense values 0..99 (worst quarter = the first 25)."""
    return [pool_fn(i) for i in range(n_pool)]


def _cur(v, rec=(5, 3, 0), measures=(OFF,)):
    return sm.Current(8, rec, np.zeros(7), {m: v for m in measures})


def _ranks(measures=(OFF,), rank=30):
    """This team's rank among 32: 30 is bottom quarter, 2 top quarter, 16 neither."""
    return {m: {"T": rank, **{f"X{i}": 0 for i in range(31)}} for m in measures}


def test_the_quarter_is_within_each_season_not_across_them():
    # EPA drifts: the same 0.3 is a bottom-quarter offense in a high season, ordinary in a low one
    high = [_cand(i, 0.3 + i / 100, 1, 0, measures=[OFF], season=2020) for i in range(32)]
    low = [_cand(i, -0.1 + i / 100, 1, 0, measures=[OFF], season=2004) for i in range(32)]
    t = sm.FlagTable(high + low)
    inq = t.column(RED)[2]
    assert inq[:32].sum() == 8 and inq[32:].sum() == 8
    assert inq[0] and not inq[31]  # 0.30 in 2020 is its season's worst
    assert inq[32] and not inq[63]


def test_a_rank_and_its_quarter_always_agree():
    top = _spec("strength.epa_off_adj", "hi")
    ranks = list(range(1, 33))
    assert sm.in_quarter(RED, 25, ranks) and not sm.in_quarter(RED, 24, ranks)
    assert sm.in_quarter(top, 8, ranks) and not sm.in_quarter(top, 9, ranks)
    luck = _spec("strength.luck", "lo")  # neutral: rank 1 is the highest, so low luck is rank 32
    assert sm.in_quarter(luck, 32, ranks) and not sm.in_quarter(luck, 1, ranks)


def test_ties_use_the_same_average_rank_as_the_history():
    """Ten teams tied at the bottom of a streak: min-rank 23, average rank 27.5, so all are in the
    quarter, as they would be in the history's column."""
    streak = _spec("form.streak", "lo")
    ranks = list(range(1, 23)) + [23] * 10
    assert sm.in_quarter(streak, 23, ranks)
    pool = [
        _cand(i, -3.0 if i < 10 else float(i), 1, 0, measures=["form.streak"]) for i in range(32)
    ]
    assert sm.FlagTable(pool).column(streak)[2][:10].all()


def test_a_lower_is_better_measure_flags_its_highest_values():
    spec = sm.FlagSpec("red", "strength.epa_def_adj", "lo", "Defense", "made", "lower")
    t = sm.FlagTable([_cand(i, i / 100, 1, 0, measures=[spec.measure]) for i in range(100)])
    inq = t.column(spec)[2]
    assert inq[99] and not inq[0] and inq.sum() == 25


def test_a_card_needs_rates_the_record_did_not_settle():
    """At 0-7 nobody made it and at 11-3 everybody did: neither says anything, for any kind."""
    m = "form.streak"

    def table(flagged_made, others_made):
        pool = [_cand(i, 1.0 if i >= 30 else 0.0, i < flagged_made or 30 <= i < 30 + others_made, 0, measures=[m]) for i in range(100)]  # fmt: skip
        return sm.FlagTable(pool)

    cur, rk = _cur(-5.0, measures=(m,)), _ranks((m,))
    assert sm.flag_cards(table(0, 0), cur, rk, "T") == []
    assert sm.flag_cards(table(0, 20), cur, rk, "T") == []  # none of the flagged teams made it
    assert sm.flag_cards(table(2, 4), cur, rk, "T") == []  # about 6% on both sides
    assert sm.flag_cards(table(30, 70), cur, rk, "T") == []  # all of them
    assert sm.flag_cards(table(12, 28), cur, rk, "T")[0]["kind"] == "fine"


def test_a_fine_card_shows_no_lower_share_than_the_rest():
    m = "form.streak"

    def table(flagged_made):
        pool = [_cand(i, 1.0 if i >= 30 else 0.0, i < flagged_made or 30 <= i < 58, 0, measures=[m]) for i in range(100)]  # fmt: skip
        return sm.FlagTable(pool)

    cur, rk = _cur(-5.0, measures=(m,)), _ranks((m,))
    assert sm.flag_cards(table(9), cur, rk, "T") == []  # 30% against 40%
    assert sm.flag_cards(table(12), cur, rk, "T")[0]["kind"] == "fine"  # the same 40%


def test_no_card_outside_the_games_the_study_covered():
    pool = _line(lambda i: _cand(i, i, i >= 25 and i % 2 == 0, 0, measures=[OFF]))
    t = sm.FlagTable(pool)
    for n, shown in ((5, False), (6, True), (12, True), (13, False)):
        cur = sm.Current(n, (5, 3, 0), np.zeros(7), {OFF: -5.0})
        assert bool(sm.flag_cards(t, cur, _ranks(), "T")) is shown


def test_a_red_or_strength_card_needs_a_real_gap():
    def pool(made_low):
        return sm.FlagTable([_cand(i, i, i < made_low or 25 <= i < 25 + 30, 0, measures=[OFF]) for i in range(100)])  # fmt: skip

    assert sm.flag_cards(pool(10), _cur(-5.0), _ranks(), "T") == []  # 40% against 40%
    assert sm.flag_cards(pool(8), _cur(-5.0), _ranks(), "T")[0]["kind"] == "red"


def test_flags_count_same_record_peers_and_the_card_reads_its_counts():
    # flagged (first 25): 8 of 25 made; others: 60 of 75 made, all at the team's 5-3
    pool = _line(lambda i: _cand(i, i, i % 25 < 8 if i < 25 else i % 5 != 0, 0, measures=[OFF]))
    cards = sm.flag_cards(sm.FlagTable(pool), _cur(-5.0), _ranks(), "T")
    assert len(cards) == 1
    c = cards[0]
    assert c["kind"] == "red" and c["quarter"] == "bottom" and c["outcome"] == "made"
    assert c["flagged"] == [8, 25] and c["others"] == [60, 75]
    assert c["peers"] == "5-3" and c["rank"] == 30 and c["label"] == "Offense"
    # a team outside the quarter has no card
    assert sm.flag_cards(sm.FlagTable(pool), _cur(50.0), _ranks(rank=16), "T") == []


def test_peers_are_exactly_this_record():
    """A range of records would put the weak teams at its low end and the gap would be the record."""

    def rec(i):
        return (5, 3, 0) if i in (0, 1, 2, 50, 51, 52, 53, 54, 55, 56) else (4, 4, 0) if i < 30 else (6, 2, 0)  # fmt: skip

    pool = [_cand(i, i, i % 3 == 0, 0, rec=rec(i), measures=[OFF]) for i in range(100)]
    t = sm.FlagTable(pool)
    assert t.counts(RED, 10) is None  # 3 flagged at 5-3, and 4-4 and 6-2 don't help
    assert t.peers(10) == {
        "made": sum(c.outcome.playoffs for c in pool if c.rec == (5, 3, 0)),
        "n": 10,
    }
    assert sm.flag_cards(t, _cur(-5.0), _ranks(), "T") == []
    full = [_cand(i, i, 1, 0, rec=(5, 3, 0), measures=[OFF]) for i in range(100)]
    assert sm.FlagTable(full).counts(RED, 10) is not None


def test_a_card_is_hidden_when_its_own_counts_disagree_with_its_kind():
    def pool(flag_rate, other_rate):
        def mk(i):
            if i < 25:
                made = i < round(flag_rate * 25)
            else:
                made = (i - 25) < round(other_rate * 75)
            return _cand(i, i, made, 0, measures=[OFF])

        return sm.FlagTable([mk(i) for i in range(100)])

    # red but the flagged teams did better: no card
    assert sm.flag_cards(pool(0.8, 0.4), _cur(-5.0), _ranks(), "T") == []
    assert len(sm.flag_cards(pool(0.2, 0.6), _cur(-5.0), _ranks(), "T")) == 1
    # strength but the top quarter did worse
    top = _spec(OFF, "hi")
    assert top.kind == "strength"

    def strength(flag_rate):
        def mk(i):  # the top quarter is i >= 74
            made = (i - 74) < round(flag_rate * 26) if i >= 74 else (i % 5 != 0)
            return _cand(i, i, made, 0, measures=[OFF])

        return sm.FlagTable([mk(i) for i in range(100)])

    assert sm.flag_cards(strength(0.9), _cur(500.0), _ranks(rank=2), "T")[0]["kind"] == "strength"
    assert sm.flag_cards(strength(0.2), _cur(500.0), _ranks(rank=2), "T") == []

    # fine: the same share shows, a lower one does not, a better one does
    fine_m = "strength.luck"

    def fine(flag_rate, other_rate=0.5):
        def mk(i):
            made = (i < round(flag_rate * 25)) if i < 25 else ((i - 25) < round(other_rate * 75))
            return _cand(i, i, made, 0, measures=[fine_m])

        return sm.FlagTable([mk(i) for i in range(100)])

    cur = _cur(-5.0, measures=(fine_m,))
    rk = _ranks((fine_m,))
    assert sm.flag_cards(fine(0.52), cur, rk, "T")[0]["kind"] == "fine"  # 52% vs 51%
    assert sm.flag_cards(fine(0.28), cur, rk, "T") == []  # 28% vs 50%
    assert sm.flag_cards(fine(0.8), cur, rk, "T")[0]["kind"] == "fine"


def test_outcome_is_conference_game_for_the_rating_and_made_otherwise():
    elo, qb = "strength.elo_pre", "strength.qb_epa"
    ms = [elo, qb]

    # the top quarter is rank/N >= .75 (26 of 100): about 4 in 5 make it, 1 in 5 reach a conference
    # game; the others 40% and 10%
    def mk(i):
        top = i >= 74
        made = (i % 5 != 0) if top else (i % 5 < 2)
        conf = (i % 5 == 0) if top else (i % 10 == 0)
        return _cand(i, i, made, conf, measures=ms)

    t = sm.FlagTable([mk(i) for i in range(100)])
    cards = {
        c["measure"]: c for c in sm.flag_cards(t, _cur(500.0, measures=ms), _ranks(ms, rank=2), "T")
    }
    assert cards[elo]["outcome"] == "conf"
    assert cards[qb]["outcome"] == "made"
    top = [mk(i) for i in range(75, 100)]
    assert cards[elo]["flagged"] == [sum(c.outcome.rank >= 3 for c in top), 25]
    assert cards[qb]["flagged"] == [sum(c.outcome.playoffs for c in top), 25]
    assert cards[elo]["flagged"][0] != cards[qb]["flagged"][0]


def test_at_most_three_cards_a_group_biggest_gap_first():
    ms = [s.measure for s in sm.FLAG_SPECS if s.kind == "strength"]
    assert len(set(ms)) == 3

    def mk(i):
        top = i >= 74
        made = (i % 25 != 0) if top else (i % 5 == 0)  # about 96% vs 20%
        conf = (i % 2 == 0) if top else (i % 20 == 0)  # about 50% vs 5%
        return _cand(i, i, made, conf, measures=ms)

    t = sm.FlagTable([mk(i) for i in range(100)])
    cards = sm.flag_cards(t, _cur(500.0, measures=ms), _ranks(ms, rank=2), "T")
    assert [c["kind"] for c in cards] == ["strength"] * 3
    # made-based first (bigger gap; ties by measure id), then the better of the two conf ones
    assert [c["measure"] for c in cards] == [
        "strength.epa_off_adj", "strength.qb_epa", "strength.elo_pre",
    ]  # fmt: skip


def test_no_group_shows_more_than_three_cards():
    ms = [s.measure for s in sm.FLAG_SPECS if s.kind == "fine"]
    assert len(ms) == 4

    def mk(i):
        return _cand(i, i, i % 2 == 0, 0, measures=ms)

    cards = sm.flag_cards(
        sm.FlagTable([mk(i) for i in range(100)]), _cur(-5.0, measures=ms), _ranks(ms), "T"
    )
    assert len(cards) == sm.MAX_CARDS


def test_groups_come_out_in_the_pages_order():
    ms = [OFF, "strength.luck"]

    # the offense measure is both worst-quarter (red) and the luck measure low (fine) for the team
    def mk(i):
        low = i < 25
        made = (i % 25 < 5) if low else (i % 2 == 0)
        return _cand(i, i, made, 0, measures=ms)

    t = sm.FlagTable([mk(i) for i in range(100)])
    cards = sm.flag_cards(t, _cur(-3.0, measures=ms), _ranks(ms), "T")
    assert [c["kind"] for c in cards] == ["red"] + ["fine"] * (len(cards) - 1)
    assert cards[0]["measure"] == OFF


def test_rank_is_best_first_and_every_measure_is_ranked(world):
    g, f = world
    _, ranks = sm._current(g, f, SEASON, NOW)
    # every team has a row, so each flag measure ranks 32 teams 1..32 (no ties in random data)
    assert sorted(ranks["strength.qb_epa"].values()) == list(range(1, 33))
    latest = {
        t: v
        for t, v in sm.team_latest(
            f.filter(pl.col("season") == SEASON),
            sm._naive(g.filter((pl.col("season") == SEASON) & (pl.col("game_type") == "REG"))),
            NOW,
        )
        .filter(pl.col("feature") == "strength.qb_epa")
        .select("team", "value")
        .iter_rows()
    }
    best = max(latest, key=latest.get)
    assert ranks["strength.qb_epa"][best] == 1
    assert ranks["strength.luck"] is not None


def test_a_history_with_no_pool_makes_no_flags():
    t = sm.FlagTable([])
    assert sm.flag_cards(t, _cur(0.0), _ranks(), "T") == []


# ---------------------------------------------------------------------------------- real data


def _loso_brier(cands, n=8, k=25):
    """Leave one season out: each team-season's neighbours come from the other seasons only (and
    are standardized over them); the forecast is the share of those k that made the playoffs."""
    pool = [c for c in cands if c.n == n]
    y = np.array([c.outcome.playoffs for c in pool], dtype=float)
    p = []
    for c in pool:
        rest = [o for o in pool if o.season != c.season]
        near = sm._nearest(rest, c.x, k)
        p.append(np.mean([o.outcome.playoffs for _, o in near]))
    return float(np.mean((np.array(p) - y) ** 2)), float(np.mean((y.mean() - y) ** 2)), len(pool)


def test_leave_one_season_out_brier_on_real_data():
    from nfl.features import store

    paths = get_paths()
    if not (paths.marts / "features").exists() or not (paths.curated / "games").exists():
        pytest.skip("needs the feature store and curated games (NFL_DATA_ROOT)")
    games = store.games_frame(paths)
    feats = sm.load_features(paths, 2026)
    cands = sm.candidates(games, feats, 2026)
    if not cands:
        pytest.skip("no strength features on disk")
    brier, base, n = _loso_brier(cands)
    print(f"\nLOSO Brier made-playoffs, k=25, 8 games: {brier:.4f} (base {base:.4f}, n={n})")
    assert n > 600 and brier <= 0.140


def test_real_data_every_team_has_an_entry_and_the_file_validates():
    from nfl.config import current_season, now_utc
    from nfl.features import store

    paths = get_paths()
    if not (paths.marts / "features").exists() or not (paths.curated / "games").exists():
        pytest.skip("needs the feature store and curated games (NFL_DATA_ROOT)")
    season = current_season()
    games = store.games_frame(paths)
    now = now_utc().replace(tzinfo=None, microsecond=0)
    played = games.filter(
        (pl.col("season") == season)
        & (pl.col("game_type") == "REG")
        & pl.col("home_score").is_not_null()
    )
    if played.height < 32 * sm.MIN_GAMES // 2:
        pytest.skip("not in season: fewer than MIN_GAMES played")
    out = sm.similar_file(games, sm.load_features(paths, season), season, now)
    lb.SimilarFile.model_validate(out)
    json.dumps(out, allow_nan=False)
    assert len(out["teams"]) == 32
    for e in out["teams"].values():
        assert len(e["nearest"]) == sm.K_SUMMARY and len(e["profile"]) == 7
        assert all(len(f["flagged"]) == 2 and f["rank"] <= 32 for f in e["flags"])
    # a rebuild on the same inputs is identical
    again = sm.similar_file(games, sm.load_features(paths, season), season, now)
    assert json.dumps(again) == json.dumps(out)
