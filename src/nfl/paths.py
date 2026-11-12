"""Paths to an upset (ADR 0028, M25.4): conditions, never a probability.

Pure functions over the `upset_conditions` SQL model (one row per game and team, see
src/nfl/sql/models/upset_conditions.sql). Pass a DuckDB connection from `nfl.catalog.connect` or the
model's polars frame; nothing here reads or writes files. Every number in a sentence comes from the
returned record (ADR 0024's rule); the record is plain data (`dataclasses.asdict` gives site JSON).

Point in time: the bucket table for a game in season S reads seasons < S; a team's rate of producing or
allowing a condition reads that season's games with week < `as_of_week`. The game itself and later
games are never read.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import polars as pl

from nfl.models.elo import TEAM_ALIASES

COIN_FLIP = "coin flip for every team"
WEAK = "weakly predictable"

BUCKETS = ("0-2.5", "3-6.5", "7-9.5", "10+")
TOP_N = 3
MAX_LEVERS = 4  # Austin, 2026-11-12: up to four when four are worth showing
MIN_GAP = 8  # rank places between the dog's unit and the favorite's matching unit
MAX_DOG_RANK = 16  # the dog's unit is in the top half
MIN_RANK_WEEK = 4  # ranks need three games


@dataclass(frozen=True)
class Condition:
    id: str
    column: str  # boolean column in upset_conditions, from the team's view
    label: str
    definition: str
    plan: str  # "to win" phrasing after "How X wins:"
    done: str  # past tense after the team name, for the outcome sentence
    plausibility: str
    measured_r: float | None  # pre-game r of both teams' season rates with the realized margin
    help: str
    # For the levers and the face-off (ranks): the per-game value of this team's offense (`stat`) and
    # of the opponent's offense against it (`stat_opp`, what this team's defense allowed), and whether
    # more is better for the offense. `net`: one ranking of stat - stat_opp (special teams).
    stat: str = ""
    stat_opp: str = ""
    higher_better: bool = True
    off_noun: str = ""  # "GB's <off_noun> (7th)"
    def_noun: str = ""
    tier: int = 1  # 2 = weaker conditions, picked as levers only after every tier-1 one
    family: str = ""  # at most one lever per family (explosives, big runs and deep passes overlap)
    net: bool = False


CONDITIONS: tuple[Condition, ...] = (
    Condition(
        "turnovers",
        "turnovers",
        "Win the turnover battle",
        "Takeaways minus giveaways (interceptions and lost fumbles) of at least +1.",
        "win the turnover battle",
        "won the turnover battle",
        COIN_FLIP,
        0.005,
        "Before a game, both teams' turnover rates to date predict its turnover margin with r +0.005 "
        "(2006-2025): a coin flip for every team.",
        "giveaways",
        "takeaways",
        False,
        "ball security",
        "takeaways",
    ),
    Condition(
        "early_down",
        "early_down",
        "Win early downs",
        "The team's EPA per play on first and second down (win probability 20-80%) beats the opponent's.",
        "win early downs",
        "won early downs",
        WEAK,
        0.17,
        "Season-to-date early-down EPA predicts the game's with r +0.17 (2006-2025): weakly predictable.",
        "early_down_epa",
        "early_down_epa_opp",
        True,
        "early-down offense",
        "early-down defense",
    ),
    Condition(
        "explosives",
        "explosives_more",
        "More explosive plays",
        "More passes of 20+ yards and runs of 10+ yards than the opponent.",
        "hit more explosive plays",
        "had more explosive plays",
        WEAK,
        0.16,
        "Season-to-date explosive plays predict the game's with r +0.16 (2006-2025): weakly predictable.",
        "explosives",
        "explosives_opp",
        True,
        "explosive plays",
        "explosive-play defense",
        family="explosive",
    ),
    Condition(
        "sacks",
        "sacks",
        "Sack the quarterback more",
        "The opponent's offense was sacked at least two more times than this team's.",
        "out-sack the other side by two",
        "out-sacked the other side by two",
        WEAK,
        0.15,
        "Season-to-date sack rates predict the game's sack margin with r +0.15 (2006-2025): weakly "
        "predictable.",
        "sacks_taken",
        "sacks_made",
        False,
        "pass protection",
        "pass rush",
    ),
    Condition(
        "special_teams",
        "special_teams",
        "Win special teams",
        "Special-teams EPA at least +3 points better than the opponent's.",
        "win special teams by a field goal",
        "won special teams by a field goal",
        WEAK,
        None,
        "Not measured before the game; the history says what winning dogs did, nothing about whether "
        "either team tends to produce it.",
        "st_epa",
        "st_epa_opp",
        True,
        "special teams",
        "special teams",
        net=True,
    ),
    # Six more (Austin, 2026-11-12). r: both teams' season-to-date rates (week 4 on) against the
    # game's difference, 2006-2025, measured the way the five above were.
    Condition(
        "pass_game",
        "pass_game",
        "Pass better",
        "More EPA per dropback than the opponent (sacks and scrambles count; win probability 20-80%).",
        "out-pass the other side",
        "out-passed the other side",
        WEAK,
        0.20,
        "Season-to-date EPA per dropback predicts the game's difference with r +0.20 (2006-2025): "
        "weakly predictable. It is also close to the result itself: a team that passes well scores.",
        "pass_epa",
        "pass_epa_opp",
        True,
        "passing offense",
        "pass defense",
    ),
    Condition(
        "big_runs",
        "big_runs_more",
        "More big runs",
        "More runs of 10+ yards than the opponent.",
        "break more big runs",
        "broke more big runs",
        WEAK,
        0.22,
        "Season-to-date 10-yard runs predict the game's difference with r +0.22 (2006-2025): weakly "
        "predictable.",
        "big_runs",
        "big_runs_opp",
        True,
        "big-play run game",
        "run defense on big plays",
        family="explosive",
    ),
    Condition(
        "third_down",
        "third_down",
        "Win third down",
        "A higher third-down conversion rate than the opponent.",
        "convert more third downs",
        "converted more third downs",
        WEAK,
        0.15,
        "Season-to-date third-down rates predict the game's difference with r +0.15 (2006-2025): weakly "
        "predictable.",
        "third_down_rate",
        "third_down_rate_opp",
        True,
        "third-down offense",
        "third-down defense",
    ),
    Condition(
        "run_game",
        "run_game",
        "Run more efficiently",
        "A higher rush success rate than the opponent (win probability 20-80%).",
        "run more efficiently",
        "ran more efficiently",
        WEAK,
        0.13,
        "Season-to-date rush success predicts the game's difference with r +0.13 (2006-2025): weakly "
        "predictable.",
        "rush_sr",
        "rush_sr_opp",
        True,
        "run game",
        "run defense",
        tier=2,
    ),
    Condition(
        "deep_passes",
        "deep_passes_more",
        "More deep completions",
        "More completions of 20+ yards than the opponent.",
        "hit more deep passes",
        "hit more deep passes",
        WEAK,
        0.14,
        "Season-to-date 20-yard completions predict the game's difference with r +0.14 (2006-2025): "
        "weakly predictable.",
        "deep_passes",
        "deep_passes_opp",
        True,
        "deep passing",
        "deep-pass defense",
        tier=2,
        family="explosive",
    ),
    Condition(
        "red_zone",
        "red_zone",
        "Finish in the red zone",
        "A higher touchdown rate on drives that reach the opponent's 20.",
        "finish drives in the red zone",
        "finished more red-zone drives",
        COIN_FLIP,
        0.04,
        "Season-to-date red-zone touchdown rates predict the game's difference with r +0.04 "
        "(2006-2025): a coin flip for every team.",
        "rz_td_rate",
        "rz_td_rate_opp",
        True,
        "red-zone offense",
        "red-zone defense",
        tier=2,
    ),
)
CORE = tuple(c for c in CONDITIONS if c.tier == 1 and c.id in (
    "turnovers", "early_down", "explosives", "sacks", "special_teams"))  # fmt: skip
BY_ID = {c.id: c for c in CONDITIONS}

TAIL = " None of this is in the odds we show; it is what winning underdogs did."


# ---- records (plain data; asdict -> JSON) ----------------------------------------------------


@dataclass
class BucketCell:
    """One size bucket x condition over earlier seasons' dogs."""

    bucket: str
    condition: str
    n_dogs: int  # dogs in the bucket
    n: int  # of them, how many met the condition
    win_rate_if: float | None  # dog win rate given the condition (None when n = 0)
    happens: float | None  # share of dogs in the bucket that met it
    base_rate: float | None  # the bucket's dog win rate


