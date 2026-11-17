"""Deserved to win (ADR 0016 amendment 2026-11-17): who the plays said should have won.

The old "played like" rested on one input, EPA per play with turnover plays dropped, counted over
the whole game. It read MIN's 30-10 win at GB (2026 week 10) as 58% MIN: GB's passes while down
17-20 in the second half counted in full, GB's three turnovers (two lost fumbles) counted not at
all, and home field moved the answer 9 points toward GB.

The meter is a margin in points built from three factors, each measured on the plays that still
mattered, and turned into a win chance:

    deserved margin (home - away) = b_eff * d_efficiency + b_chance * d_chances - d_giveaways
    deserved to win (home)        = 1 / (1 + exp(-k * deserved margin))

- **Garbage time.** Every play is weighted by how much the game was still in doubt, from
  nflfastR's win probability for the offense before the snap (`wp`, the model without the
  spread): weight 1 while it is between 5% and 95%, falling linearly to a quarter at 1% and 99%
  (a garbage-time snap still says a little about a team). A play with no `wp` counts fully.
  Tested on 2015-2025 against no weighting, stricter rules (10/90 hard, 15/85) and floors of 0,
  0.1, 0.25 and 0.5: the soft rule fit the result best, and the quarter floor held the same fit
  and carried slightly more to the rest of the season (r 0.259 against 0.255 with no floor).
- **Efficiency**: weighted EPA per play over the offense's passes and runs, interceptions and
  lost fumbles left out (they are the third factor).
- **Scoring chances**: the weighted share of drives that reached the opponent's 40 (a pass, run,
  field goal or punt snapped there), each drive weighted by its first snap.
- **Giveaways, in points**: the expected points a team handed over, priced by what each
  turnover costs on average (`value_interception`, `value_fumble_lost` in the expectations), not
  fitted. Fumbles count at the league's lost share (who fell on the ball doesn't count, putting
  it on the ground does). Interceptions are shrunk toward the league rate: 0.45 x interceptions
  + 0.55 x league rate x dropbacks (Austin, 2026-11-18: some picks are tips, some bad throws
  aren't caught). 0.45 is measured: on FTN's charting (2022-2025, 2,173 team-games) only 49% of
  interception-worthy throws were picked and 14% of interceptions weren't charted as bad
  throws; regressing a game's charted expected interceptions on its actual ones gives a slope of
  0.45 (correlation 0.63). The price is fixed because a fitted one re-inflates: with picks
  shrunk, the least-squares price per giveaway rose from 3.2 to 4.8 points and undid the change.
- **Left out**: success rate and the share of snaps that came on third down (both are in the
  retro's Efficiency section, against the season and the league). On
  2015-2025 games neither adds to the margin once efficiency and scoring chances are in (success
  rate's weight is about zero; third-down share's sign flips with the set). Over a season, though,
  fewer third downs goes with a better offense (team-season r = -0.80 with EPA per play).

Efficiency and scoring-chance weights are a least-squares fit of the final margin less the
giveaway points, no intercept, so
the meter is symmetric and home field plays no part; `k` is a one-parameter logistic of the
result on the fitted margin. Both are fit on the expectations window (regular seasons
2015-2025) and used only for later seasons (principle 2; `applies_to`).

What the screen found (2015-2021 fit, 2022-2025 held out): the three factors explain 76% of the
margin's variance (EPA alone 63%); the meter's log loss on the result is 0.30 (the old one 0.46);
the deserved winner lost 12.5% of games. As a forecast of the rest of the season no single-game
set beats another (r about 0.25 for all, the real margin included): one game is mostly noise.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl

from nfl.retro.schema import Deserved, DeservedFactor, DeservedFit

WP_FULL = 0.05  # weight 1 while the offense's win chance is in [5%, 95%]
WP_ZERO = 0.01  # weight WP_FLOOR at or beyond 1% / 99%; linear between
WP_FLOOR = 0.25  # what a garbage-time snap still counts
CHANCE_YL = 40  # a scoring chance: the drive snapped at or inside the opponent's 40
DRIVE_TYPES = ["pass", "run", "field_goal", "punt"]
TOSS_UP = 0.6  # below this the meter calls it a toss-up
INT_KEEP = 0.45  # share of a game's interceptions that is the throw (FTN 2022-2025; docstring)


def garbage_weight() -> pl.Expr:
    """How much a play counts, from the offense's pre-snap win chance `wp` (null counts fully)."""
    lo = pl.min_horizontal(pl.col("wp"), 1 - pl.col("wp"))
    return (
        pl.when(pl.col("wp").is_null())
        .then(1.0)
        .when(lo >= WP_FULL)
        .then(1.0)
        .when(lo <= WP_ZERO)
        .then(WP_FLOOR)
        .otherwise(WP_FLOOR + (1 - WP_FLOOR) * (lo - WP_ZERO) / (WP_FULL - WP_ZERO))
        .alias("w")
    )


