"""site/league.json: standings, simulated playoff odds and game leverage (ADR 0019, M14.10).

Called at the end of `site.build`, so every refresh, lock, odds run and `nfl-site` run refreshes it.
Two variants run on the same engine: the Student's probabilities and the market's. A build is a
snapshot of its inputs and the seed derives from them, so a rebuild with no new data is identical.
Snapshots append to `marts/league/season=YYYY/snapshots.parquet` only when a caller asks (the Tuesday
refresh and real locks), and existing rows are never rewritten.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict

from nfl.config import Paths, current_season, now_utc
from nfl.features import store
from nfl.league.divisions import DIVISION_TEAMS, DIVISIONS, conference_of, division_of
from nfl.league.inputs import VariantInputs, load_inputs
from nfl.league.simulate import DEFAULT_RUNS, SHOCK_SIGMA, SimResult, simulate_season
from nfl.league.standings import GameResult, Results, canon
from nfl.league.tiebreak import rank_division, seed_conference

SCHEMA_VERSION = "1"
TIEBREAK = "steps 1–6, then a coin flip"
VARIANTS = ("student", "market")
SNAPSHOT_KINDS = ("refresh", "lock")
HISTORY_KIND = "refresh"  # the page shows the Tuesday series


class Standing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    team: str
    conf: str
    div: str
    w: int
    l: int
    t: int
    pct: float
    div_rec: str
    conf_rec: str
    pf: int
    pa: int
    left: int
    div_rank: int
    seed_today: int | None


class Wins(BaseModel):
    mean: float
    lo: float
    hi: float


class Odds(BaseModel):
    playoffs: float
    division: float
    bye: float
    seed: list[float]
    rounds: dict[str, float]
    wins: Wins


class Variant(BaseModel):
    sources: dict[str, int]
    teams: dict[str, Odds]


class SwingRow(BaseModel):
    team: str
    if_home_win: float
    if_away_win: float


class GameRow(BaseModel):
    game_id: str
    week: int
    kickoff: str
    home: str
    away: str
    p_student: float
    p_market: float
    market_source: str
    leverage_total: float
    swings: list[SwingRow]
    n_home_wins: int
    n_away_wins: int


class HistoryPoint(BaseModel):
    week: int
    student: float | None
    market: float | None


class LeagueFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    season: int
    generated_at: str
    as_of: str
    through_week: int
    n_sims: int
    seed: int
    shock_sigma: float
    tiebreak: str
    teams: list[Standing]
    odds: dict[str, Variant]
    games: list[GameRow]
    history: dict[str, list[HistoryPoint]]
    similar: dict[str, dict]


def _stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _r(x: float) -> float:
    return round(float(x), 4)


def _rec(r: tuple[int, int, int]) -> str:
    return f"{r[0]}-{r[1]}" + (f"-{r[2]}" if r[2] else "")


def regular_season(games: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Played and remaining regular-season games. Played means a final score is on file."""
    reg = games.filter(pl.col("game_type") == "REG") if "game_type" in games.columns else games
    reg = reg.with_columns(
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
        if isinstance(reg.schema["kickoff_utc"], pl.Datetime)
        and reg.schema["kickoff_utc"].time_zone
        else pl.col("kickoff_utc")
    )
    done = pl.col("home_score").is_not_null() & pl.col("away_score").is_not_null()
    return reg.filter(done), reg.filter(~done)


def played_results(played: pl.DataFrame) -> list[GameResult]:
    cols = ("home_team", "away_team", "home_score", "away_score")
    return [GameResult.from_scores(h, a, int(hs), int(s)) for h, a, hs, s in played.select(cols).iter_rows()]  # fmt: skip


def seed_of(season: int, played: pl.DataFrame, inputs: dict[str, VariantInputs]) -> int:
    """From the season, the last result and the inputs: a rebuild on the same inputs is identical."""
    last = played["kickoff_utc"].max() if played.height else None
    h = hashlib.sha256(f"{season}|{last}|{played.height}".encode())
    for v in VARIANTS:
        x = inputs[v]
        h.update("|".join(x.game_ids).encode())
        h.update(np.round(np.asarray(x.p_home, dtype=float), 6).tobytes())
    return int(h.hexdigest()[:8], 16)


