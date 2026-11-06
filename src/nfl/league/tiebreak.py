"""NFL standings tiebreakers (ADR 0019): division ranks and playoff seeds.

The real procedure through the points steps: head-to-head (a sweep for three or more clubs from
different divisions), division record, common games (minimum four for wild cards), conference
record, strength of victory, strength of schedule, then the points ranks and net points, then a
coin flip. Net touchdowns need play-by-play and fall to the coin.

Rules implemented (NFL.com tie-breaking procedures):
- only one club advances per step; clubs eliminated at a step send the rest back to step 1;
- wild-card ties between three or more clubs first keep only the best club of each division;
- seeds among division winners use the wild-card steps;
- the points steps run only when every game has a score; simulated games have none, so the
  procedure ends at strength of schedule and a coin flip drawn from `rng`. A run with no coin
  consumes no random numbers.

Validated against the actual seeds of all 2002-2025 conference-seasons (tests/test_league_tiebreak).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from nfl.league.divisions import DIVISION_TEAMS, DIVISIONS
from nfl.league.standings import CONFERENCE_SET, DIVISION_SET, Results

Vals = dict[str, float | None]
Measure = Callable[[Results, list[str]], Vals]
Trace = list[tuple[str, str, int]]  # (context, deciding step, clubs tied)


def _h2h(r: Results, ts: list[str]) -> Vals:
    return {t: r.pct_vs(t, set(ts) - {t}) for t in ts}


def _h2h_wc(r: Results, ts: list[str]) -> Vals:
    """Two clubs: head-to-head if they played (else level)."""
    a, b = ts
    if r.games_vs(a, [b]) == 0:
        return {t: 0.0 for t in ts}
    return _h2h(r, ts)


def _h2h_sweep(r: Results, ts: list[str]) -> Vals:
    """Three or more clubs: a sweep of all the others (+1) or being swept by all (-1)."""
    out: Vals = {}
    for t in ts:
        others = set(ts) - {t}
        if all(r.games_vs(t, [o]) > 0 for o in others):
            w, l, tie = r.record_vs(t, others)
            out[t] = 1.0 if l == 0 and tie == 0 else -1.0 if w == 0 and tie == 0 else 0.0
        else:
            out[t] = 0.0
    return out


def _division_rec(r: Results, ts: list[str]) -> Vals:
    return {t: r.pct_vs(t, DIVISION_SET[t] - {t}) for t in ts}


def _conference_rec(r: Results, ts: list[str]) -> Vals:
    return {t: r.pct_vs(t, CONFERENCE_SET[DIVISIONS[t][0]] - {t}) for t in ts}


def _common(r: Results, ts: list[str]) -> Vals:
    c = r.common_opponents(ts)
    return {t: r.pct_vs(t, c) for t in ts}


def _common4(r: Results, ts: list[str]) -> Vals:
    c = r.common_opponents(ts)
    if any(r.games_vs(t, c) < 4 for t in ts):
        return {t: 0.0 for t in ts}
    return {t: r.pct_vs(t, c) for t in ts}


def _sov(r: Results, ts: list[str]) -> Vals:
    return {t: r.sov(t) for t in ts}


def _sos(r: Results, ts: list[str]) -> Vals:
    return {t: r.sos(t) for t in ts}


def _conf_points(r: Results, ts: list[str]) -> Vals:
    _, conf = r.points_ranks()
    return {t: -conf.get(t, 0) for t in ts}


def _league_points(r: Results, ts: list[str]) -> Vals:
    league, _ = r.points_ranks()
    return {t: -league.get(t, 0) for t in ts}


def _net_common(r: Results, ts: list[str]) -> Vals:
    c = r.common_opponents(ts)
    return {t: r.net_points(t, c) for t in ts}


def _net_conf(r: Results, ts: list[str]) -> Vals:
    return {t: r.net_points(t, CONFERENCE_SET[DIVISIONS[t][0]] - {t}) for t in ts}


def _net_all(r: Results, ts: list[str]) -> Vals:
    return {t: r.net_points(t) for t in ts}


# (name, measure, needs scores); higher value wins; None = not applicable to that club
Step = tuple[str, Measure, bool]

DIVISION_STEPS: tuple[Step, ...] = (
    ("h2h", _h2h, False),
    ("division", _division_rec, False),
    ("common", _common, False),
    ("conference", _conference_rec, False),
    ("sov", _sov, False),
    ("sos", _sos, False),
    ("conf_points", _conf_points, True),
    ("league_points", _league_points, True),
    ("net_common", _net_common, True),
    ("net_all", _net_all, True),
)
WILDCARD_STEPS_2: tuple[Step, ...] = (
    ("h2h", _h2h_wc, False),
    ("conference", _conference_rec, False),
    ("common4", _common4, False),
    ("sov", _sov, False),
    ("sos", _sos, False),
    ("conf_points", _conf_points, True),
    ("league_points", _league_points, True),
    ("net_conf", _net_conf, True),
    ("net_all", _net_all, True),
)
WILDCARD_STEPS_N: tuple[Step, ...] = (("h2h_sweep", _h2h_sweep, False),) + WILDCARD_STEPS_2[1:]


def _winners(vals: Vals) -> set[str]:
    """Clubs holding the best value. Not applicable (a None) means the step eliminates nobody."""
    if any(v is None for v in vals.values()):
        return set(vals)
    m = max(v for v in vals.values() if v is not None)
    return {t for t, v in vals.items() if v == m}


def _coin(ts: list[str], rng: np.random.Generator, ctx: str, trace: Trace | None) -> str:
    if trace is not None:
        trace.append((ctx, "coin", len(ts)))
    return sorted(ts)[int(rng.integers(len(ts)))]


def _run(
    r: Results,
    ts: list[str],
    steps: tuple[Step, ...],
    ctx: str,
    redo: Callable[[list[str]], str],
    rng: np.random.Generator,
    trace: Trace | None,
) -> str:
    for name, fn, needs_scores in steps:
        if needs_scores and not r.scored:
            continue
        win = _winners(fn(r, ts))
        if len(win) == 1:
            if trace is not None:
                trace.append((ctx, name, len(ts)))
            return next(iter(win))
        if len(win) < len(ts):  # some eliminated: the rest restart at step 1
            return redo(sorted(win))
    return _coin(ts, rng, ctx, trace)


def break_division_tie(
    r: Results, ts: list[str], rng: np.random.Generator, trace: Trace | None = None
) -> str:
    """The one club that wins a tie among clubs of one division."""
    ts = sorted(ts)
    if len(ts) == 1:
        return ts[0]
    return _run(
        r,
        ts,
        DIVISION_STEPS,
        "division",
        lambda s: break_division_tie(r, s, rng, trace),
        rng,
        trace,
    )


def break_wildcard_tie(
    r: Results,
    ts: list[str],
    divorder: dict[str, list[str]],
    rng: np.random.Generator,
    trace: Trace | None = None,
) -> str:
    """The one club that wins a tie for a wild-card spot or among division winners.

    `divorder` maps a division to its clubs in rank order, used to keep only each division's
    best club in a tie of three or more.
    """
    ts = sorted(ts)
    if len(ts) == 1:
        return ts[0]
    divs = {DIVISIONS[t][1] for t in ts}
    if len(divs) == 1:
        return break_division_tie(r, ts, rng, trace)
    if len(ts) > 2:
        keep = sorted(
            min((t for t in ts if DIVISIONS[t][1] == d), key=divorder[d].index) for d in divs
        )
        if len(keep) < len(ts):
            return break_wildcard_tie(r, keep, divorder, rng, trace)
    steps = WILDCARD_STEPS_2 if len(ts) == 2 else WILDCARD_STEPS_N
    return _run(
        r,
        ts,
        steps,
        "wildcard",
        lambda s: break_wildcard_tie(r, s, divorder, rng, trace),
        rng,
        trace,
    )


def _order(
    r: Results,
    pool: list[str],
    n: int,
    pick: Callable[[list[str]], str],
) -> list[str]:
    """The best `n` clubs of `pool` by win percentage, ties broken one winner at a time."""
    left = list(pool)
    out: list[str] = []
    while left and len(out) < n:
        m = max(r.pct(t) for t in left)
        tied = [t for t in left if r.pct(t) == m]
        w = pick(tied) if len(tied) > 1 else tied[0]
        out.append(w)
        left.remove(w)
    return out


def rank_division(
    r: Results, division: str, rng: np.random.Generator, trace: Trace | None = None
) -> list[str]:
    """The four clubs of `division`, first place to last."""
    return _order(
        r,
        list(DIVISION_TEAMS[division]),
        4,
        lambda tied: break_division_tie(r, tied, rng, trace),
    )


def seed_conference(
    r: Results,
    conf: str,
    rng: np.random.Generator,
    *,
    n_seeds: int = 7,
    trace: Trace | None = None,
) -> list[str]:
    """The `n_seeds` playoff clubs of `conf` in seed order: four division winners, then wild cards.

    n_seeds is 7 from 2020 and 6 from 2002 to 2019.
    """
    divorder = {d: rank_division(r, d, rng, trace) for d in DIVISION_TEAMS if d.startswith(conf)}
    pick = lambda tied: break_wildcard_tie(r, tied, divorder, rng, trace)
    seeds = _order(r, [o[0] for o in divorder.values()], 4, pick)
    rest = [t for o in divorder.values() for t in o[1:]]
    return seeds + _order(r, rest, n_seeds - 4, pick)
