"""What could swing a game, and what the model says if it does (ADR 0023, M20.6).

**The quarterback what-if.** The quarterback features follow the projected starter (`nfl.features.qb`):
for an upcoming game that's the depth chart's QB1. When the starter is in doubt (on the injury report
with a game status), or the team's usual starter is listed but not charted first, we rescore the game
with the other quarterback: his `strength.qb_epa` and `qb_cpoe` computed exactly as the features
compute them (`qb.compute` with him named as the starter), `availability.qb1_out` set to whether the
charted QB1 sits, and `availability.qb_change` to whether he differs from last game's starter. Every
approach is rescored with its locked artifact. This is our model's sensitivity, not the market's, and
it never changes a locked row.

**Other factors** are listed, not rescored: starters on the injury report at the weights the
availability family uses (QB 5; T, DE, OLB, top CB, top WR 2), a coaching or play-calling change that
starts this week (the staff spells table), and a short week.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from nfl.models.elo import TEAM_ALIASES

DOUBT = ("Questionable", "Doubtful", "Out")
SHORT_REST = 6  # days


def _canon(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


def depth_qbs(depth: pl.DataFrame, cutoff: datetime) -> dict[str, list[tuple[str, str]]]:
    """team -> [(gsis_id, name)] of QBs ranked 1 and 2 on the latest timestamped chart before `cutoff`."""
    if depth.is_empty() or "dt" not in depth.columns:
        return {}
    d = depth.filter(
        pl.col("dt").is_not_null() & (pl.col("pos_abb") == "QB") & pl.col("pos_rank").is_in([1, 2])
    )
    d = d.with_columns(
        pl.col("dt").str.to_datetime("%Y-%m-%dT%H:%M:%SZ", strict=False).alias("_dt")
    )
    d = d.filter(pl.col("_dt") < cutoff)
    if d.is_empty():
        return {}
    last = d.group_by("team").agg(pl.col("_dt").max().alias("_last"))
    d = d.join(last, on="team").filter(pl.col("_dt") == pl.col("_last")).sort("team", "pos_rank")
    out: dict[str, list[tuple[str, str]]] = {}
    for r in (
        d.unique(["team", "pos_rank"], keep="first").sort("team", "pos_rank").iter_rows(named=True)
    ):
        out.setdefault(_canon(r["team"]), []).append((r["gsis_id"], r["player_name"]))
    return out


def full_names(depth: pl.DataFrame) -> dict[str, str]:
    """gsis -> the name the depth chart prints (play-by-play abbreviates first names)."""
    if depth.is_empty() or "player_name" not in depth.columns:
        return {}
    d = depth.filter(pl.col("gsis_id").is_not_null() & pl.col("player_name").is_not_null())
    return dict(d.select("gsis_id", "player_name").unique("gsis_id", keep="last").iter_rows())


def recent_starters(
    plays: pl.DataFrame, games: pl.DataFrame, cutoff: datetime, n: int = 4
) -> dict[str, dict]:
    """team -> {'last': gsis, 'usual': gsis, 'names': {gsis: name}} from the first dropback of each of
    the team's games that kicked off before `cutoff`, over its last `n` games."""
    k = games.select(
        "game_id",
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")).alias("_k"),
    )
    first = (
        plays.filter((pl.col("qb_dropback") == 1) & pl.col("passer_player_id").is_not_null())
        .join(k, on="game_id")
        .filter(pl.col("_k") < cutoff)
        .sort("game_id", "play_id")
        .group_by("game_id", "posteam", maintain_order=True)
        .agg(pl.col("passer_player_id").first().alias("qb"), pl.col("passer_player_name").first().alias("name"),
             pl.col("_k").first())
        .sort("_k")
    )  # fmt: skip
    out: dict[str, dict] = {}
    for (team,), g in first.group_by(["posteam"]):
        g = g.sort("_k").tail(n)
        qbs = g["qb"].to_list()
        usual = max(set(qbs), key=lambda q: (qbs.count(q), qbs[::-1].index(q) * -1))
        out[_canon(team)] = {
            "last": qbs[-1],
            "usual": usual,
            "names": dict(zip(g["qb"], g["name"], strict=True)),
        }
    return out


