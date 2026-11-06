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
from scipy.stats import rankdata

from nfl.config import Paths
from nfl.league.standings import canon
from nfl.league.teams import team_latest

SCHEMA_VERSION = "1"
FIRST_CANDIDATE = 2002
MIN_GAMES = 4  # fewer and the record says little, and the vector is mostly last season
K_SUMMARY = 25
RECORD_WEIGHT = 2.0
FEATURES = (
    "strength.epa_off_adj",
    "strength.epa_def_adj",
    "strength.point_diff_pg",
    "strength.pythag_win_pct",
    "strength.qb_epa",
    "strength.sos",
)
# The seven axes of the profile chart, in fixed order: (id, label, better). `profile` percentiles
# are oriented so 100 is best where `better` is set; defense is lower-is-better, so it is flipped.
# Schedule has no good direction: 100 is the hardest schedule, 0 the easiest. Record is first and
# is the only axis that is not a feature (win pct after n games).
MEASURES = (
    ("record", "Record", "higher"),
    ("strength.epa_off_adj", "Offense", "higher"),
    ("strength.epa_def_adj", "Defense", "lower"),
    ("strength.point_diff_pg", "Point margin", "higher"),
    ("strength.pythag_win_pct", "Expected win rate", "higher"),
    ("strength.qb_epa", "QB play", "higher"),
    ("strength.sos", "Schedule", None),
)  # fmt: skip


@dataclass(frozen=True)
class FlagSpec:
    kind: str  # red | fine | strength
    measure: str
    end: str  # "lo": worst quarter on the oriented scale (low end if neutral); "hi": best quarter
    label: str
    outcome: str  # "made" the playoffs, or reached a conference game ("conf")
    better: str | None  # "higher" | "lower" | None (neutral)


# The flags the page may show, and nothing else: the page never searches for patterns at build
# time. Chosen 2026-11-06 after looking at 2002-2025 at 6, 8, 10 and 12 games, among teams on the
# same record; the split-half check reuses those seasons, so nothing here is a held-out test. The
# red and strength flags clear Benjamini-Hochberg at 10% and point the same way in both halves. The
# "fine" flags are nulls, no penalty found, except a low-luck record, which is a real effect. Table
# and method: .notes/plans/similar-insights.md, scripts/league_flags.py. Each says what the team's
# own quarter did against same-record peers, never that a measure matters on its own. Rejected:
# defense (adjusted, -3.4, too close to a penalty to call fine), point margin (conf not significant),
# high luck, EPA trend, rushing offense, special teams.
FLAG_SPECS = (
    FlagSpec("red", "strength.epa_off_adj", "lo", "Offense", "made", "higher"),
    FlagSpec("red", "strength.pythag_win_pct", "lo", "Expected win rate", "made", "higher"),
    FlagSpec("red", "strength.qb_epa", "lo", "QB play", "made", "higher"),
    FlagSpec("strength", "strength.elo_pre", "hi", "Long-run rating", "conf", "higher"),
    FlagSpec("strength", "strength.qb_epa", "hi", "QB play", "made", "higher"),
    FlagSpec("strength", "strength.epa_off_adj", "hi", "Offense", "made", "higher"),
    FlagSpec("fine", "strength.luck", "lo", "Luck", "made", None),  # record undersells them
    FlagSpec("fine", "form.last3_win_pct", "lo", "Last three games", "made", "higher"),
    FlagSpec("fine", "form.streak", "lo", "Streak", "made", "higher"),
    FlagSpec("fine", "decisions.turnover_margin_pg", "lo", "Turnover margin", "made", "higher"),
)  # fmt: skip
FLAG_FEATURES = tuple(dict.fromkeys(f.measure for f in FLAG_SPECS))
FLAG_KINDS = ("red", "fine", "strength")  # the page's group order
MIN_FLAGGED = 8
MIN_OTHERS = 15
MIN_FLAG_GAMES, MAX_FLAG_GAMES = 6, 12  # the study's range; from 13 games the effects fade or flip
MIN_GAP = 0.02  # under this the two groups are the same; the page's "share" wording uses it too
MIN_RATE, MAX_RATE = 0.10, 0.90  # outside these the record itself decided it, on either side
QUARTER = 0.25  # of that season's teams, so a rank and its quarter always agree
MAX_CARDS = 3
LOAD_FAMILIES = ("strength", "form", "decisions")
ROUND_RANK = {"WC": 1, "DIV": 2, "CON": 3, "SB": 4}
ROUND_NAME = {1: "wc", 2: "div", 3: "conf", 4: "sb"}
FEATURE_SCHEMA = {
    "season": pl.Int64, "game_id": pl.Utf8, "side": pl.Utf8, "feature": pl.Utf8,
    "value": pl.Float64, "known_as_of": pl.Datetime("us"),
}  # fmt: skip


