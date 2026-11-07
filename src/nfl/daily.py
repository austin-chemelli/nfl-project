"""`nfl daily`: the Wed, Fri and Sat evening pass (ADR 0023, M20.1).

Between the Tuesday refresh and the locks, keep the week's games current: this season's ingest
(injury reports, depth charts, schedules), one odds snapshot, curate, tendencies, features, then the
site JSON. Nothing is graded and nothing is locked here; the Tuesday refresh still grades and settles.
Preview scores (`nfl.previews`, never graded) run after the features; later steps of M20 join `STEPS` in order.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from rich.console import Console

from nfl.config import Paths, current_season


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[Paths, int, Console], object]
    needs_odds: bool = False


def _ingest(paths: Paths, season: int, console: Console) -> None:
    from nfl.ingest import ingest

    ingest(
        paths,
        seasons={d: (season, season) for d in ("pbp", "ftn_charting", "injuries", "depth_charts")},
    )


def _odds(paths: Paths, season: int, console: Console) -> None:
    from nfl import odds

    m = odds.snapshot(paths)
    console.print(
        f"odds: {m.n_events} events, credits used {m.requests_used}, remaining {m.requests_remaining}"
    )


def _curate(paths: Paths, season: int, console: Console) -> None:
    from nfl.curate import curate

    curate(paths)


def _tendencies(paths: Paths, season: int, console: Console) -> None:
    from nfl.tendencies import build

    build(paths)


def _features(paths: Paths, season: int, console: Console) -> None:
    from nfl.features.build import build_all

    build_all(paths)


def _previews(paths: Paths, season: int, console: Console) -> None:
    from nfl import previews

    console.print(f"previews: {previews.run(paths)} rows")


def _site(paths: Paths, season: int, console: Console) -> None:
    from nfl.site import build

    build(paths, season)


STEPS: list[Step] = [
    Step("ingest", _ingest),
    Step("odds snapshot", _odds, needs_odds=True),
    Step("curate", _curate),
    Step("tendencies", _tendencies),
    Step("features", _features),
    Step("previews", _previews),
    Step("site", _site),
]


def plan(odds: bool = True) -> list[str]:
    """The step names a run would take, in order."""
    return [s.name for s in STEPS if odds or not s.needs_odds]


def run(paths: Paths, console: Console, odds: bool = True, season: int | None = None) -> None:
    season = season or current_season()
    took = []
    for s in STEPS:
        if s.needs_odds and not odds:
            continue
        t0 = time.perf_counter()
        console.rule(s.name)
        s.run(paths, season, console)
        took.append((s.name, time.perf_counter() - t0))
    console.print("daily: " + ", ".join(f"{n} {t:.0f}s" for n, t in took))
