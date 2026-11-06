"""Similar seasons (ADR 0019, M14.14): past teams that looked like this one after the same number of
games, and how they finished. Descriptive, never a forecast.

Alignment is by games played, not by calendar week (byes). A past team's vector is the feature row of
its (n+1)th regular-season game, so its values were known before that game, and its record is its
first n games. The current team's vector is `team_latest`'s row (the same "next game as of the last
feature build" row `teams.json` shows) and n is the number of its regular-season games before that
row's game, never a count taken from the clock. Candidates are the 2002 to 2025 regular seasons
(`FIRST_CANDIDATE` to the season before the current one); team codes print as they were then.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb
import numpy as np
import polars as pl

from nfl.config import Paths
from nfl.league.standings import canon
from nfl.league.teams import team_latest

FIRST_CANDIDATE = 2002
MIN_GAMES = 4  # fewer and the record says little, and the vector is mostly last season
K_SUMMARY = 25
K_SHOWN = 10
RECORD_WEIGHT = 2.0
FEATURES = (
    "strength.epa_off_adj",
    "strength.epa_def_adj",
    "strength.point_diff_pg",
    "strength.pythag_win_pct",
    "strength.qb_epa",
    "strength.sos",
)
ROUND_RANK = {"WC": 1, "DIV": 2, "CON": 3, "SB": 4}
ROUND_NAME = {1: "wc", 2: "div", 3: "conf", 4: "sb"}
FEATURE_SCHEMA = {
    "season": pl.Int64, "game_id": pl.Utf8, "side": pl.Utf8, "feature": pl.Utf8,
    "value": pl.Float64, "known_as_of": pl.Datetime("us"),
}  # fmt: skip


def load_features(paths: Paths, season: int) -> pl.DataFrame:
    """Only what this module reads: its features, the strength family, candidate seasons through
    `season`. Filters go into the read, so the bucket mount serves a few columns of one file a season."""
    root = (paths.marts / "features").as_posix()
    files = f"{root}/season=*/strength.parquet"
    if not any((paths.marts / "features").glob("season=*/strength.parquet")):
        return pl.DataFrame(schema=FEATURE_SCHEMA)
    names = ",".join(f"'{f}'" for f in FEATURES)
    con = duckdb.connect()
    return con.sql(
        "select cast(season as bigint) as season, game_id, side, feature, "
        "cast(value as double) as value, cast(known_as_of as timestamp) as known_as_of "
        f"from read_parquet('{files}', hive_partitioning=true) "
        f"where season between {FIRST_CANDIDATE} and {int(season)} "
        f"and feature in ({names}) and side in ('home', 'away')"
    ).pl()


@dataclass(frozen=True)
class Outcome:
    w: int
    l: int
    t: int
    playoffs: bool
    rank: int  # furthest round reached, 0 if none (WC 1, DIV 2, CON 3, SB 4)
    champ: bool

    @property
    def final(self) -> str:
        return f"{self.w}-{self.l}-{self.t}"

    @property
    def round(self) -> str | None:
        if self.champ:
            return "champ"
        return ROUND_NAME.get(self.rank)


def _naive(games: pl.DataFrame) -> pl.DataFrame:
    k = games.schema["kickoff_utc"]
    if isinstance(k, pl.Datetime) and k.time_zone:
        return games.with_columns(pl.col("kickoff_utc").dt.replace_time_zone(None))
    return games


def _result(pf: int, pa: int) -> int:
    return 1 if pf > pa else -1 if pf < pa else 0


def _team_games(games: pl.DataFrame) -> dict[tuple[int, str], list[tuple]]:
    """(season, team as printed) -> that team's games in order: (kickoff, game_id, regular,
    game_type, pf, pa), scores None when not played."""
    out: dict[tuple[int, str], list[tuple]] = {}
    cols = ("season", "game_id", "game_type", "kickoff_utc", "home_team", "away_team", "home_score", "away_score")  # fmt: skip
    for s, gid, gt, k, h, a, hs, as_ in games.select(cols).iter_rows():
        ok = hs is not None and as_ is not None
        out.setdefault((s, h), []).append((k, gid, gt == "REG", gt, hs if ok else None, as_ if ok else None))  # fmt: skip
        out.setdefault((s, a), []).append((k, gid, gt == "REG", gt, as_ if ok else None, hs if ok else None))  # fmt: skip
    for v in out.values():
        v.sort(key=lambda r: (r[0] is None, r[0], r[1]))
    return out


def _outcome(rows: list[tuple]) -> Outcome:
    w = l = t = 0
    rank, champ = 0, False
    for _k, _gid, regular, gt, pf, pa in rows:
        if pf is None:
            continue
        r = _result(pf, pa)
        if regular:
            w, l, t = w + (r > 0), l + (r < 0), t + (r == 0)
        else:
            rank = max(rank, ROUND_RANK.get(gt, 0))
            champ = champ or (gt == "SB" and r > 0)
    return Outcome(w, l, t, rank > 0, rank, champ)


def _record_to(reg: list[tuple], n: int) -> tuple[int, int, int] | None:
    """W-L-T of the first n regular-season games; None if one of them has no score."""
    w = l = t = 0
    for _k, _gid, _reg, _gt, pf, pa in reg[:n]:
        if pf is None:
            return None
        r = _result(pf, pa)
        w, l, t = w + (r > 0), l + (r < 0), t + (r == 0)
    return w, l, t


def _pct(rec: tuple[int, int, int], n: int) -> float:
    return (rec[0] + 0.5 * rec[2]) / n


def _latest(feats: pl.DataFrame) -> dict[tuple[str, str], dict[str, float]]:
    """(game_id, side) -> feature -> value, the newest finite row of each."""
    x = (
        feats.filter(pl.col("value").is_finite())
        .sort("known_as_of")
        .group_by("game_id", "side", "feature", maintain_order=True)
        .last()
    )
    out: dict[tuple[str, str], dict[str, float]] = {}
    for gid, side, f, v in x.select("game_id", "side", "feature", "value").iter_rows():
        out.setdefault((gid, side), {})[f] = v
    return out


@dataclass
class Candidate:
    season: int
    team: str  # as printed then
    n: int
    rec: tuple[int, int, int]
    x: np.ndarray  # win pct, then FEATURES
    outcome: Outcome


def candidates(games: pl.DataFrame, feats: pl.DataFrame, season: int) -> list[Candidate]:
    """Every past team-season and games-played count n (MIN_GAMES to the last count whose next game
    exists) with all seven values known. Seasons FIRST_CANDIDATE to season - 1."""
    games = _naive(games).filter(
        (pl.col("season") >= FIRST_CANDIDATE) & (pl.col("season") < season)
    )
    vec = _latest(feats.filter(pl.col("season") < season))
    sides: dict[str, tuple[str, str]] = {
        gid: (h, a) for gid, h, a in games.select("game_id", "home_team", "away_team").iter_rows()
    }
    out = []
    for (s, team), rows in _team_games(games).items():
        reg = [r for r in rows if r[2]]
        oc = _outcome(rows)
        for n in range(MIN_GAMES, len(reg)):  # the (n+1)th game must exist
            gid = reg[n][1]
            side = "home" if sides[gid][0] == team else "away"
            v = vec.get((gid, side))
            rec = _record_to(reg, n)
            if rec is None or v is None or any(f not in v for f in FEATURES):
                continue
            x = np.array([_pct(rec, n), *(v[f] for f in FEATURES)], dtype=float)
            out.append(Candidate(s, team, n, rec, x, oc))
    return out


def _nearest(cands: list[Candidate], x: np.ndarray, k: int) -> list[tuple[float, Candidate]]:
    """The k nearest of `cands` (all at one n) to x: standardized over the candidates, record
    weighted RECORD_WEIGHT. Ties break on the newer season, then the team code."""
    A = np.vstack([c.x for c in cands])
    sd = A.std(0)
    sd[sd == 0] = 1.0
    w = np.ones(A.shape[1])
    w[0] = RECORD_WEIGHT
    d = np.sqrt((((A - x) / sd * w) ** 2).sum(1))
    seasons = np.array([c.season for c in cands])
    teams = np.array([c.team for c in cands])
    order = np.lexsort((teams, -seasons, d))[:k]
    return [(float(d[i]), cands[i]) for i in order]


def _row(d: float, c: Candidate) -> dict:
    return {
        "season": c.season, "team": c.team, "dist": round(d, 2),
        "rec_then": f"{c.rec[0]}-{c.rec[1]}" + (f"-{c.rec[2]}" if c.rec[2] else ""),
        "final": c.outcome.final, "playoffs": c.outcome.playoffs, "round": c.outcome.round,
    }  # fmt: skip


def summary(near: list[tuple[float, Candidate]]) -> dict:
    oc = [c.outcome for _, c in near]
    return {
        "k_summary": len(near),
        "made_playoffs": sum(o.playoffs for o in oc),
        "rounds": {
            "div": sum(o.rank >= 2 for o in oc),
            "conf": sum(o.rank >= 3 for o in oc),
            "sb": sum(o.rank >= 4 for o in oc),
            "champ": sum(o.champ for o in oc),
        },
    }


def _current(
    games: pl.DataFrame, feats: pl.DataFrame, season: int, now: datetime
) -> dict[str, tuple[int, tuple[int, int, int], np.ndarray]]:
    """team -> (n, record to date, vector) from `team_latest`. A team with no row for one of the
    features, or rows for different games, is left out."""
    cur = _naive(games.filter(pl.col("season") == season))
    if feats.is_empty() or cur.is_empty():
        return {}
    latest = team_latest(feats.filter(pl.col("season") == season), cur, now)
    if latest.is_empty():
        return {}
    by_team: dict[str, dict[str, tuple[float, str, datetime]]] = {}
    for f, t, v, gid, k in latest.select("feature", "team", "value", "game_id", "kickoff_utc").iter_rows():  # fmt: skip
        by_team.setdefault(t, {})[f] = (v, gid, k)
    tg = _team_games(cur)
    out = {}
    for team, fv in by_team.items():
        if any(f not in fv for f in FEATURES) or len({fv[f][1] for f in FEATURES}) != 1:
            continue
        gid, kick = fv[FEATURES[0]][1], fv[FEATURES[0]][2]
        rows = tg.get((season, team), [])
        reg = [r for r in rows if r[2]]
        if kick is None:
            continue
        # Position of the row's game among the team's regular-season games. After a team's last
        # game there is no next row, so team_latest hands back its last one: n is then the games
        # before it, and the final game is not in that vector.
        n = sum((r[0] is not None and (r[0], r[1]) < (kick, gid)) for r in reg)
        rec = _record_to(reg, n)
        if rec is None or n < MIN_GAMES:
            continue
        x = np.array([_pct(rec, n), *(fv[f][0] for f in FEATURES)], dtype=float)
        out[team] = (n, rec, x)
    return out


def similar_file(
    games: pl.DataFrame, feats: pl.DataFrame, season: int, now: datetime
) -> dict[str, dict]:
    """The `similar` object of league.json. `games` carries every season from FIRST_CANDIDATE
    through `season`; `feats` is `load_features`' output. Teams with nothing to show are absent."""
    if feats.is_empty() or games.is_empty():
        return {}
    cur = _current(games, feats, season, now)
    if not cur:
        return {}
    by_n: dict[int, list[Candidate]] = {}
    for c in candidates(games, feats, season):
        by_n.setdefault(c.n, []).append(c)
    out = {}
    for team, (n, _rec, x) in sorted(cur.items()):
        pool = by_n.get(n, [])
        if len(pool) < K_SUMMARY:
            continue
        near = _nearest(pool, x, K_SUMMARY)
        out[canon(team)] = {
            "games_played": n,
            **summary(near),
            "neighbours": [_row(d, c) for d, c in near[:K_SHOWN]],
        }
    return out