@dataclass
class ConditionPath:
    id: str
    label: str
    definition: str
    win_rate_if: float | None
    win_rate_pct: int | None
    n: int
    happens: float | None
    happens_pct: int | None
    base_rate: float | None
    base_rate_pct: int | None
    dog_games: int  # the dog's games this season before the as-of week
    dog_count: int  # of them, how many it produced the condition
    fav_games: int  # the favorite's games, same window
    fav_count: int  # of them, how many it allowed the condition (the other side produced it)
    plausibility: str
    measured_r: float | None
    help: str


@dataclass
class RankRow:
    """One team's season-to-date rank on one condition's stat, 1 = best, before the as-of week."""

    id: str
    label: str
    off_noun: str
    def_noun: str
    off_value: float | None  # per game: the offense's value (or the net, for special teams)
    off_rank: int | None
    def_value: float | None  # per game: what the defense allowed (the net again for special teams)
    def_rank: int | None
    n_teams: int
    games: int


@dataclass
class Lever:
    """A condition where the dog's unit is strong and the favorite's matching unit is weak."""

    id: str
    label: str
    side: str  # offense | defense | net: which of the dog's units
    dog_noun: str
    fav_noun: str
    dog_rank: int
    fav_rank: int
    n_teams: int
    gap: int  # fav_rank - dog_rank
    win_rate_pct: int | None  # dogs of this size who met the condition
    base_rate_pct: int | None  # all dogs of this size
    plausibility: str
    tier: int
    headline: str