def standings(results: Results, remaining: pl.DataFrame, seed: int) -> list[dict]:
    """One row per team, today, by the real tiebreakers (points steps included: every game is scored)."""
    rng = np.random.default_rng(seed)
    seeds = {
        t: i + 1
        for conf in ("AFC", "NFC")
        for i, t in enumerate(seed_conference(results, conf, rng))
    }
    div_rank = {
        t: i + 1 for d in DIVISION_TEAMS for i, t in enumerate(rank_division(results, d, rng))
    }
    left: dict[str, int] = {}
    for col in ("home_team", "away_team"):
        for t in remaining[col].to_list():
            left[canon(t)] = left.get(canon(t), 0) + 1
    rows = []
    for t in sorted(DIVISIONS):
        w, lo, ti = results.record(t)
        pf, pa = results.points(t)
        rows.append({
            "team": t, "conf": conference_of(t), "div": division_of(t), "w": w, "l": lo, "t": ti,
            "pct": _r(results.pct(t)), "div_rec": _rec(results.division_record(t)),
            "conf_rec": _rec(results.conference_record(t)), "pf": pf, "pa": pa,
            "left": left.get(t, 0), "div_rank": div_rank[t], "seed_today": seeds.get(t),
        })  # fmt: skip
    return rows


def _odds(sim: SimResult) -> dict[str, dict]:
    return {
        t: {
            "playoffs": _r(o.playoffs), "division": _r(o.division), "bye": _r(o.bye),
            "seed": [_r(s) for s in o.seed], "rounds": {k: _r(v) for k, v in o.rounds.items()},
            "wins": {"mean": round(o.wins_mean, 2), "lo": o.wins_lo, "hi": o.wins_hi},
        }
        for t, o in sim.teams.items()
    }  # fmt: skip


def _games(sim: SimResult, market: VariantInputs, remaining: pl.DataFrame) -> list[dict]:
    """Every remaining game, by leverage, with swings from the Student's runs."""
    p_market = dict(zip(market.game_ids, market.p_home, strict=True))
    source = dict(zip(market.game_ids, market.source, strict=True))
    meta = {r["game_id"]: r for r in remaining.iter_rows(named=True)}
    out = []
    for g in sim.games:
        m = meta[g.game_id]
        out.append({
            "game_id": g.game_id, "week": m["week"], "kickoff": _stamp(m["kickoff_utc"]),
            "home": canon(m["home_team"]), "away": canon(m["away_team"]),
            "p_student": _r(g.p_home), "p_market": _r(p_market[g.game_id]),
            "market_source": source[g.game_id], "leverage_total": _r(g.leverage_total),
            "swings": [
                {"team": s.team, "if_home_win": _r(s.if_home_win), "if_away_win": _r(s.if_away_win)}
                for s in g.swings
            ],
            "n_home_wins": g.n_home_wins, "n_away_wins": g.n_away_wins,
        })  # fmt: skip
    return out


def league_file(
    games: pl.DataFrame,
    inputs: dict[str, VariantInputs],
    season: int,
    as_of: datetime,
    n_runs: int = DEFAULT_RUNS,
    sigma: float = SHOCK_SIGMA,
) -> tuple[dict, dict[str, SimResult]] | None:
    """The league.json object (history empty) and the runs, or None once no regular-season game is
    left: the engine has no playoff results to start from, so the last in-season file stays up."""
    played, remaining = regular_season(games)
    if remaining.is_empty():
        return None
    base = played_results(played)
    seed = seed_of(season, played, inputs)
    sims = {
        v: simulate_season(
            base, x.game_ids, x.home, x.away, x.p_home, x.ratings,
            sigma=sigma, home_adv=x.home_term, n_runs=n_runs, rng=seed + i,
        )
        for i, (v, x) in enumerate((v, inputs[v]) for v in VARIANTS)
    }  # fmt: skip
    obj = {
        "schema_version": SCHEMA_VERSION,
        "season": season,
        "generated_at": _stamp(as_of),
        "as_of": _stamp(as_of),
        "through_week": int(played["week"].max()) if played.height else 0,
        "n_sims": n_runs,
        "seed": seed,
        "shock_sigma": sigma,
        "tiebreak": TIEBREAK,
        "teams": standings(Results(base), remaining, seed),
        "odds": {
            v: {"sources": inputs[v].source_counts, "teams": _odds(sims[v])} for v in VARIANTS
        },
        "games": _games(sims["student"], inputs["market"], remaining),
        "history": {},
        "similar": {},
    }
    return obj, sims