def load_features(paths: Paths, season: int) -> pl.DataFrame:
    """Only what this module reads: its features from the strength, form and decisions families,
    candidate seasons through `season`. Filters go into the read, so the bucket mount serves a few
    columns of a few files a season."""
    root = paths.marts / "features"
    files = [
        f.as_posix() for fam in LOAD_FAMILIES for f in sorted(root.glob(f"season=*/{fam}.parquet"))
    ]
    if not files:
        return pl.DataFrame(schema=FEATURE_SCHEMA)
    names = ",".join(f"'{f}'" for f in (*FEATURES, *FLAG_FEATURES))
    listing = ",".join(f"'{f}'" for f in files)
    con = duckdb.connect()
    return con.sql(
        "select cast(season as bigint) as season, game_id, side, feature, "
        "cast(value as double) as value, cast(known_as_of as timestamp) as known_as_of "
        f"from read_parquet([{listing}], hive_partitioning=true) "
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
    fv: dict[str, float]  # FLAG_FEATURES known at this point (any may be missing)


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
            fv = {f: v[f] for f in FLAG_FEATURES if f in v}
            out.append(Candidate(s, team, n, rec, x, oc, fv))
    return out


def _sd(A: np.ndarray) -> np.ndarray:
    sd = A.std(0)
    sd[sd == 0] = 1.0
    return sd


def _nearest(cands: list[Candidate], x: np.ndarray, k: int) -> list[tuple[float, Candidate]]:
    """The k nearest of `cands` (all at one n) to x: standardized over the candidates, record
    weighted RECORD_WEIGHT. Ties break on the newer season, then the team code."""
    A = np.vstack([c.x for c in cands])
    sd = _sd(A)
    w = np.ones(A.shape[1])
    w[0] = RECORD_WEIGHT
    d = np.sqrt((((A - x) / sd * w) ** 2).sum(1))
    seasons = np.array([c.season for c in cands])
    teams = np.array([c.team for c in cands])
    order = np.lexsort((teams, -seasons, d))[:k]
    return [(float(d[i]), cands[i]) for i in order]


def _rec_str(rec: tuple[int, int, int]) -> str:
    return f"{rec[0]}-{rec[1]}" + (f"-{rec[2]}" if rec[2] else "")


def profile(pool_x: np.ndarray, x: np.ndarray) -> list[int]:
    """x's percentile (0 to 100) against each column of `pool_x`, in MEASURES order, oriented so
    100 is best where a measure has a direction (a lower-is-better measure is flipped). Ties count
    half. Schedule has no good direction, so 100 is the hardest."""
    out = []
    for j, (_id, _label, better) in enumerate(MEASURES):
        col = pool_x[:, j]
        p = 100 * ((col < x[j]).sum() + 0.5 * (col == x[j]).sum()) / len(col)
        out.append(round(100 - p if better == "lower" else p))
    return out


def gaps(pool_x: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[list[str], list[str]]:
    """(closest two, furthest one) measure ids between teams x and y: |difference| in percentile
    points, as the chart draws them, so the words and the dots agree. Ties go to the earlier measure."""
    g = np.abs(np.array(profile(pool_x, x)) - np.array(profile(pool_x, y)))
    asc = np.argsort(g, kind="stable")
    desc = np.argsort(-g, kind="stable")
    return [MEASURES[i][0] for i in asc[:2]], [MEASURES[desc[0]][0]]


def _nearest_row(d: float, c: Candidate, pool_x: np.ndarray, x: np.ndarray) -> dict:
    closest, furthest = gaps(pool_x, x, c.x)
    return {
        "season": c.season, "team": c.team, "dist": round(d, 2), "rec_then": _rec_str(c.rec),
        "final": c.outcome.final, "playoffs": c.outcome.playoffs, "round": c.outcome.round,
        "profile": profile(pool_x, c.x), "closest": closest, "furthest": furthest,
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


@dataclass
class Current:
    n: int
    rec: tuple[int, int, int]
    x: np.ndarray
    fv: dict[str, float]  # FLAG_FEATURES from the same game's row as x


def _current(
    games: pl.DataFrame, feats: pl.DataFrame, season: int, now: datetime
) -> tuple[dict[str, Current], dict[str, dict[str, int]]]:
    """(team -> Current, measure -> team -> rank among the teams with a row, 1 = best by the
    measure's direction, highest first when it has none) from `team_latest`. A team with no row for
    one of the FEATURES, or rows for different games, is left out.

    Only regular-season games go to `team_latest`: once a playoff team's next row is a postseason
    game there is no pool at that n, and the team would drop out until August."""
    none: tuple[dict, dict] = ({}, {})
    cur = _naive(games.filter((pl.col("season") == season) & (pl.col("game_type") == "REG")))
    if feats.is_empty() or cur.is_empty():
        return none
    latest = team_latest(feats.filter(pl.col("season") == season), cur, now)
    if latest.is_empty():
        return none
    by_team: dict[str, dict[str, tuple[float, str, datetime]]] = {}
    for f, t, v, gid, k in latest.select("feature", "team", "value", "game_id", "kickoff_utc").iter_rows():  # fmt: skip
        by_team.setdefault(t, {})[f] = (v, gid, k)
    ranks: dict[str, dict[str, int]] = {}
    for spec in FLAG_SPECS:
        vals = {t: fv[spec.measure][0] for t, fv in by_team.items() if spec.measure in fv}
        sign = -1.0 if spec.better == "lower" else 1.0
        ranks[spec.measure] = {
            t: 1 + sum(sign * u > sign * v for u in vals.values()) for t, v in vals.items()
        }
    tg = _team_games(cur)
    out = {}
    for team, fv in by_team.items():
        if any(f not in fv for f in FEATURES) or len({fv[f][1] for f in FEATURES}) != 1:
            continue
        gid, kick = fv[FEATURES[0]][1], fv[FEATURES[0]][2]
        if kick is None:
            continue
        # Position of the row's game among the team's scored regular-season games. After a team's
        # last game there is no next row, so team_latest hands back its last one: n is then the
        # games before it, and the final game is not in that vector. Only scored games count, so
        # a kickoff with no score yet doesn't drop the team. A late score can leave n one ahead of
        # the vector until the next feature build; that is accepted.
        scored = [r for r in tg.get((season, team), []) if r[2] and r[4] is not None]
        n = sum(r[0] is not None and (r[0], r[1]) < (kick, gid) for r in scored)
        rec = _record_to(scored, n)
        if rec is None or n < MIN_GAMES:
            continue
        x = np.array([_pct(rec, n), *(fv[f][0] for f in FEATURES)], dtype=float)
        flag_vals = {f: fv[f][0] for f in FLAG_FEATURES if f in fv and fv[f][1] == gid}
        out[team] = Current(n, rec, x, flag_vals)
    return out, ranks


class FlagTable:
    """The history at one games-played count, as arrays, for the flag rules."""

    def __init__(self, pool: list[Candidate]):
        self.pool = pool
        self.key = np.array([2 * c.rec[0] + c.rec[2] for c in pool])  # wins, ties half, doubled
        self.made = np.array([c.outcome.playoffs for c in pool], dtype=float)
        self.conf = np.array([c.outcome.rank >= 3 for c in pool], dtype=float)
        self._cache: dict[tuple[str, str], tuple] = {}

    def column(self, spec: FlagSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(has a value, oriented value, in the spec's quarter) over the pool. Oriented: higher is
        better where the measure has a direction. The quarter is within each season at this n: EPA
        levels drift over the years, and "bottom quarter" has to mean the same as a team's rank."""
        hit = self._cache.get((spec.measure, spec.end))
        if hit is None:
            sign = -1.0 if spec.better == "lower" else 1.0
            has = np.array([spec.measure in c.fv for c in self.pool])
            x = np.array([sign * c.fv.get(spec.measure, np.nan) for c in self.pool])
            inq = np.zeros(len(self.pool), dtype=bool)
            seasons = np.array([c.season for c in self.pool])
            for s in np.unique(seasons[has]):
                m = has & (seasons == s)
                r = rankdata(x[m] if spec.end == "lo" else -x[m], method="average")
                inq[m] = r / m.sum() <= QUARTER
            hit = self._cache[(spec.measure, spec.end)] = (has, x, inq)
        return hit

    def peers(self, rec_key: int) -> dict[str, int]:
        """How teams on exactly this record did, whatever their measures."""
        same = self.key == rec_key
        return {"made": int(self.made[same].sum()), "n": int(same.sum())}

    def counts(self, spec: FlagSpec, rec_key: int) -> tuple | None:
        """([k, n] flagged, [k, n] others) among teams on exactly this record, or None if short of
        MIN_FLAGGED or MIN_OTHERS. No widening: a range of records puts the weak teams at its low end
        and the rest at its high end, and the gap is then mostly the record."""
        has, _, inq = self.column(spec)
        y = self.conf if spec.outcome == "conf" else self.made
        peers = has & (self.key == rec_key)
        f, o = peers & inq, peers & ~inq
        if f.sum() < MIN_FLAGGED or o.sum() < MIN_OTHERS:
            return None
        return [int(y[f].sum()), int(f.sum())], [int(y[o].sum()), int(o.sum())]


def in_quarter(spec: FlagSpec, rank: int, ranks: list[int]) -> bool:
    """This team's quarter among this season's teams, by average rank, as `FlagTable.column` does for
    the history. `ranks` are every team's min-ranks: 1 is the best, or the highest on a neutral
    measure, so a low end is a high rank number either way."""
    n = len(ranks)
    mean = rank + (ranks.count(rank) - 1) / 2
    return (n + 1 - mean if spec.end == "lo" else mean) / n <= QUARTER


def flag_cards(
    table: FlagTable, cur: Current, rank_of: dict[str, dict[str, int]], team: str
) -> list[dict]:
    """The cards for one team, in the page's group order, at most MAX_CARDS a group, biggest gap
    first. Peers: same games played and exactly the same record; below MIN_FLAGGED flagged or
    MIN_OTHERS others, no card. A card shows only inside the study's range of games, and only if its
    own counts agree with its kind: red a lower rate than the others, strength a higher one, fine no
    lower, each by MIN_GAP, with rates that aren't settled by the record alone."""
    if not MIN_FLAG_GAMES <= cur.n <= MAX_FLAG_GAMES:
        return []
    key = 2 * cur.rec[0] + cur.rec[2]
    cards = []
    for spec in FLAG_SPECS:
        v = cur.fv.get(spec.measure)
        if v is None or team not in rank_of.get(spec.measure, {}) or not table.pool:
            continue
        if not in_quarter(spec, rank_of[spec.measure][team], list(rank_of[spec.measure].values())):
            continue
        got = table.counts(spec, key)
        if got is None:
            continue
        (fk, fn), (ok, on) = got
        a, b = fk / fn, ok / on
        gap = a - b
        if max(a, b) < MIN_RATE or min(a, b) > MAX_RATE:
            continue  # at 0-7 nobody made it, at 11-3 everybody did: nothing to say either way
        agree = {
            "red": gap <= -MIN_GAP,
            "strength": gap >= MIN_GAP,
            "fine": gap >= -MIN_GAP and fk >= 1,
        }
        if not agree[spec.kind]:
            continue
        cards.append((
            abs(gap), spec.measure,
            {
                "kind": spec.kind, "measure": spec.measure, "label": spec.label,
                "rank": rank_of[spec.measure][team],
                "quarter": "bottom" if spec.end == "lo" else "top", "outcome": spec.outcome,
                "peers": _rec_str(cur.rec),
                "flagged": [fk, fn], "others": [ok, on],
            },
        ))  # fmt: skip
    out = []
    for kind in FLAG_KINDS:
        mine = sorted((c for c in cards if c[2]["kind"] == kind), key=lambda c: (-c[0], c[1]))
        out += [c[2] for c in mine[:MAX_CARDS]]
    return out


def similar_file(games: pl.DataFrame, feats: pl.DataFrame, season: int, now: datetime) -> dict:
    """The site/similar.json object. `games` carries every season from FIRST_CANDIDATE through
    `season`; `feats` is `load_features`' output. Teams with nothing to show are absent."""
    out: dict = {
        "schema_version": SCHEMA_VERSION,
        "season": season,
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "measures": [{"id": i, "label": label} for i, label, _ in MEASURES],
        "teams": {},
    }
    if feats.is_empty() or games.is_empty():
        return out
    cur, ranks = _current(games, feats, season, now)
    if not cur:
        return out
    by_n: dict[int, list[Candidate]] = {}
    for c in candidates(games, feats, season):
        by_n.setdefault(c.n, []).append(c)
    tables: dict[int, FlagTable] = {}
    for team, c in sorted(cur.items()):
        pool = by_n.get(c.n, [])
        if len(pool) < K_SUMMARY:
            continue
        pool_x = np.vstack([p.x for p in pool])
        near = _nearest(pool, c.x, K_SUMMARY)
        table = tables.setdefault(c.n, FlagTable(pool))
        seasons = [p.season for p in pool]
        out["teams"][canon(team)] = {
            "games_played": c.n,
            "record": _rec_str(c.rec),
            **summary(near),
            "pool": {"seasons": [min(seasons), max(seasons)], "n": len(pool)},
            "profile": profile(pool_x, c.x),
            "nearest": [_nearest_row(d, p, pool_x, c.x) for d, p in near],
            "peers": table.peers(2 * c.rec[0] + c.rec[2]),
            "flags": flag_cards(table, c, ranks, team),
        }
    return out
