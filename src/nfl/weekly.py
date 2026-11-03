"""`nfl weekly refresh`: the Tuesday job (and any time you want everything current).

Current-season ingest (idempotent), optional Odds API snapshot, curate (incl. lines), tendencies,
all feature families, score finished games that have no prediction yet, grade (scorecard,
divergence, site JSON), ledger (open/settle/CLV). Does not refit: fits are frozen for the season
(ADR 0005). Historical rebuilds use the individual commands.
"""

from __future__ import annotations

import time

from rich.console import Console

from nfl.config import Paths, current_season


def refresh(paths: Paths, console: Console, odds: bool = True) -> None:
    from nfl import ledger
    from nfl.curate import curate
    from nfl.features.build import build_all
    from nfl.grade import grade
    from nfl.ingest import ingest
    from nfl.tendencies import build as build_tendencies

    season = current_season()
    steps = []

    def step(name, fn):
        t0 = time.perf_counter()
        console.rule(name)
        out = fn()
        steps.append((name, time.perf_counter() - t0))
        return out

    step(
        "ingest",
        lambda: ingest(
            paths,
            seasons={
                d: (season, season) for d in ("pbp", "ftn_charting", "injuries", "depth_charts")
            },
        ),
    )
    if odds:
        from nfl import odds as odds_mod

        m = step("odds snapshot", lambda: odds_mod.snapshot(paths))
        console.print(
            f"odds: {m.n_events} events, credits used {m.requests_used}, remaining {m.requests_remaining}"
        )
    step("curate", lambda: curate(paths))
    step("tendencies", lambda: build_tendencies(paths))
    step("features", lambda: build_all(paths))
    step("score unscored", lambda: _score_unscored(paths, season, console))
    step("grade", lambda: grade(paths, console))

    def _ledger():
        ledger.open_bets(paths)
        ledger.summary(ledger.settle(paths)).write_parquet(paths.marts / "ledger_summary.parquet")

    step("ledger", _ledger)

    from nfl.site import build as build_site

    step("site", lambda: build_site(paths))
    console.print("weekly refresh: " + ", ".join(f"{n} {s:.0f}s" for n, s in steps))


def _score_unscored(paths: Paths, season: int, console: Console) -> None:
    """Finished games of the season with no prediction (played before locks began, or a missed lock)
    would otherwise never reach the tracker: the reference models and the approaches score them as
    backfill at the synthetic lock. Both are append-only; games already scored are skipped."""
    from nfl.approaches.run import fill_unscored
    from nfl.predict import predict

    refs = predict(paths, (season, season))
    rows = fill_unscored(paths, season)
    console.print(f"unscored: {refs} reference rows, {rows} approach rows (backfill)")