def snapshot_path(paths: Paths, season: int) -> Path:
    return paths.marts / "league" / f"season={season}" / "snapshots.parquet"


def snapshot_rows(
    obj: dict,
    sims: dict[str, SimResult],
    inputs: dict[str, VariantInputs],
    kind: str,
    as_of: datetime,
) -> pl.DataFrame:
    rows = []
    for v in VARIANTS:
        for t, o in obj["odds"][v]["teams"].items():
            rows.append({
                "as_of": as_of, "kind": kind, "week": obj["through_week"] + 1, "variant": v,
                "team": t, "playoffs": o["playoffs"], "division": o["division"], "bye": o["bye"],
                "seed_probs": o["seed"], "round_div": o["rounds"]["div"],
                "round_conf": o["rounds"]["conf"], "round_sb": o["rounds"]["sb"],
                "round_champ": o["rounds"]["champ"], "wins_mean": o["wins"]["mean"],
                "wins_lo": o["wins"]["lo"], "wins_hi": o["wins"]["hi"],
                "model_version": inputs[v].model_version, "n_sims": sims[v].n_runs,
                "seed": obj["seed"],
            })  # fmt: skip
    return pl.DataFrame(rows, schema_overrides={"as_of": pl.Datetime("us")})


def append_snapshot(path: Path, rows: pl.DataFrame) -> bool:
    """Add rows after what's there; old rows stay as they are. False if this build is already in."""
    old = pl.read_parquet(path) if path.exists() else None
    if old is not None:
        key = rows.select("as_of", "kind").unique()
        if old.join(key, on=["as_of", "kind"], how="semi").height:
            return False
    out = rows if old is None else pl.concat([old, rows.select(old.columns)])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    out.write_parquet(tmp)
    os.replace(tmp, path)
    return True


def history(path: Path) -> dict[str, list[dict]]:
    """Each team's P(playoffs) by week from the Tuesday series, the week's last row per variant."""
    if not path.exists():
        return {}
    s = pl.read_parquet(path).filter(pl.col("kind") == HISTORY_KIND)
    if s.is_empty():
        return {}
    last = s.sort("as_of").group_by("week", "team", "variant").agg(pl.col("playoffs").last())
    wide = last.pivot(on="variant", index=["week", "team"], values="playoffs").sort("week")
    out: dict[str, list[dict]] = {}
    for r in wide.iter_rows(named=True):
        out.setdefault(r["team"], []).append(
            {"week": r["week"], "student": r.get("student"), "market": r.get("market")}
        )
    return out


def build(
    paths: Paths,
    season: int | None = None,
    snapshot: str | None = None,
    now: datetime | None = None,
    n_runs: int = DEFAULT_RUNS,
) -> dict | None:
    """Write site/league.json; with `snapshot` ('refresh' or 'lock') append the snapshot rows too."""
    if snapshot is not None and snapshot not in SNAPSHOT_KINDS:
        raise ValueError(f"snapshot must be one of {SNAPSHOT_KINDS}, got {snapshot!r}")
    t0 = time.perf_counter()
    season = season or current_season()
    as_of = (now or now_utc()).replace(tzinfo=None, microsecond=0)
    games = store.games_frame(paths).filter(pl.col("season") == season)
    inputs = load_inputs(paths, season, as_of)
    made = league_file(games, inputs, season, as_of, n_runs=n_runs)
    if made is None:
        return None
    obj, sims = made
    path = snapshot_path(paths, season)
    if snapshot:
        append_snapshot(path, snapshot_rows(obj, sims, inputs, snapshot, as_of))
    obj["history"] = history(path)
    LeagueFile.model_validate(obj)
    text = json.dumps(obj, allow_nan=False, separators=(",", ":"))
    out = paths.site / "league.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    seconds = round(time.perf_counter() - t0, 1)
    print(f"league: {len(text) / 1024:.0f} KB, {obj['n_sims']} runs per variant, {seconds}s")
    return {"bytes": len(text), "seconds": seconds, "games": len(obj["games"]), "seed": obj["seed"]}
