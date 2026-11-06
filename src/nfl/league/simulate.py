"""Season Monte Carlo for the league page (ADR 0019, M14.7).

Each run draws a team-strength shock, plays the remaining games, seeds each conference with the
tiebreak procedure, then plays the 7-team bracket (wild card 2v7 / 3v6 / 4v5, the 1 seed on a bye,
reseeding so the 1 seed meets the lowest seed left, a neutral-site Super Bowl). Outcomes and
shocks are vectorized in numpy; the seeding and the bracket run per run in Python. Simulated ties
are ignored. Leverage comes from the same runs by one matrix product.

Pure computation: returns dataclasses, writes nothing (`build.py` serializes).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from nfl.league.divisions import DIVISIONS

DEFAULT_RUNS = 10_000
MIN_BRANCH_RUNS = 1_000  # a leverage branch needs at least this many runs
MIN_SWING = 0.05  # and the swing at least 5 points of probability
WINS_LO, WINS_HI = 10, 90  # percentiles of the wins range
CONFS = ("AFC", "NFC")
N_SEEDS = 7
ROUNDS = ("div", "conf", "sb", "champ")

Seeder = Callable[..., list[str]]


@dataclass(slots=True)
class TeamOdds:
    team: str
    playoffs: float
    division: float
    bye: float
    seed: list[float]  # P(seed k), k = 1..7
    rounds: dict[str, float]  # div, conf, sb, champ
    wins_mean: float
    wins_lo: float
    wins_hi: float


@dataclass(slots=True)
class Swing:
    team: str
    if_home_win: float
    if_away_win: float


@dataclass(slots=True)
class GameLeverage:
    game_id: str
    p_home: float
    leverage_total: float  # sum of |swing| over reported swings
    n_home_wins: int
    n_away_wins: int
    swings: list[Swing] = field(default_factory=list)


@dataclass(slots=True)
class SimResult:
    n_runs: int
    seed: int | None
    sigma: float
    teams: dict[str, TeamOdds]
    games: list[GameLeverage]  # ranked by leverage_total, descending


def _default_seeder() -> Seeder:
    from nfl.league.tiebreak import seed_conference

    return seed_conference


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def simulate_season(
    played,
    game_ids: Sequence[str],
    home: Sequence[str],
    away: Sequence[str],
    p_home: Sequence[float],
    ratings: dict[str, float],
    *,
    sigma: float,
    home_adv: float = 0.0,
    n_runs: int = DEFAULT_RUNS,
    rng: np.random.Generator | int | None = None,
    seeder: Seeder | None = None,
) -> SimResult:
    """Simulate the rest of the regular season and the playoffs `n_runs` times.

    `played`: GameResults so far. `game_ids/home/away/p_home`: the remaining regular-season games.
    `ratings` (missing teams count 0) and `home_adv` give the playoff game probabilities
    sigmoid(r_home - r_away + home_adv); the Super Bowl is neutral (no home term).
    `sigma` is the std of the per-run team logit shock, applied to every game of a team.
    """
    from nfl.league.standings import GameResult, Results

    seeder = seeder or _default_seeder()
    seed_val = rng if isinstance(rng, int) else None
    gen = rng if isinstance(rng, np.random.Generator) else np.random.default_rng(rng)

    teams = sorted(DIVISIONS)
    ix = {t: i for i, t in enumerate(teams)}
    nt, ng = len(teams), len(game_ids)
    hi = np.array([ix[t] for t in home], dtype=int)
    ai = np.array([ix[t] for t in away], dtype=int)
    p = np.asarray(p_home, dtype=float)
    rating = np.array([ratings.get(t, 0.0) for t in teams])

    # Draw everything random up front, in a fixed order, so a seed fixes the output.
    delta = gen.normal(0.0, sigma, (n_runs, nt)) if sigma > 0 else np.zeros((n_runs, nt))
    u_games = gen.random((n_runs, ng))
    u_bracket = gen.random((n_runs, 13))

    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        logit = np.log(p / (1.0 - p))  # +-inf for p in {0, 1}; the shock leaves them there
        q = _sigmoid(logit[None, :] + delta[:, hi] - delta[:, ai])
    outcomes = u_games < q  # runs x games, True = home win

    played = list(played)
    base = Results(played)
    pairs = [
        (GameResult(home[g], away[g], 1.0), GameResult(home[g], away[g], 0.0)) for g in range(ng)
    ]

    # Wins (ties as half) per run and team: played + simulated, vectorized.
    base_wins = np.zeros(nt)
    for r in played:
        base_wins[ix[r.home]] += r.outcome
        base_wins[ix[r.away]] += 1.0 - r.outcome
    o = outcomes.astype(np.float32)
    h_mat = np.zeros((ng, nt), np.float32)
    a_mat = np.zeros((ng, nt), np.float32)
    h_mat[np.arange(ng), hi] = 1.0
    a_mat[np.arange(ng), ai] = 1.0
    wins = base_wins[None, :] + o @ h_mat + (1.0 - o) @ a_mat

    def win_prob(h: int, a: int, neutral: bool, d: np.ndarray) -> float:
        adv = 0.0 if neutral else home_adv
        return float(_sigmoid(rating[h] - rating[a] + adv + d[h] - d[a]))

    seed_n = np.zeros((nt, N_SEEDS))
    round_n = {r: np.zeros(nt) for r in ROUNDS}
    playoff_y = np.zeros((n_runs, nt), np.float32)

    for run in range(n_runs):
        results = base.extended([pairs[g][0 if outcomes[run, g] else 1] for g in range(ng)])
        d = delta[run]
        u = u_bracket[run]
        k = 0
        champs: dict[str, int] = {}
        for conf in CONFS:
            seeds = [ix[t] for t in seeder(results, conf, gen)]
            if len(seeds) != N_SEEDS:
                raise ValueError(f"seeder returned {len(seeds)} {conf} seeds, expected 7")
            for s, t in enumerate(seeds):
                seed_n[t, s] += 1
                playoff_y[run, t] = 1.0

            # `seeds` position is the seed; a lower position hosts. Draw k advances per game.
            def play(a: int, b: int, seeds=seeds, u=u, d=d) -> int:
                nonlocal k
                p_a = win_prob(seeds[a], seeds[b], False, d)
                k += 1
                return a if u[k - 1] < p_a else b

            wc = [play(1, 6), play(2, 5), play(3, 4)]
            alive = sorted([0, *wc])
            for s in alive:
                round_n["div"][seeds[s]] += 1
            alive = sorted([play(alive[0], alive[3]), play(alive[1], alive[2])])
            for s in alive:
                round_n["conf"][seeds[s]] += 1
            champs[conf] = seeds[play(alive[0], alive[1])]
        a_team, n_team = champs["AFC"], champs["NFC"]
        for t in (a_team, n_team):
            round_n["sb"][t] += 1
        x = u[k] < win_prob(a_team, n_team, True, d)  # AFC is the nominal "home"
        round_n["champ"][a_team if x else n_team] += 1

    r = float(n_runs)
    out: dict[str, TeamOdds] = {}
    lo, hi_w = np.percentile(wins, [WINS_LO, WINS_HI], axis=0)
    for t, i in ix.items():
        out[t] = TeamOdds(
            team=t,
            playoffs=float(seed_n[i].sum() / r),
            division=float(seed_n[i, :4].sum() / r),
            bye=float(seed_n[i, 0] / r),
            seed=[float(x) / r for x in seed_n[i]],
            rounds={n: float(round_n[n][i] / r) for n in ROUNDS},
            wins_mean=float(wins[:, i].mean()),
            wins_lo=float(lo[i]),
            wins_hi=float(hi_w[i]),
        )

    games = _leverage(outcomes, playoff_y, game_ids, p, teams)
    return SimResult(n_runs, seed_val, sigma, out, games)


def _leverage(outcomes, playoff_y, game_ids, p, teams) -> list[GameLeverage]:
    """P(playoffs | game result) for every game and team from the same runs, by one matmul."""
    o = outcomes.astype(np.float32)
    n_home = o.sum(axis=0)
    n_away = outcomes.shape[0] - n_home
    y_total = playoff_y.sum(axis=0)
    hits_home = o.T @ playoff_y  # games x teams: runs with a home win and the team in
    games: list[GameLeverage] = []
    for g, gid in enumerate(game_ids):
        nh, na = int(n_home[g]), int(n_away[g])
        lev = GameLeverage(gid, float(p[g]), 0.0, nh, na)
        if nh >= MIN_BRANCH_RUNS and na >= MIN_BRANCH_RUNS:
            p_h = hits_home[g] / nh
            p_a = (y_total - hits_home[g]) / na
            diff = p_h - p_a
            # tolerance: float32 sums can land a hair under an exact threshold
            for t in np.flatnonzero(np.abs(diff) >= MIN_SWING - 1e-6):
                lev.swings.append(Swing(teams[t], float(p_h[t]), float(p_a[t])))
                lev.leverage_total += abs(float(diff[t]))
            lev.swings.sort(key=lambda s: -abs(s.if_home_win - s.if_away_win))
        games.append(lev)
    games.sort(key=lambda x: -x.leverage_total)
    return games
