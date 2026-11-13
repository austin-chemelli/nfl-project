"""Season simulation (M14.7). Unit tests run against a stub standings module and a by-wins seeder,
so they do not depend on the tiebreak implementation; one test uses the real seeder."""

import importlib
import importlib.util
import random
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nfl.league import simulate as sim
from nfl.league.divisions import DIVISIONS

TEAMS = sorted(DIVISIONS)
AFC = [t for t in TEAMS if DIVISIONS[t][0] == "AFC"]
NFC = [t for t in TEAMS if DIVISIONS[t][0] == "NFC"]


@dataclass(frozen=True, slots=True)
class _GR:
    home: str
    away: str
    outcome: float
    home_score: int | None = None
    away_score: int | None = None


class _Res:
    def __init__(self, games):
        self.games = list(games)

    def extended(self, games):
        return _Res([*self.games, *games])


@pytest.fixture
def stub(monkeypatch):
    mod = types.ModuleType("nfl.league.standings")
    mod.GameResult, mod.Results = _GR, _Res
    monkeypatch.setitem(sys.modules, "nfl.league.standings", mod)
    return mod


def by_wins(results, conf, rng, n_seeds=7):
    w = dict.fromkeys(TEAMS, 0.0)
    for g in results.games:
        w[g.home] += g.outcome
        w[g.away] += 1 - g.outcome
    cand = [t for t in TEAMS if DIVISIONS[t][0] == conf]
    return sorted(cand, key=lambda t: (-w[t], t))[:n_seeds]


def run(played=(), games=(), p=None, **kw):
    ids = [f"g{i}" for i in range(len(games))]
    h = [g[0] for g in games]
    a = [g[1] for g in games]
    kw.setdefault("sigma", 0.0)
    kw.setdefault("n_runs", 200)
    kw.setdefault("rng", 1)
    return sim.simulate_season(
        played, ids, h, a, p if p is not None else [0.5] * len(ids), {}, seeder=by_wins, **kw
    )


def random_slate(seed=0, n=40):
    r = random.Random(seed)
    games = []
    for _ in range(n):
        h, a = r.sample(TEAMS, 2)
        games.append((h, a))
    return games, [r.uniform(0.2, 0.8) for _ in games]


def test_deterministic_for_a_seed(stub):
    games, p = random_slate()
    a = run(games=games, p=p, sigma=0.4, rng=7)
    b = run(games=games, p=p, sigma=0.4, rng=7)
    c = run(games=games, p=p, sigma=0.4, rng=8)
    assert a == b
    assert a != c


def test_degenerate_equals_deterministic_standings(stub):
    # each team plays once; winners are the first team of each pair, p in {0, 1}
    games = [(TEAMS[i], TEAMS[i + 1]) for i in range(0, 32, 2)]
    played = [_GR(TEAMS[0], TEAMS[2], 1.0)]  # one earlier result; TEAMS[0] has 2 wins
    res = run(played=played, games=games, p=[1.0] * 16, sigma=0.0, n_runs=20)
    # also with sigma > 0, certain games stay certain
    res_s = run(played=played, games=games, p=[1.0] * 16, sigma=0.5, n_runs=20)
    for r in (res, res_s):
        for conf in ("AFC", "NFC"):
            expect = by_wins(_Res([*played, *[_GR(h, a, 1.0) for h, a in games]]), conf, None)
            for s, t in enumerate(expect):
                assert r.teams[t].seed[s] == 1.0
        assert sum(t.playoffs for t in r.teams.values()) == 14
        assert (
            r.teams[
                by_wins(_Res([*played, *[_GR(h, a, 1.0) for h, a in games]]), "AFC", None)[0]
            ].bye
            == 1.0
        )


def test_invariants_with_noise(stub):
    games, p = random_slate(3, 120)
    r = run(games=games, p=p, sigma=0.6, n_runs=500)
    assert sum(t.playoffs for t in r.teams.values()) == pytest.approx(14)
    for conf in ("AFC", "NFC"):
        ts = [r.teams[t] for t in TEAMS if DIVISIONS[t][0] == conf]
        for k in range(7):
            assert sum(t.seed[k] for t in ts) == pytest.approx(1.0)
        assert sum(t.division for t in ts) == pytest.approx(4)
        assert sum(t.bye for t in ts) == pytest.approx(1)
        assert sum(t.rounds["div"] for t in ts) == pytest.approx(4)
        assert sum(t.rounds["conf"] for t in ts) == pytest.approx(2)
        assert sum(t.rounds["sb"] for t in ts) == pytest.approx(1)
    assert sum(t.rounds["champ"] for t in r.teams.values()) == pytest.approx(1)
    for t in r.teams.values():
        assert t.wins_lo <= t.wins_mean <= t.wins_hi