@dataclass
class Chip:
    """A tier-1 condition that isn't a lever, said in one line."""

    id: str
    label: str
    kind: str  # even | favorite | weak (the dog ranks better, but its unit is not good)
    dog_noun: str
    fav_noun: str
    dog_rank: int
    fav_rank: int
    text: str


@dataclass
class UpsetPaths:
    game_id: str | None
    season: int
    week: int
    as_of_week: int
    dog: str
    favorite: str
    size: float  # points, |spread|
    bucket: str
    base_rate: float | None
    base_rate_pct: int | None
    conditions: list[ConditionPath] = field(default_factory=list)  # all five, best win rate first
    top: list[str] = field(default_factory=list)  # ids of the levers, in order
    sentence: str = ""
    levers: list[Lever] = field(default_factory=list)
    chips: list[Chip] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutcomeCondition:
    id: str
    label: str
    met: bool


@dataclass
class PathsOutcome:
    game_id: str
    dog: str
    favorite: str
    size: float
    bucket: str
    dog_won: bool
    tied: bool
    margin: float  # the dog's margin
    conditions: list[OutcomeCondition] = field(default_factory=list)
    met: list[str] = field(default_factory=list)  # ids
    sentence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---- helpers ---------------------------------------------------------------------------------


def load_conditions(con) -> pl.DataFrame:
    """The `upset_conditions` model from a catalog connection (empty when it isn't built)."""
    return con.sql("select * from upset_conditions").pl()


def _frame(con_or_df) -> pl.DataFrame:
    return con_or_df if isinstance(con_or_df, pl.DataFrame) else load_conditions(con_or_df)


def bucket_of(spread: float) -> str:
    a = abs(spread)
    return "0-2.5" if a < 3 else "3-6.5" if a < 7 else "7-9.5" if a < 10 else "10+"


