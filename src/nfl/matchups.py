"""The matchup engine (ADR 0028, M25.1): what a unit does in a situation, and what the opponent's habits
imply for this game, in points per game.

Pure functions over the `team_split_week` SQL model (src/nfl/sql/models/team_split_week.sql). Pass a
DuckDB connection from `nfl.catalog.connect` or the model's polars frame; nothing here reads or writes
files. Hold an `Engine` (or pass a frame) when asking about many units, since each module-level call
builds a fresh one. Records are frozen dataclasses with `to_dict()` (they become site JSON in M25.3).

Point in time: everything for a game in week `w` of season `S` reads season `S` rows with week < `w`
only, for the league rates as well as the team's; the shrinkage constant `k` reads seasons < `S`. The
game itself and later weeks never enter.

Definitions
- A unit is a team and a side: `off` (its own plays) or `def` (the plays it defended, so every EPA on a
  `def` row is EPA allowed). `with` / `without` is the split's flag (the situation or not).
- raw gap = EPA per play with the situation minus without. Positive = the situation is better for the
  offense on the play (for a `def` unit: worse for the defense).
- n (the shrinkage weight's n) is the harmonic combination of the unit's with and without plays,
  n = n_with * n_without / (n_with + n_without). A gap of two means has variance sigma^2 * (1/n_with +
  1/n_without) = sigma^2 / n, which is the form k's method of moments assumes; with-plays alone would
  ignore that a situation seen 20 times in 2000 plays has an almost unmeasurable gap.
- shrunk gap = league gap + n / (n + k) * (raw gap - league gap); n = 0 gives the league gap exactly.
  (`.notes/plans/interaction-features.md` writes the same thing as a residual added to the league level.)
- k = sigma^2 / tau^2 by method of moments over team-seasons < S: the variance of team-season gaps
  around their season's league gap = tau^2 + sigma^2 / n. Per split and side (an offense's gap and a
  defense's gap are different quantities), clamped to [K_MIN, K_MAX]; K_DEFAULT when no earlier
  season has the split (FTN splits in 2022); K_MAX when the observed variance does not exceed the
  sampling variance (nothing measurable beyond noise).

Edge convention
- `edge_pts_pg = (opponent rate - rate faced) * shrunk gap * base plays`; positive favours the
  *offense* of that side, always. The gap is the non-choosing unit's: for a defense-chosen split (blitz,
  box) the habit is the defense's and the gap is the offense's EPA with minus without; for an
  offense-chosen split (play action, motion, screen, rpo, shotgun, no huddle, deep pass) the habit is
  the offense's and the gap is the defense's EPA *allowed* with minus without. `neither` splits (downs,
  field zone, game script, opponent tier) get no edge, only unit numbers (`has_edge` False).
- `rate_faced` is the unit's own season-to-date rate in the situation (the share of its plays in it),
  so the edge measures what this opponent changes. `base_plays` is the gap owner's plays per game in the
  split's universe.
- Rates are raw (no shrinkage): a unit with no plays yet takes the league rate.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import polars as pl

from nfl import splits
from nfl.models.elo import TEAM_ALIASES

SIGMA2 = 2.9  # variance of EPA per play (SD about 1.7), `.notes/plans/interaction-features.md`
K_MIN = 400.0
K_MAX = 5000.0
K_DEFAULT = 2000.0
MIN_N_EFF = 30.0  # a team-season gap with less combined n is left out of the k fit
OVERALL_SPLIT = "shotgun"  # its universe is every play, so with + without = the unit's whole season

STABLE_R = 0.3
SOME_R = 0.1
STABLE, SOME, NOISE = "stable", "some", "noise"

Side = str  # "off" | "def"


def _code(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


# ---- records ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitSplit:
    """One unit (team, side) in one split, as of the week. Gaps are EPA per play."""

    split: str
    team: str
    side: str
    n_with: int
    n_without: int
    epa_with: float | None
    epa_without: float | None
    success_with: float | None
    success_without: float | None
    raw_gap: float | None
    league_gap: float | None
    shrunk_gap: float | None
    k: float
    n: float  # harmonic n of with / without
    weight: float  # n / (n + k): the share of the team's own residual kept
    rate: float | None  # the unit's share of plays in the situation (league rate when it has none)
    plays_pg: float | None  # plays per game in the split's universe

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MatchupRow:
    split: str
    label: str
    chooser: str
    has_edge: bool  # False for `neither` splits and `Split.no_edge` ones: unit numbers only
    favours: str | None  # "offense" / "defense" by the edge's sign; None without an edge
    opp_rate: float | None  # how often the choosing unit puts the game in the situation
    opp_rate_lo: (
        float | None
    )  # the league's spread of that habit (min, quartiles, max across teams)
    opp_rate_q1: float | None
    opp_rate_med: float | None
    opp_rate_q3: float | None
    opp_rate_hi: float | None
    rate_faced: float | None  # the other unit's own rate so far
    n_with: int  # the gap owner's (the non-choosing unit's; for `neither`, the offense's)
    n_without: int
    epa_with: float | None
    epa_without: float | None
    shrunk_gap: float | None
    league_gap: float | None
    base_plays: float | None
    edge_pts_pg: float | None  # > 0 favours the offense of this side
    reliability: str
    offense: UnitSplit
    defense: UnitSplit
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MatchupSide:
    offense: str
    defense: str
    rows: list[MatchupRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MatchupEdges:
    season: int
    week: int
    as_of_week: int  # rows with week < as_of_week were read
    sides: list[MatchupSide]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UnitRank:
    team: str
    side: str
    rank: int | None  # 1 = best (offense: highest EPA per play; defense: lowest allowed)
    of: int
    epa_pp: float | None
    plays: int
    league_epa_pp: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---- loading ---------------------------------------------------------------------------------


def load_split_model(con) -> pl.DataFrame:
    """The `team_split_week` model from a catalog connection (empty when it isn't built)."""
    return con.sql("select * from team_split_week").pl()


def _frame(con_or_df) -> pl.DataFrame:
    return con_or_df if isinstance(con_or_df, pl.DataFrame) else load_split_model(con_or_df)


def _div(a: float, b: float) -> float | None:
    return a / b if b else None


# ---- the engine ------------------------------------------------------------------------------


class Engine:
    """The split model prepared for point-in-time reads. Caches per (season, week) tables and k."""

    def __init__(self, con_or_df):
        df = _frame(con_or_df)
        self._df = df
        self._units_cache: dict[tuple[int, int], dict] = {}
        self._league_cache: dict[tuple[int, int], dict] = {}
        self._k_cache: dict[int, dict] = {}
        self._season_df: dict[int, pl.DataFrame] = {}

    # -- tables -------------------------------------------------------------------------------

    def _season(self, season: int) -> pl.DataFrame:
        if season not in self._season_df:
            self._season_df[season] = self._df.filter(pl.col("season") == season)
        return self._season_df[season]

    def units(self, season: int, week: int) -> dict[tuple[str, str, str], dict]:
        """(side, split, team) -> sums over season `season` weeks < `week`."""
        key = (season, week)
        if key in self._units_cache:
            return self._units_cache[key]
        d = self._season(season).filter(pl.col("week") < week)
        out: dict[tuple[str, str, str], dict] = {}
        if d.height:
            g = d.group_by("side", "split", "team").agg(
                n1=pl.col("plays").filter(pl.col("flag")).sum(),
                e1=pl.col("epa_sum").filter(pl.col("flag")).sum(),
                s1=pl.col("success_sum").filter(pl.col("flag")).sum(),
                n0=pl.col("plays").filter(~pl.col("flag")).sum(),
                e0=pl.col("epa_sum").filter(~pl.col("flag")).sum(),
                s0=pl.col("success_sum").filter(~pl.col("flag")).sum(),
                games=pl.col("game_id").n_unique(),
            )
            for r in g.iter_rows(named=True):
                out[(r["side"], r["split"], r["team"])] = r
        self._units_cache[key] = out
        return out

    def league(self, season: int, week: int) -> dict[tuple[str, str], dict]:
        """(side, split) -> pooled with / without sums, the league gap and rate, and the team rates'
        distribution, as of the week."""
        key = (season, week)
        if key in self._league_cache:
            return self._league_cache[key]
        acc: dict[tuple[str, str], dict] = {}
        for (side, split, _team), r in self.units(season, week).items():
            a = acc.setdefault(
                (side, split), {k: 0.0 for k in ("n1", "e1", "n0", "e0")} | {"rates": []}
            )
            for k in ("n1", "e1", "n0", "e0"):
                a[k] += r[k] or 0.0
            rate = _div(r["n1"] or 0, (r["n1"] or 0) + (r["n0"] or 0))
            if rate is not None:
                a["rates"].append(rate)
        for a in acc.values():
            m1, m0 = _div(a["e1"], a["n1"]), _div(a["e0"], a["n0"])
            a["gap"] = None if m1 is None or m0 is None else m1 - m0
            a["rate"] = _div(a["n1"], a["n1"] + a["n0"])
            a["games"] = None
        self._league_cache[key] = acc
        return acc

    def k(self, season: int, side: str, split: str) -> float:
        """The shrinkage constant for (side, split) in `season`, from seasons < `season` only."""
        if season not in self._k_cache:
            self._k_cache[season] = self._fit_k(season)
        return self._k_cache[season].get((side, split), K_DEFAULT)

    def _fit_k(self, season: int) -> dict[tuple[str, str], float]:
        prior = self._df.filter(pl.col("season") < season)
        if prior.is_empty():
            return {}
        t = prior.group_by("season", "side", "split", "team").agg(
            n1=pl.col("plays").filter(pl.col("flag")).sum(),
            e1=pl.col("epa_sum").filter(pl.col("flag")).sum(),
            n0=pl.col("plays").filter(~pl.col("flag")).sum(),
            e0=pl.col("epa_sum").filter(~pl.col("flag")).sum(),
        )
        lg = t.group_by("season", "side", "split").agg(
            L1=pl.col("e1").sum() / pl.col("n1").sum(), L0=pl.col("e0").sum() / pl.col("n0").sum()
        )
        t = t.join(lg, on=["season", "side", "split"]).filter(
            (pl.col("n1") > 0) & (pl.col("n0") > 0)
        )
        t = t.with_columns(
            n=pl.col("n1") * pl.col("n0") / (pl.col("n1") + pl.col("n0")),
            dev=(pl.col("e1") / pl.col("n1") - pl.col("e0") / pl.col("n0"))
            - (pl.col("L1") - pl.col("L0")),
        ).filter(pl.col("n") >= MIN_N_EFF)
        out: dict[tuple[str, str], float] = {}
        for (side, split), g in t.group_by("side", "split"):
            if g.height < 8:
                continue
            tau2 = float(g["dev"].var()) - float((SIGMA2 / g["n"]).mean())
            out[(side, split)] = K_MAX if tau2 <= 0 else float(np.clip(SIGMA2 / tau2, K_MIN, K_MAX))
        return out

    # -- unit numbers -------------------------------------------------------------------------

    def unit_split(self, season: int, week: int, team: str, side: str, split: str) -> UnitSplit:
        team = _code(team)
        r = self.units(season, week).get((side, split, team))
        lg = self.league(season, week).get((side, split))
        n1, n0 = int((r or {}).get("n1") or 0), int((r or {}).get("n0") or 0)
        e1, e0 = (r or {}).get("e1") or 0.0, (r or {}).get("e0") or 0.0
        s1, s0 = (r or {}).get("s1") or 0.0, (r or {}).get("s0") or 0.0
        m1, m0 = _div(e1, n1), _div(e0, n0)
        raw = None if m1 is None or m0 is None else m1 - m0
        league_gap = lg["gap"] if lg else None
        n = n1 * n0 / (n1 + n0) if n1 and n0 else 0.0
        k = self.k(season, side, split)
        w = n / (n + k)
        if league_gap is None:
            shrunk = None
        elif raw is None:
            shrunk = league_gap
        else:
            shrunk = league_gap + w * (raw - league_gap)
        rate = _div(n1, n1 + n0)
        if rate is None and lg:
            rate = lg["rate"]
        games = (r or {}).get("games") or 0
        return UnitSplit(
            split, team, side, n1, n0, m1, m0, _div(s1, n1), _div(s0, n0), raw, league_gap,
            shrunk, k, n, w, rate, _div(n1 + n0, games),
        )  # fmt: skip

    def unit_splits(self, season: int, week: int, team: str, side: str) -> list[UnitSplit]:
        return [self.unit_split(season, week, team, side, s.id) for s in splits.SPLITS]

    # -- overall units ------------------------------------------------------------------------

    def overall(self, season: int, week: int, side: str) -> dict[str, tuple[float, int]]:
        """team -> (EPA per play, plays) over every play, weeks < `week` (the shotgun universe)."""
        out = {}
        for (sd, split, team), r in self.units(season, week).items():
            if sd == side and split == OVERALL_SPLIT:
                n = int((r["n1"] or 0) + (r["n0"] or 0))
                if n:
                    out[team] = (((r["e1"] or 0.0) + (r["e0"] or 0.0)) / n, n)
        return out

    def unit_rank(self, season: int, week: int, team: str, side: str) -> UnitRank:
        team = _code(team)
        ov = self.overall(season, week, side)
        league_n = sum(n for _, n in ov.values())
        league = sum(e * n for e, n in ov.values()) / league_n if league_n else None
        if team not in ov:
            return UnitRank(team, side, None, len(ov), None, 0, league)
        sign = -1.0 if side == "off" else 1.0  # offense: higher is better; defense: lower is better
        rank = 1 + sum(1 for t, (e, _) in ov.items() if sign * e < sign * ov[team][0] and t != team)
        return UnitRank(team, side, rank, len(ov), ov[team][0], ov[team][1], league)

    def opponents_faced(
        self, season: int, week: int, team: str, side: str
    ) -> dict[str, Any] | None:
        """The average strength of the units `team`'s `side` unit has faced, weeks < `week`: for an
        offense the mean EPA per play its opponents' defenses allowed overall, for a defense the mean
        EPA their offenses made (season to date, each opponent counted once per game). Compare with
        `UnitRank.league_epa_pp`."""
        team = _code(team)
        d = self._season(season).filter(
            (pl.col("week") < week) & (pl.col("split") == OVERALL_SPLIT) & (pl.col("side") == side)
        )
        mine = d.filter(pl.col("team") == team)["game_id"].unique().to_list()
        if not mine:
            return None
        opp_side = "def" if side == "off" else "off"
        opp = self.overall(season, week, opp_side)
        opp_teams = (
            self._season(season)
            .filter(
                (pl.col("week") < week) & pl.col("game_id").is_in(mine)
                & (pl.col("split") == OVERALL_SPLIT) & (pl.col("side") == opp_side)
            )
            .select("game_id", "team")
            .unique()
        )  # fmt: skip
        vals = [opp[t][0] for t in opp_teams["team"] if t in opp]
        if not vals:
            return None
        return {"games": len(vals), "mean_epa_pp": float(np.mean(vals))}

    # -- the game -----------------------------------------------------------------------------

    def _opp_dist(self, season: int, week: int, side: str, split: str):
        lg = self.league(season, week).get((side, split))
        r = lg["rates"] if lg else []
        if not r:
            return None, None, None, None, None
        q = np.quantile(r, [0, 0.25, 0.5, 0.75, 1.0])
        return tuple(float(x) for x in q)

    def side_rows(
        self, season: int, week: int, offense: str, defense: str, reliab: dict[str, str]
    ) -> list[MatchupRow]:
        rows = []
        for s in splits.SPLITS:
            o = self.unit_split(season, week, offense, "off", s.id)
            d = self.unit_split(season, week, defense, "def", s.id)
            rel = reliab.get(s.id, NOISE)
            if s.chooser == "neither" or s.no_edge:
                rows.append(
                    MatchupRow(
                        s.id, s.label, s.chooser, False, None, None, None, None, None, None, None,
                        None, o.n_with, o.n_without, o.epa_with, o.epa_without, o.shrunk_gap,
                        o.league_gap, o.plays_pg, None, rel, o, d,
                        note=s.no_edge or "no edge: neither unit chooses this situation",
                    )
                )  # fmt: skip
                continue
            chooser_unit, owner = (d, o) if s.chooser == "defense" else (o, d)
            faced_unit = owner
            opp_side = "def" if s.chooser == "defense" else "off"
            dist = self._opp_dist(season, week, opp_side, s.id)
            opp_rate, rate_faced = chooser_unit.rate, faced_unit.rate
            edge = None
            if None not in (opp_rate, rate_faced, owner.shrunk_gap, owner.plays_pg):
                edge = (opp_rate - rate_faced) * owner.shrunk_gap * owner.plays_pg
            if owner.plays_pg is None:  # no plays yet: the league's plays per game is unknown
                edge = None
            favours = None if not edge else ("offense" if edge > 0 else "defense")
            rows.append(
                MatchupRow(
                    s.id, s.label, s.chooser, True, favours, opp_rate, *dist, rate_faced,
                    owner.n_with, owner.n_without, owner.epa_with, owner.epa_without,
                    owner.shrunk_gap, owner.league_gap, owner.plays_pg, edge, rel, o, d,
                )
            )  # fmt: skip
        return rows

    def matchup_edges(
        self, game: Any, as_of_week: int | None = None, ledger: pl.DataFrame | None = None
    ) -> MatchupEdges:
        season, week = int(_gv(game, "season")), int(_gv(game, "week"))
        as_of = week if as_of_week is None else as_of_week
        home, away = _code(_gv(game, "home_team")), _code(_gv(game, "away_team"))
        reliab = {s.id: reliability(s.id, ledger) for s in splits.SPLITS}
        sides = [
            MatchupSide(home, away, self.side_rows(season, as_of, home, away, reliab)),
            MatchupSide(away, home, self.side_rows(season, as_of, away, home, reliab)),
        ]
        return MatchupEdges(season, week, as_of, sides)


def _gv(game: Any, key: str):
    return game[key] if isinstance(game, dict) else getattr(game, key)


# ---- module-level functions ------------------------------------------------------------------


def unit_splits(season: int, week: int, team: str, side: str, con_or_df) -> list[UnitSplit]:
    """Every split for one unit, as of `week` (rows with week < `week` in `season`)."""
    return Engine(con_or_df).unit_splits(season, week, team, side)


def matchup_edges(
    game: Any, con_or_df, as_of_week: int | None = None, ledger: pl.DataFrame | None = None
) -> MatchupEdges:
    """Both sides' split rows for `game` (a dict or object with season, week, home_team, away_team),
    as of the game's week unless `as_of_week` says otherwise. `ledger` is the candidates ledger
    (`candidate_screen.latest(paths)`); without it every badge is `noise`."""
    return Engine(con_or_df).matchup_edges(game, as_of_week, ledger)


def unit_rank(season: int, week: int, team: str, side: str, con_or_df) -> UnitRank:
    """Rank of a unit by EPA per play over weeks < `week` (offense: highest first; defense: lowest
    allowed first), from the split model's all-plays universe."""
    return Engine(con_or_df).unit_rank(season, week, team, side)


def opponents_faced(season: int, week: int, team: str, side: str, con_or_df):
    return Engine(con_or_df).opponents_faced(season, week, team, side)


def reliability(split: str, ledger: pl.DataFrame | None = None) -> str:
    """`stable` (split-half r >= 0.3), `some` (>= 0.1) or `noise`, from the latest ledger row of
    candidate `split_<split>_gap`; `noise` when there is no row or no split-half r."""
    if ledger is None or ledger.is_empty() or "candidate" not in ledger.columns:
        return NOISE
    rows = ledger.filter(pl.col("candidate") == f"split_{split}_gap")
    if rows.is_empty():
        return NOISE
    if "run_at" in rows.columns:
        rows = rows.sort("run_at")
    r = rows["split_half"][-1]
    if r is None or (isinstance(r, float) and np.isnan(r)):
        return NOISE
    return STABLE if r >= STABLE_R else SOME if r >= SOME_R else NOISE


def load_ledger(paths) -> pl.DataFrame:
    """The latest candidates-ledger row per candidate (empty when the ledger doesn't exist)."""
    from nfl import candidate_screen

    try:
        return candidate_screen.latest(paths)
    except Exception:  # noqa: BLE001 - the ledger is optional context: badges fall back to `noise`
        return pl.DataFrame()


def ranks(con_or_df, season: int, week: int, teams: Iterable[str], side: str) -> list[UnitRank]:
    e = Engine(con_or_df)
    return [e.unit_rank(season, week, t, side) for t in teams]
