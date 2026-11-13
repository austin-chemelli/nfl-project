"""Parity fixtures for the browser's copy of the league engine (M26.3, ADR 0029).

The TypeScript in web/src/lib/league/ must give the Python's answers. Two files under
web/src/test/fixtures/league_parity/:

- `sim.json` (from committed inputs only, so CI can regenerate and compare it): the 2024 schedule
  from tests/fixtures/league_results_2023_2024.csv, weeks 1-10 played, weeks 11-18 priced from
  fixed ratings. It holds the random draws of 60 runs with each run's seeds and champion (runs whose
  seeding ended in a coin flip are marked: the two languages' generators differ), plus the odds from
  4,000 Python runs for a statistical check.
- `seasons.json` (needs local curated games): every 2002-2025 regular season with the seeds the
  Python gives (it matches the real postseason on all 48 conference-seasons), with and without the
  points steps, plus 10 perturbed copies per season (30% of results flipped, no scores: the
  simulation's case) with their seeds where no coin was needed.

    uv run python scripts/league_parity.py [--sim-only]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl

from nfl.league.divisions import DIVISIONS
from nfl.league.simulate import simulate_season
from nfl.league.standings import GameResult, Results, canon
from nfl.league.tiebreak import seed_conference

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "src" / "test" / "fixtures" / "league_parity"
CSV = ROOT / "tests" / "fixtures" / "league_results_2023_2024.csv"

SIM_SEASON, SIM_PLAYED_THROUGH = 2024, 10
SIM_SIGMA, SIM_HOME, SIM_SEED = 0.4, 0.15, 20261112
REPLAY_RUNS, STAT_RUNS = 60, 4000
PERTURB_PER_SEASON, PERTURB_FLIP = 10, 0.3


def _ratings() -> dict[str, float]:
    """Fixed, spread-out ratings (logit), so some games are lopsided and some are coin flips."""
    teams = sorted(DIVISIONS)
    return {t: round(((i * 7) % 32 - 15.5) / 18, 6) for i, t in enumerate(teams)}


def sim_scenario() -> dict:
    df = pl.read_csv(CSV).filter((pl.col("season") == SIM_SEASON) & (pl.col("game_type") == "REG"))
    played, remaining = [], []
    rat = _ratings()
    for w, h, a, hs, as_ in df.select("week", "home_team", "away_team", "home_score", "away_score").iter_rows():  # fmt: skip
        h, a = canon(h), canon(a)
        if w <= SIM_PLAYED_THROUGH:
            played.append({"home": h, "away": a, "home_score": int(hs), "away_score": int(as_)})
        else:
            p = 1 / (1 + np.exp(-(rat[h] - rat[a] + SIM_HOME)))
            remaining.append(
                {"id": f"{w:02d}_{a}_{h}", "home": h, "away": a, "p": round(float(p), 6)}
            )
    return {"played": played, "games": remaining, "ratings": rat, "home_adv": SIM_HOME, "sigma": SIM_SIGMA}  # fmt: skip


def _run(sc: dict, n_runs: int, on_run=None, seeder=None):
    base = [GameResult.from_scores(g["home"], g["away"], g["home_score"], g["away_score"]) for g in sc["played"]]  # fmt: skip
    gs = sc["games"]
    return simulate_season(
        base, [g["id"] for g in gs], [g["home"] for g in gs], [g["away"] for g in gs],
        [g["p"] for g in gs], sc["ratings"], sigma=sc["sigma"], home_adv=sc["home_adv"],
        n_runs=n_runs, rng=SIM_SEED, on_run=on_run, seeder=seeder,
    )  # fmt: skip


def sim_fixture() -> dict:
    sc = sim_scenario()
    nt, ng = len(DIVISIONS), len(sc["games"])
    # The same draws, in the same order, as simulate_season makes them from the seed.
    gen = np.random.default_rng(SIM_SEED)
    delta = sc["sigma"] * gen.standard_normal((REPLAY_RUNS, nt))
    u_games = gen.random((REPLAY_RUNS, ng))
    u_bracket = gen.random((REPLAY_RUNS, 13))

    coin = {"now": False}
    runs: list[dict] = []

    def seeder(r, conf, rng, n_seeds=7):
        trace: list = []
        out = seed_conference(r, conf, rng, n_seeds=n_seeds, trace=trace)
        coin["now"] = coin["now"] or any(step == "coin" for _, step, _ in trace)
        return out

    def on_run(run, seeds, champ):
        runs.append({"AFC": seeds["AFC"], "NFC": seeds["NFC"], "champ": champ, "coin": coin["now"]})
        coin["now"] = False

    _run(sc, REPLAY_RUNS, on_run=on_run, seeder=seeder)
    stat = _run(sc, STAT_RUNS)
    return {
        "scenario": sc,
        "teams": sorted(DIVISIONS),
        "draws": {
            "delta": [[float(x) for x in row] for row in delta],
            "u_games": [[float(x) for x in row] for row in u_games],
            "u_bracket": [[float(x) for x in row] for row in u_bracket],
        },
        "runs": runs,
        "stat": {
            "n_runs": STAT_RUNS,
            "teams": {
                t: {
                    "playoffs": o.playoffs,
                    "division": o.division,
                    "bye": o.bye,
                    "champ": o.rounds["champ"],
                    "wins_mean": o.wins_mean,
                }
                for t, o in stat.teams.items()
            },
        },
    }


def seasons_fixture(games: pl.DataFrame) -> dict:
    out = []
    rng = np.random.default_rng(7)
    for season in range(2002, 2026):
        reg = games.filter((pl.col("season") == season) & (pl.col("game_type") == "REG"))
        rows = [
            (canon(h), canon(a), int(hs), int(as_))
            for h, a, hs, as_ in reg.select(
                "home_team", "away_team", "home_score", "away_score"
            ).iter_rows()
        ]
        n_seeds = 7 if season >= 2020 else 6
        scored = Results(GameResult.from_scores(*x) for x in rows)
        capped = Results(GameResult(h, a, 1.0 if hs > as_ else 0.0 if hs < as_ else 0.5) for h, a, hs, as_ in rows)  # fmt: skip
        seeds = {c: seed_conference(scored, c, np.random.default_rng(0), n_seeds=n_seeds) for c in ("AFC", "NFC")}  # fmt: skip
        seeds_capped = {c: seed_conference(capped, c, np.random.default_rng(0), n_seeds=n_seeds) for c in ("AFC", "NFC")}  # fmt: skip
        perturbed = []
        for _ in range(PERTURB_PER_SEASON):
            flip = rng.random(len(rows)) < PERTURB_FLIP
            outcomes = []
            for (h, a, hs, as_), f in zip(rows, flip, strict=True):
                o = 1.0 if hs > as_ else 0.0 if hs < as_ else 0.5
                outcomes.append(1.0 - o if f else o)
            r = Results(GameResult(h, a, o) for (h, a, _, _), o in zip(rows, outcomes, strict=True))
            trace: list = []
            s = {c: seed_conference(r, c, np.random.default_rng(0), n_seeds=n_seeds, trace=trace) for c in ("AFC", "NFC")}  # fmt: skip
            coin = any(step == "coin" for _, step, _ in trace)
            steps = sorted({step for _, step, _ in trace})
            code = "".join("H" if o == 1.0 else "A" if o == 0.0 else "T" for o in outcomes)
            perturbed.append({"outcomes": code, "seeds": None if coin else s, "steps": steps})
        out.append({
            "season": season, "n_seeds": n_seeds, "games": [list(x) for x in rows],
            "seeds": seeds, "seeds_capped": seeds_capped, "perturbed": perturbed,
        })  # fmt: skip
    return {"seasons": out}


def dump(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":")) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim-only", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sim.json").write_text(dump(sim_fixture()))
    print("wrote sim.json")
    if not args.sim_only:
        from nfl.config import get_paths

        p = get_paths()
        games = pl.read_parquet(str(p.curated_table("games")) + "/*/*.parquet", hive_partitioning=True)  # fmt: skip
        (OUT / "seasons.json").write_text(dump(seasons_fixture(games)))
        print("wrote seasons.json")


if __name__ == "__main__":
    main()