def _wmean(e: pl.Expr, cond: pl.Expr | None = None) -> pl.Expr:
    w = pl.col("w")
    if cond is not None:
        e, w = e.filter(cond), w.filter(cond)
    return pl.when(w.sum() > 0).then((e * w).sum() / w.sum()).otherwise(None)


def league_int_rate(plays: pl.DataFrame) -> float:
    """Interceptions per dropback over the offensive passes and runs of `plays`."""
    off = plays.filter(
        pl.col("play_type").is_in(["pass", "run"])
        & pl.col("epa").is_not_null()
        & (pl.col("qb_dropback").fill_null(0) == 1)
    )
    return float(off["interception"].fill_null(0).mean() or 0.0)  # type: ignore[arg-type]


def team_factors(
    plays: pl.DataFrame, lost_share: float, int_rate: float = 0.0, int_keep: float = 1.0,
    v_int: float = 1.0, v_fum: float = 1.0,
) -> pl.DataFrame:  # fmt: skip
    """One row per (game_id, posteam): the factors from that team's offensive snaps.

    `plays` needs game_id, posteam, play_type, epa, success, wp, down, qb_dropback, interception,
    fumble, fumble_lost, fixed_drive, yardline_100 (nulls allowed). Giveaways are expected points:
    interceptions (`int_keep` of their number plus the rest at `int_rate` per dropback) times
    `v_int`, plus fumbles times the lost share times `v_fum`. Team codes are compared as
    given, so pass plays already canonical or all from one printing.
    """
    df = plays.filter(pl.col("posteam").is_not_null()).with_columns(garbage_weight())
    off = df.filter(pl.col("play_type").is_in(["pass", "run"]) & pl.col("epa").is_not_null())
    ints = int_keep * pl.col("interception").fill_null(0) + (1 - int_keep) * int_rate * pl.col(
        "qb_dropback"
    ).fill_null(0)
    turnover = (pl.col("interception").fill_null(0) == 1) | (
        pl.col("fumble_lost").fill_null(0) == 1
    )
    per = off.group_by("game_id", "posteam").agg(
        _wmean(pl.col("epa"), ~turnover).alias("efficiency"),
        _wmean(pl.col("success").fill_null(0).cast(pl.Float64)).alias("success"),
        _wmean((pl.col("down") == 3).cast(pl.Float64), pl.col("down").is_not_null()).alias(
            "third_share"
        ),
        ((v_int * ints + v_fum * lost_share * pl.col("fumble").fill_null(0)) * pl.col("w"))
        .sum()
        .alias("giveaways"),
        pl.col("interception").fill_null(0).sum().alias("ints"),
        pl.col("fumble").fill_null(0).sum().alias("fumbles"),
        pl.len().alias("plays"),
        pl.col("w").sum().alias("w_plays"),
    )
    drives = (
        df.filter(pl.col("play_type").is_in(DRIVE_TYPES) & pl.col("fixed_drive").is_not_null())
        .sort("game_id", "fixed_drive", "play_id")
        .group_by("game_id", "posteam", "fixed_drive")
        .agg(
            pl.col("w").first(),
            (pl.col("yardline_100").min() <= CHANCE_YL)
            .fill_null(False)
            .cast(pl.Float64)
            .alias("c"),
        )
        .group_by("game_id", "posteam")
        .agg(
            pl.when(pl.col("w").sum() > 0)
            .then((pl.col("c") * pl.col("w")).sum() / pl.col("w").sum())
            .otherwise(None)
            .alias("chances"),
            pl.col("c").sum().alias("chance_drives"),
            pl.len().alias("drives"),
        )
    )
    return per.join(drives, on=["game_id", "posteam"], how="left")