def _code(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


def _pct(x: float | None) -> int | None:
    return None if x is None else round(100 * x)


# ---- the bucket table ------------------------------------------------------------------------


def bucket_table(con_or_df, before_season: int) -> list[BucketCell]:
    """Dogs' win rate by size bucket x condition over seasons < `before_season` (point in time)."""
    df = _frame(con_or_df)
    dogs = df.filter((pl.col("role") == "dog") & (pl.col("season") < before_season))
    out = []
    for b in BUCKETS:
        d = dogs.filter(pl.col("size_bucket") == b)
        n_dogs = d.height
        base = d["won"].mean() if n_dogs else None
        for c in CONDITIONS:
            w = d.filter(pl.col(c.column))
            n = w.height
            out.append(
                BucketCell(
                    b, c.id, n_dogs, n,
                    w["won"].mean() if n else None,
                    n / n_dogs if n_dogs else None,
                    base,
                )
            )  # fmt: skip
    return out


# ---- before the game -------------------------------------------------------------------------


def _rate_counts(df: pl.DataFrame, season: int, as_of_week: int, team: str, col: str, *, own: bool):
    """(games, count): the team's games this season before the as-of week where `col` held for the
    team (own=True: what it produces) or for its opponent (own=False: what it allows)."""
    key = "team" if own else "opponent"
    g = df.filter(
        (pl.col("season") == season) & (pl.col("week") < as_of_week) & (pl.col(key) == team)
    )
    return g.height, int(g[col].fill_null(False).sum()) if g.height else 0


def _gv(game: Any, key: str):
    return game[key] if isinstance(game, dict) else getattr(game, key)


def _gv0(game: Any, key: str, default=None):
    try:
        return _gv(game, key)
    except KeyError, AttributeError:
        return default


def upset_paths(game: Any, as_of_week: int, con_or_df) -> UpsetPaths | None:
    """How the underdog can win `game`, as conditions with history. `game` has season, week, home_team,
    away_team and spread_line (> 0 means home favored); game_id optional. None for a pick'em or a
    missing line. Never a probability."""
    spread = _gv0(game, "spread_line")
    if spread is None or np.isnan(spread) or spread == 0:
        return None
    season, week = int(_gv(game, "season")), int(_gv(game, "week"))
    home, away = _gv(game, "home_team"), _gv(game, "away_team")
    dog, fav = (away, home) if spread > 0 else (home, away)
    df = _frame(con_or_df)
    bucket = bucket_of(spread)
    cells = {c.condition: c for c in bucket_table(df, season) if c.bucket == bucket}
    base = next(iter(cells.values())).base_rate
    conds = []
    for c in CONDITIONS:
        cell = cells[c.id]
        dg, dc = _rate_counts(df, season, as_of_week, _code(dog), c.column, own=True)
        fg, fc = _rate_counts(df, season, as_of_week, _code(fav), c.column, own=False)
        conds.append(
            ConditionPath(
                c.id, c.label, c.definition, cell.win_rate_if, _pct(cell.win_rate_if), cell.n,
                cell.happens, _pct(cell.happens), base, _pct(base), dg, dc, fg, fc,
                c.plausibility, c.measured_r, c.help,
            )
        )  # fmt: skip
    conds.sort(key=lambda x: -(x.win_rate_if if x.win_rate_if is not None else -1.0))
    out = UpsetPaths(
        _gv0(game, "game_id"), season, week, int(as_of_week), dog, fav, abs(float(spread)), bucket,
        base, _pct(base), conds,
    )  # fmt: skip
    out.levers, out.chips = levers_and_chips(out, team_ranks(df, season, int(as_of_week)))
    out.top = [lv.id for lv in out.levers]
    out.sentence = _paths_sentence(out)
    return out


def _paths_sentence(p: UpsetPaths) -> str:
    if p.levers:
        heads = [lv.headline for lv in p.levers]
        return f"Where {p.dog} has the edge: {'; '.join(heads)}.{TAIL}"
    if p.chips:
        return (
            f"No clear mismatch for {p.dog}: none of its strong units meets a weak {p.favorite} unit."
            f"{TAIL}"
        )
    return f"Too early in the season to rank {p.dog}'s units against {p.favorite}'s.{TAIL}"


# ---- ranks and levers -----------------------------------------------------------------------


def ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _rank(values: dict[str, float], best_high: bool) -> dict[str, int]:
    """1 = best; ties share the better rank ('min')."""
    order = sorted(values.values(), reverse=best_high)
    return {t: order.index(v) + 1 for t, v in values.items()}


def team_ranks(con_or_df, season: int, as_of_week: int) -> dict[str, dict[str, RankRow]]:
    """Every team's rank on every condition's stat, this season, games with week < as_of_week (point
    in time). Empty before MIN_RANK_WEEK. Teams are play codes (LA, LAC, LV)."""
    if as_of_week < MIN_RANK_WEEK:
        return {}
    df = _frame(con_or_df).filter((pl.col("season") == season) & (pl.col("week") < as_of_week))
    if df.is_empty():
        return {}
    out: dict[str, dict[str, RankRow]] = {}
    games = dict(df.group_by("team").len().iter_rows())
    for c in CONDITIONS:
        if not c.stat or c.stat not in df.columns:
            continue
        if c.net:
            agg = df.group_by("team").agg((pl.col(c.stat) - pl.col(c.stat_opp)).mean().alias("o"))
            agg = agg.with_columns(pl.col("o").alias("d"))
        else:
            agg = df.group_by("team").agg(
                pl.col(c.stat).mean().alias("o"), pl.col(c.stat_opp).mean().alias("d")
            )
        agg = agg.drop_nulls(["o", "d"])
        off = dict(zip(agg["team"], agg["o"], strict=True))
        dfn = dict(zip(agg["team"], agg["d"], strict=True))
        ro = _rank(off, c.higher_better)
        # a defense is best when the offenses it faced did worst
        rd = ro if c.net else _rank(dfn, not c.higher_better)
        for t, v in off.items():
            out.setdefault(t, {})[c.id] = RankRow(
                c.id, c.label, c.off_noun, c.def_noun, round(v, 3), ro[t], round(dfn[t], 3),
                rd[t], len(off), games[t],
            )  # fmt: skip
    return out


def _angles(c: Condition, d: RankRow, f: RankRow):
    """(side, dog_noun, fav_noun, dog_rank, fav_rank) for each way the dog's units meet the
    favorite's on this condition."""
    if c.net:
        return [("net", c.off_noun, c.off_noun, d.off_rank, f.off_rank)]
    return [
        ("offense", c.off_noun, c.def_noun, d.off_rank, f.def_rank),
        ("defense", c.def_noun, c.off_noun, d.def_rank, f.off_rank),
    ]


def levers_and_chips(p: UpsetPaths, ranks: dict[str, dict[str, RankRow]]):
    """The dog's levers (strong unit against a weak one, at most MAX_LEVERS, tier-1 conditions
    first, then by gap x lift, one per family) and a chip for each tier-1 condition left over."""
    d, f = ranks.get(_code(p.dog)), ranks.get(_code(p.favorite))
    if not d or not f:
        return [], []
    by_id = {c.id: c for c in p.conditions}
    cands, best = [], {}
    for c in CONDITIONS:
        if c.id not in d or c.id not in f:
            continue
        cp = by_id[c.id]
        lift = (cp.win_rate_if or 0) - (cp.base_rate or 0)
        angs = sorted(_angles(c, d[c.id], f[c.id]), key=lambda a: -(a[4] - a[3]))
        best[c.id] = angs[0]
        side, dn, fn, dr, fr = angs[0]
        if dr <= MAX_DOG_RANK and fr - dr >= MIN_GAP and lift > 0:
            cands.append((c.tier, -(fr - dr) * lift, c, angs[0], cp))
    cands.sort(key=lambda x: (x[0], x[1]))
    levers, families = [], set()
    for _, _, c, (side, dn, fn, dr, fr), cp in cands:
        if c.family and c.family in families:
            continue
        if c.family:
            families.add(c.family)
        head = f"{p.dog}'s {dn} ({ordinal(dr)}) against {p.favorite}'s {fn} ({ordinal(fr)})"
        levers.append(
            Lever(
                c.id, c.label, side, dn, fn, dr, fr, d[c.id].n_teams, fr - dr, cp.win_rate_pct,
                cp.base_rate_pct, c.plausibility, c.tier, head,
            )
        )  # fmt: skip
        if len(levers) == MAX_LEVERS:
            break
    taken = {lv.id for lv in levers}
    chips = []
    for c in CONDITIONS:
        if c.tier != 1 or c.id in taken or c.id not in best or (c.family and c.family in families):
            continue
        side, dn, fn, dr, fr = best[c.id]
        gap = fr - dr
        kind = "favorite" if gap <= -MIN_GAP else "weak" if gap >= MIN_GAP else "even"
        text = f"{p.dog}'s {dn} {ordinal(dr)}, {p.favorite}'s {fn} {ordinal(fr)}"
        chips.append(Chip(c.id, c.label, kind, dn, fn, dr, fr, text))
    return levers, chips


# ---- after the game --------------------------------------------------------------------------


def paths_outcome(game_id: str, con_or_df) -> PathsOutcome | None:
    """For a finished game: which of the tier-1 conditions the underdog met, and whether it won. None
    for a pick'em or a game the model doesn't hold (unplayed, postseason, no line)."""
    df = _frame(con_or_df).filter(pl.col("game_id") == game_id)
    dog = df.filter(pl.col("role") == "dog")
    if dog.height != 1:
        return None
    r = dog.row(0, named=True)
    conds = [OutcomeCondition(c.id, c.label, bool(r[c.column])) for c in CONDITIONS if c.tier == 1]
    met = [c.id for c in conds if c.met]
    tied = r["margin"] == 0
    won = bool(r["won"])
    fate = "it won" if won else "it tied" if tied else "it lost"
    team = r["team"]
    if met:
        phr = [BY_ID[i].done.format(dog=team, fav=r["opponent"]) for i in met]
        said = phr[0] if len(phr) == 1 else ", ".join(phr[:-1]) + " and " + phr[-1]
        sentence = f"{team} {said}; {fate}."
    else:
        sentence = f"{team} met none of the conditions; {fate}."
    return PathsOutcome(
        game_id, team, r["opponent"], abs(float(r["spread"])), r["size_bucket"], won, tied,
        float(r["margin"]), conds, met, sentence,
    )  # fmt: skip