def test_bracket_stronger_team_wins_more(stub):
    ratings = {t: 0.0 for t in TEAMS}
    ratings[TEAMS[0]] = 3.0
    games = [(TEAMS[i], TEAMS[i + 1]) for i in range(0, 32, 2)]
    ids = [f"g{i}" for i in range(16)]
    r = sim.simulate_season(
        [],
        ids,
        [g[0] for g in games],
        [g[1] for g in games],
        [1.0] * 16,
        ratings,
        sigma=0.0,
        n_runs=300,
        rng=2,
        seeder=lambda res, conf, rng, **kw: by_wins(res, conf, rng, **kw),
    )
    kc = r.teams[TEAMS[0]]
    assert kc.playoffs == 1.0  # certain winner, first in the name order
    assert kc.rounds["champ"] > 0.2


def _swing_setup():
    x, y = AFC[0], AFC[-1]
    mids = AFC[1:-1]
    # 6 certain winners + whoever wins x-y = 7 one-win teams, all in; the loser of x-y is out
    games = [(x, y)] + [(mids[i], mids[i + 6]) for i in range(6)]
    games += [(NFC[i], NFC[i + 8]) for i in range(8)]
    p = [0.5] + [1.0] * 14
    return x, y, games, p


def test_leverage_matches_analytic_swing(stub):
    x, y, games, p = _swing_setup()
    r = run(games=games, p=p, n_runs=4000, rng=3)
    top = r.games[0]
    assert top.game_id == "g0"
    sw = {s.team: s for s in top.swings}
    assert set(sw) == {x, y}
    assert (sw[x].if_home_win, sw[x].if_away_win) == (1.0, 0.0)
    assert (sw[y].if_home_win, sw[y].if_away_win) == (0.0, 1.0)
    assert top.leverage_total == pytest.approx(2.0)
    assert all(g.swings == [] for g in r.games[1:])
    assert r.teams[x].playoffs == pytest.approx(top.n_home_wins / 4000)
    assert r.teams[y].playoffs == pytest.approx(top.n_away_wins / 4000)


def test_swings_need_enough_runs_on_each_branch(stub):
    _, _, games, p = _swing_setup()
    r = run(games=games, p=p, n_runs=1500, rng=3)  # ~750 per branch
    assert r.games[0].swings == []
    r = run(games=games, p=[0.99] + p[1:], n_runs=4000, rng=3)  # ~40 away wins
    assert all(g.swings == [] for g in r.games)


def test_swings_need_five_points(stub, monkeypatch):
    _, _, games, p = _swing_setup()
    monkeypatch.setattr(sim, "MIN_SWING", 1.5)  # the real swing here is 1.0
    r = run(games=games, p=p, n_runs=4000, rng=3)
    assert all(g.swings == [] for g in r.games)


def test_constants():
    assert sim.MIN_BRANCH_RUNS == 1000 and sim.MIN_SWING == 0.05


def test_real_seeder():
    pytest.importorskip("nfl.league.tiebreak")
    st = importlib.import_module("nfl.league.standings")
    r = random.Random(5)
    played = []
    for _ in range(8):
        order = TEAMS[:]
        r.shuffle(order)
        for i in range(0, 32, 2):
            hs, as_ = r.randint(10, 35), r.randint(10, 35)
            played.append(
                st.GameResult(
                    order[i], order[i + 1], 1.0 if hs > as_ else 0.0 if hs < as_ else 0.5, hs, as_
                )
            )
    games = []
    for _ in range(3):
        order = TEAMS[:]
        r.shuffle(order)
        games += [(order[i], order[i + 1]) for i in range(0, 32, 2)]
    ids = [f"g{i}" for i in range(len(games))]
    res = sim.simulate_season(
        played,
        ids,
        [g[0] for g in games],
        [g[1] for g in games],
        [0.5] * len(games),
        {},
        sigma=0.3,
        n_runs=100,
        rng=1,
    )
    assert sum(t.playoffs for t in res.teams.values()) == pytest.approx(14)
    for conf in ("AFC", "NFC"):
        ts = [res.teams[t] for t in TEAMS if DIVISIONS[t][0] == conf]
        for k in range(7):
            assert sum(t.seed[k] for t in ts) == pytest.approx(1.0)