def candidates(chart: list[tuple[str, str]], starters: dict) -> dict[str, str]:
    """gsis -> name for the quarterbacks a team could start: charted 1 and 2, its usual starter and
    last game's starter, first listed first."""
    names = starters.get("names", {})
    out: dict[str, str] = {}
    for gsis, name in chart:
        out.setdefault(gsis, name)
    for key in ("usual", "last"):
        q = starters.get(key)
        if q:
            out.setdefault(q, names.get(q, q))
    return out


def assumed_qb(stored_epa: float | None, values: dict[str, dict]) -> str | None:
    """The candidate whose computed `qb_epa` is the one the stored features hold: who the line assumed."""
    if stored_epa is None:
        return None
    for gsis, v in values.items():
        e = v.get("strength.qb_epa")
        if e is not None and abs(e - stored_epa) < 1e-6:
            return gsis
    return None


def alternative(
    chart: list[tuple[str, str]], starters: dict, report: dict[str, str], assumed: str | None
) -> tuple[str, str] | None:
    """(alternative gsis, why) when the starter is in doubt, else None.

    - the assumed starter is on the injury report with a game status: the next one up;
    - the line assumed someone other than the charted QB1: the charted QB1;
    - the usual starter is questionable or doubtful and not assumed: him."""
    if not chart or assumed is None:
        return None
    qb1 = chart[0][0]
    if report.get(assumed) in DOUBT:
        nxt = chart[1][0] if assumed == qb1 and len(chart) > 1 else qb1 if assumed != qb1 else None
        return (nxt, "status") if nxt else None
    if assumed != qb1:
        return qb1, "chart"
    usual = starters.get("usual")
    if usual and usual != assumed and report.get(usual) in ("Questionable", "Doubtful"):
        return usual, "usual"
    return None


def qb_values(
    tg_all: pl.DataFrame, plays: pl.DataFrame, named: pl.DataFrame
) -> dict[tuple[str, str], dict]:
    """(game_id, team) -> {'strength.qb_epa': v, 'strength.qb_cpoe': v} for each row of `named`
    (game_id, team, qb1), with that quarterback as the starter.

    `tg_all` must be every team-game (game_id, team, ckey, season, kickoff_utc), as the features
    build passes it: careers come from the games in it, so one game alone would read as no career."""
    from nfl.features import qb

    if named.is_empty():
        return {}
    long = qb.compute(tg_all, plays, named)
    want = set(zip(named["game_id"], named["team"], strict=True))
    out: dict[tuple[str, str], dict] = {}
    for r in long.filter(
        pl.struct("game_id", "team").is_in([{"game_id": g, "team": t} for g, t in want])
    ).iter_rows(named=True):
        out.setdefault((r["game_id"], r["team"]), {})[r["feature"]] = r["value"]
    return out


def apply(rows: pl.DataFrame, side: str, values: dict[str, float | None]) -> pl.DataFrame:
    """As-of feature rows of one game with `side`'s values replaced (rows keep their stamps)."""
    out = rows
    for feat, v in values.items():
        hit = (pl.col("side") == side) & (pl.col("feature") == feat)
        if out.filter(hit).is_empty():
            continue
        out = out.with_columns(
            pl.when(hit).then(pl.lit(v, dtype=pl.Float64)).otherwise(pl.col("value")).alias("value")
        )
    return out


def rescore(models, asof_rows: pl.DataFrame, game_id: str, cut: datetime) -> dict[str, float]:
    """model_id -> p_home for one game's (possibly modified) as-of rows."""
    from nfl import lock

    slate = pl.DataFrame({"game_id": [game_id]})
    return {
        s.model_id: float(s.frame["p_home"][0])
        for s in lock.score_approaches(models, asof_rows, slate, cut)
    }