FACTORS = ("efficiency", "chances", "giveaways")
FITTED = ("efficiency", "chances")  # giveaways are priced in points, not fitted


def game_diffs(tf: pl.DataFrame, home_of: pl.DataFrame) -> pl.DataFrame:
    """home - away per game. `home_of`: game_id, home, away (codes as in `tf`)."""
    cols = list(FACTORS)
    h = tf.select("game_id", pl.col("posteam").alias("home"), *cols)
    a = tf.select(
        "game_id", pl.col("posteam").alias("away"), *[pl.col(c).alias(f"a_{c}") for c in cols]
    )
    df = home_of.join(h, on=["game_id", "home"]).join(a, on=["game_id", "away"])
    return df.with_columns([(pl.col(c) - pl.col(f"a_{c}")).alias(f"d_{c}") for c in cols])


MIN_GAMES = 100  # fewer games with all three factors: no fit (the meter is left out)


def fit(
    plays: pl.DataFrame, games: pl.DataFrame, lost_share: float, v_int: float, v_fum: float
) -> DeservedFit | None:
    """Least squares of the margin less the giveaway points on the efficiency and scoring-chance
    differences (no intercept), then the meter's scale by a one-parameter logistic of the result
    on the deserved margin (ties out). Giveaways are priced at `v_int` (an interception) and
    `v_fum` (a lost fumble), in points, not fitted.

    `plays`: regular-season plays with the columns `team_factors` reads plus home_team,
    away_team; `games`: game_id, home_score, away_score."""
    from nfl.retro.expectations import fit_logistic

    int_rate = league_int_rate(plays)
    tf = team_factors(plays, lost_share, int_rate, INT_KEEP, v_int, v_fum)
    home_of = plays.select("game_id", pl.col("home_team").alias("home"), pl.col("away_team").alias("away")).unique("game_id")  # fmt: skip
    df = game_diffs(tf, home_of).join(games, on="game_id")
    df = df.drop_nulls([f"d_{c}" for c in FACTORS] + ["home_score", "away_score"])
    if df.height < MIN_GAMES:
        return None
    x = np.column_stack([df[f"d_{c}"].to_numpy() for c in FITTED])
    give = df["d_giveaways"].to_numpy()
    y = (df["home_score"] - df["away_score"]).cast(pl.Float64).to_numpy()
    b, *_ = np.linalg.lstsq(x, y + give, rcond=None)
    m = x @ b - give
    sigma = float(np.std(y - m))
    r2 = float(1 - ((y - m) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    nz = y != 0
    k = float(fit_logistic(m[nz][:, None], (y[nz] > 0).astype(float))[0])
    return DeservedFit(
        b_efficiency=float(b[0]), b_chances=float(b[1]), b_giveaways=-1.0, k=k,
        sigma=sigma, r2=r2, n=len(y), wp_full=WP_FULL, wp_zero=WP_ZERO, wp_floor=WP_FLOOR,
        int_rate=int_rate, int_keep=INT_KEEP, v_interception=v_int, v_fumble=v_fum,
    )  # fmt: skip


def applies_to(seasons: tuple[int, int], season: int) -> bool:
    """A fit is used only for seasons after its window (point in time, principle 2)."""
    return seasons[1] < season


def _clock(qtr: float | None, gsr: float | None) -> str | None:
    if qtr is None or gsr is None:
        return None
    q = int(qtr)
    left = int(gsr) - (4 - q) * 900 if q <= 4 else int(gsr)
    left = max(0, left)
    return f"{'OT' if q > 4 else f'Q{q}'} {left // 60}:{left % 60:02d}"


def _garbage_from(game_plays: pl.DataFrame) -> tuple[int | None, str | None, int]:
    """When garbage time began for good: the first offensive snap after which every snap counted
    less than fully. Returns (elapsed seconds, "Q4 9:57", snaps counted less than fully)."""
    off = (
        game_plays.filter(pl.col("play_type").is_in(["pass", "run"]) & pl.col("epa").is_not_null())
        .with_columns(garbage_weight())
        .sort("play_id")
    )
    if off.is_empty():
        return None, None, 0
    w = off["w"].to_list()
    partial = sum(1 for x in w if x < 1)
    i = len(w)
    while i > 0 and w[i - 1] < 1:
        i -= 1
    if i == len(w):
        return None, None, partial
    row = off.row(i, named=True)
    gsr = row.get("game_seconds_remaining")
    qtr = row.get("qtr")
    t = None if gsr is None else int(3600 - gsr) if (qtr or 0) <= 4 else None
    return t, _clock(qtr, gsr), partial


def _pct(p: float) -> str:
    """A meter value for a sentence, held inside 1-99%."""
    return f"{min(99, max(1, round(100 * p)))}%"


def _by(m: float) -> str:
    return f"{abs(m):.1f}"


LABELS = {
    "efficiency": ("Efficiency", "EPA per play, turnover plays out"),
    "chances": ("Scoring chances", "drives reaching the opponent's 40"),
    "giveaways": (
        "Giveaways",
        "points handed over: fumbles at the league's recovery odds, picks partly evened out",
    ),
}


def deserved(
    F: DeservedFit, game_plays: pl.DataFrame, g: dict, home_code: str, away_code: str,
    lost_share: float,
) -> Deserved | None:  # fmt: skip
    """The meter for one game. `home_code`/`away_code` are the codes as printed in the plays."""
    tf = team_factors(game_plays, lost_share, F.int_rate, F.int_keep, F.v_interception, F.v_fumble)
    rows = {r["posteam"]: r for r in tf.iter_rows(named=True)}
    h, a = rows.get(home_code), rows.get(away_code)
    if h is None or a is None:
        return None
    weights = {"efficiency": F.b_efficiency, "chances": F.b_chances, "giveaways": F.b_giveaways}
    factors: list[DeservedFactor] = []
    total = 0.0
    for name in FACTORS:
        hv, av = h.get(name), a.get(name)
        pts = None
        if hv is not None and av is not None:
            pts = weights[name] * (hv - av)
            total += pts
        factors.append(_factor(name, hv, av, None if pts is None else round(pts, 1)))
    p_home = 1 / (1 + math.exp(-F.k * total))
    home, away = g["home_team"], g["away_team"]
    winner = home if total >= 0 else away
    p_w = p_home if total >= 0 else 1 - p_home
    margin = g["home_score"] - g["away_score"]
    t, clock, partial = _garbage_from(game_plays)
    played = round(h["w_plays"] + a["w_plays"])
    snaps = int(h["plays"] + a["plays"])

    real = (
        f"the game was tied {g['home_score']}-{g['away_score']}"
        if margin == 0
        else f"{home if margin > 0 else away} won by {abs(margin)}"
    )
    if p_w < TOSS_UP:
        lede = f"A toss-up on the plays ({winner} {_pct(p_w)}, by {_by(total)} points); {real}."
    else:
        joint = "and" if margin != 0 and (margin > 0) == (total >= 0) else "but"
        lede = (
            f"{winner} deserved to win: {_pct(p_w)}, the plays were worth {_by(total)} points to "
            f"{winner}, {joint} {real}."
        )
    return Deserved(
        p_home=round(p_home, 4),
        winner=winner,
        margin_home=round(total, 1),
        matches_result=None if margin == 0 else (margin > 0) == (total >= 0),
        gap_home=round(margin - total, 1),
        factors=factors,
        garbage_t=t,
        garbage_clock=clock,
        snaps=snaps,
        snaps_full=snaps - partial,
        snaps_weighted=played,
        sentence=lede,
    )


def _factor(name: str, hv: float | None, av: float | None, pts: float | None) -> DeservedFactor:
    label, note = LABELS[name]
    nd = 1 if name == "giveaways" else 3
    r = lambda v: None if v is None else round(float(v), nd)
    lead = None
    if hv is not None and av is not None and round(hv, nd) != round(av, nd):
        better_high = name != "giveaways"
        lead = "home" if (hv > av) == better_high else "away"
    return DeservedFactor(
        factor=name, label=label, note=note, home=r(hv), away=r(av), pts=pts,  # type: ignore[arg-type]
        weighted=pts is not None or name in FACTORS, leader=lead,  # type: ignore[arg-type]
    )  # fmt: skip