def test_six_seed_field_has_two_byes_and_three_v_six(stub):
    games, p = random_slate(4, 120)
    r = run(games=games, p=p, sigma=0.5, n_runs=400, n_seeds=6)
    assert sum(t.playoffs for t in r.teams.values()) == pytest.approx(12)
    for conf in ("AFC", "NFC"):
        ts = [r.teams[t] for t in TEAMS if DIVISIONS[t][0] == conf]
        assert sum(t.seed[6] for t in ts) == 0
        assert sum(t.playoffs for t in ts) == pytest.approx(6)
        assert sum(t.rounds["div"] for t in ts) == pytest.approx(4)
        assert sum(t.rounds["conf"] for t in ts) == pytest.approx(2)
        assert sum(t.rounds["sb"] for t in ts) == pytest.approx(1)


def test_six_seed_bracket_pairs_and_byes(stub):
    ratings = {t: 0.0 for t in TEAMS}
    games = [(TEAMS[i], TEAMS[i + 1]) for i in range(0, 32, 2)]
    ids = [f"g{i}" for i in range(16)]
    r = sim.simulate_season(
        [], ids, [g[0] for g in games], [g[1] for g in games], [1.0] * 16, ratings,
        sigma=0.0, n_runs=50, rng=3, seeder=by_wins, n_seeds=6,
    )  # fmt: skip
    for conf in (AFC, NFC):
        assert sum(r.teams[t].playoffs for t in conf) == pytest.approx(6)
        # 3 v 6 and 4 v 5 only: seeds 1 and 2 are never in the wild-card round
        assert sum(r.teams[t].rounds["div"] for t in conf) == pytest.approx(4)
    with pytest.raises(ValueError):
        run(n_seeds=5)


def test_shock_sigma_is_a_calibrated_grid_value():
    assert sim.SHOCK_SIGMA in (0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0)


def _backtest_module():
    path = Path(__file__).parent.parent / "scripts" / "league_backtest.py"
    spec = importlib.util.spec_from_file_location("league_backtest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_backtest_student_rows_are_frozen_at_the_cut():
    import polars as pl

    bt = _backtest_module()
    k0 = datetime(2020, 10, 1, 17)
    cut = datetime(2020, 10, 15)
    games = pl.DataFrame(
        {
            "game_id": ["a", "b", "c"],
            "kickoff_utc": [k0, k0, datetime(2020, 10, 18, 17)],  # c is after the cut
            "home_team": ["KC", "BUF", "KC"],
            "away_team": ["BUF", "KC", "BUF"],
        }
    )
    preds = pl.DataFrame(
        {
            "game_id": ["a", "b", "c"],
            "lock_ts": [k0 - timedelta(hours=1)] * 2 + [datetime(2020, 10, 18, 16)],
            "p_home": [0.6, 0.4, 0.9],
        }
    )
    fit = bt.student_inputs(games, preds, cut)
    # the row for the remaining game c (p = 0.9) is not in the fit: a and b alone give a
    # symmetric pair, so KC and BUF are equal and the home term is the logit of the mean
    assert fit.n_rows == 2
    # a row for a played game that was stamped at or after the cut trips the guard
    bad = preds.with_columns(
        pl.when(pl.col("game_id") == "a").then(cut).otherwise(pl.col("lock_ts")).alias("lock_ts")
    )
    # (filtered out by the cut, so the fit simply loses that row rather than using it)
    assert bt.student_inputs(games, bad, cut).n_rows == 1


def test_web_parity_fixture_is_current():
    """M26.3: the browser engine is checked against sim.json; a change to the Python engine must
    regenerate it (`uv run python scripts/league_parity.py --sim-only`)."""
    import importlib.util
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "league_parity", root / "scripts" / "league_parity.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = json.loads((mod.OUT / "sim.json").read_text())
    assert json.loads(mod.dump(mod.sim_fixture())) == committed, (
        "rerun scripts/league_parity.py --sim-only"
    )
