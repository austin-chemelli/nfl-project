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
    want = f.filter((pl.col("game_id") == gid) & (pl.col("side") == side)).sort("feature")
    order = sorted(sm.FEATURES)
    assert [x for _, x in sorted(zip(sm.FEATURES, c.x[1:], strict=True))] == want["value"].to_list()
    assert order == want["feature"].to_list()


def test_current_season_and_same_team_season_are_excluded(world):
    g, f = world
    assert {c.season for c in sm.candidates(g, f, SEASON)} == {2003, 2004, 2005}
    out = sm.similar_file(g, f, SEASON, NOW)
    for e in out.values():
        assert all(n["season"] < SEASON for n in e["neighbours"])


def test_every_team_gets_an_entry_with_the_contract_shape(world):
    g, f = world
    out = sm.similar_file(g, f, SEASON, NOW)
    assert sorted(out) == CODES
    for e in out.values():
        lb.Similar.model_validate(e)
        assert e["games_played"] == 8 and e["k_summary"] == sm.K_SUMMARY
        d = [n["dist"] for n in e["neighbours"]]
        assert len(d) == sm.K_SHOWN and d == sorted(d)
        assert all(len(n["final"].split("-")) == 3 for n in e["neighbours"])
    json.dumps(out, allow_nan=False)


def test_historical_codes_print_as_they_were(world):
    g, f = world
    shown = {
        n["team"]
        for e in sm.similar_file(g, f, SEASON, NOW).values()
        for n in e["neighbours"]
        if n["season"] == 2005
    }
    pool = {c.team for c in sm.candidates(g, f, SEASON) if c.season == 2005}
    assert "SD" in pool and "LAC" not in pool
    assert "LAC" not in shown
    # and the key stays today's code, found through the current game's own printed code
    assert "LAC" in sm.similar_file(g, f, SEASON, NOW)


def test_summary_equals_a_brute_force_count(world):
    g, f = world
    out = sm.similar_file(g, f, SEASON, NOW)
    pool = [c for c in sm.candidates(g, f, SEASON) if c.n == 8]
    cur = sm._current(g, f, SEASON, NOW)
    post = g.filter(pl.col("game_type") != "REG")
    rank = {"WC": 1, "DIV": 2, "CON": 3, "SB": 4}
    for team in ("KC", "CHI", "LAC"):
        near = sm._nearest(pool, cur[team][2], sm.K_SUMMARY)
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
        for n in e["neighbours"]:
            assert (n["round"] is not None) == n["playoffs"]


def test_a_team_under_min_games_has_no_entry():
    two = KICK + timedelta(days=7 * 2 + 3)  # built after week 3's games, before week 4's
    g, f = _synth(played=3, build=two)
    assert sm.similar_file(g, f, SEASON, two + timedelta(days=1)) == {}
    four = KICK + timedelta(days=7 * 3 + 3)
    g, f = _synth(played=sm.MIN_GAMES, build=four)
    out = sm.similar_file(g, f, SEASON, four + timedelta(days=1))
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
    out = sm.similar_file(g, cut, SEASON, NOW)
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
    out = sm.similar_file(g, f, SEASON, end + timedelta(days=2))
    assert len(out) == 32 and {e["games_played"] for e in out.values()} == {15}


def test_rebuild_with_no_new_data_is_identical_and_a_new_build_moves_it(world):
    g, f = world
    a = sm.similar_file(g, f, SEASON, NOW)
    # a game kicks off (week 9, no new feature build): nothing moves
    late = BUILD + timedelta(days=3)
    assert json.dumps(sm.similar_file(g, f, SEASON, late)) == json.dumps(a)
    assert json.dumps(sm.similar_file(g, f, SEASON, NOW)) == json.dumps(a)
    # week 9 is played and features are rebuilt: n and the numbers move
    b9 = KICK + timedelta(days=56 + 1)
    g2, f2 = _synth(played=9, build=b9)
    b = sm.similar_file(g2, f2, SEASON, b9 + timedelta(hours=6))
    assert {e["games_played"] for e in b.values()} == {9}
    assert json.dumps(b) != json.dumps(a)


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
