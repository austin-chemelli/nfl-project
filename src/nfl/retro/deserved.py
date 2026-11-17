"""Deserved to win (ADR 0016 amendment 2026-11-17): who the plays said should have won.

The old "played like" rested on one input, EPA per play with turnover plays dropped, counted over
the whole game. It read MIN's 30-10 win at GB (2026 week 10) as 58% MIN: GB's passes while down
17-20 in the second half counted in full, GB's three turnovers (two lost fumbles) counted not at
all, and home field moved the answer 9 points toward GB.

The meter is a margin in points built from three factors, each measured on the plays that still
mattered, and turned into a win chance:

    deserved margin (home - away) = b_eff * d_efficiency + b_chance * d_chances + b_give * d_giveaways
    deserved to win (home)        = 1 / (1 + exp(-k * deserved margin))

- **Garbage time.** Every play is weighted by how much the game was still in doubt, from
  nflfastR's win probability for the offense before the snap (`wp`, the model without the
  spread): weight 1 while it is between 5% and 95%, falling linearly to 0 at 1% and 99%. A
  play with no `wp` counts fully. Tested on 2015-2025 against no weighting and stricter rules
  (10/90 hard, 15/85): this one fit the result and the rest of the season best.
- **Efficiency**: weighted EPA per play over the offense's passes and runs, interceptions and
  lost fumbles left out (they are the third factor).
- **Scoring chances**: the weighted share of drives that reached the opponent's 40 (a pass, run,
  field goal or punt snapped there), each drive weighted by its first snap.
- **Giveaways, bounces evened out**: weighted interceptions plus fumbles times the league's lost
  share, so who fell on the ball doesn't count, but putting it on the ground does.
- **Context, not weighted**: success rate and the share of snaps that were third downs. On
  2015-2025 games neither adds to the margin once efficiency and scoring chances are in (success
  rate's weight is about zero; third-down share's sign flips with the set). Over a season, though,
  fewer third downs goes with a better offense (team-season r = -0.80 with EPA per play).

Weights are a least-squares fit of the final margin on the three differences, no intercept, so
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
WP_ZERO = 0.01  # weight 0 at or beyond 1% / 99%; linear between
CHANCE_YL = 40  # a scoring chance: the drive snapped at or inside the opponent's 40
DRIVE_TYPES = ["pass", "run", "field_goal", "punt"]
TOSS_UP = 0.6  # below this the meter calls it a toss-up


def garbage_weight() -> pl.Expr:
    """How much a play counts, from the offense's pre-snap win chance `wp` (null counts fully)."""
    lo = pl.min_horizontal(pl.col("wp"), 1 - pl.col("wp"))
    return (
        pl.when(pl.col("wp").is_null())
        .then(1.0)
        .when(lo >= WP_FULL)
        .then(1.0)
        .when(lo <= WP_ZERO)
        .then(0.0)
        .otherwise((lo - WP_ZERO) / (WP_FULL - WP_ZERO))
        .alias("w")
    )


def _wmean(e: pl.Expr, cond: pl.Expr | None = None) -> pl.Expr:
    w = pl.col("w")
    if cond is not None:
        e, w = e.filter(cond), w.filter(cond)
    return pl.when(w.sum() > 0).then((e * w).sum() / w.sum()).otherwise(None)


def team_factors(plays: pl.DataFrame, lost_share: float) -> pl.DataFrame:
    """One row per (game_id, posteam): the factors from that team's offensive snaps.

    `plays` needs game_id, posteam, play_type, epa, success, wp, down, interception, fumble,
    fumble_lost, fixed_drive, yardline_100 (nulls allowed). Team codes are compared as given, so
    pass plays already canonical or all from one printing.
    """
    df = plays.filter(pl.col("posteam").is_not_null()).with_columns(garbage_weight())
    off = df.filter(pl.col("play_type").is_in(["pass", "run"]) & pl.col("epa").is_not_null())
    turnover = (pl.col("interception").fill_null(0) == 1) | (
        pl.col("fumble_lost").fill_null(0) == 1
    )
    per = off.group_by("game_id", "posteam").agg(
        _wmean(pl.col("epa"), ~turnover).alias("efficiency"),
        _wmean(pl.col("success").fill_null(0).cast(pl.Float64)).alias("success"),
        _wmean((pl.col("down") == 3).cast(pl.Float64), pl.col("down").is_not_null()).alias(
            "third_share"
        ),
        (
            (pl.col("interception").fill_null(0) + lost_share * pl.col("fumble").fill_null(0))
            * pl.col("w")
        )
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


def fit(plays: pl.DataFrame, games: pl.DataFrame, lost_share: float) -> DeservedFit | None:
    """Least squares of the margin on the three differences (no intercept), then the meter's
    scale by a one-parameter logistic of the result on the fitted margin (ties out).

    `plays`: regular-season plays with the columns `team_factors` reads plus home_team,
    away_team; `games`: game_id, home_score, away_score."""
    from nfl.retro.expectations import fit_logistic

    tf = team_factors(plays, lost_share)
    home_of = plays.select("game_id", pl.col("home_team").alias("home"), pl.col("away_team").alias("away")).unique("game_id")  # fmt: skip
    df = game_diffs(tf, home_of).join(games, on="game_id")
    df = df.drop_nulls([f"d_{c}" for c in FACTORS] + ["home_score", "away_score"])
    if df.height < MIN_GAMES:
        return None
    x = np.column_stack([df[f"d_{c}"].to_numpy() for c in FACTORS])
    y = (df["home_score"] - df["away_score"]).cast(pl.Float64).to_numpy()
    b, *_ = np.linalg.lstsq(x, y, rcond=None)
    m = x @ b
    sigma = float(np.std(y - m))
    r2 = float(1 - ((y - m) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    nz = y != 0
    k = float(fit_logistic(m[nz][:, None], (y[nz] > 0).astype(float))[0])
    return DeservedFit(
        b_efficiency=float(b[0]), b_chances=float(b[1]), b_giveaways=float(b[2]), k=k,
        sigma=sigma, r2=r2, n=len(y), wp_full=WP_FULL, wp_zero=WP_ZERO,
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
    "giveaways": ("Giveaways", "interceptions, plus fumbles at the league's recovery odds"),
    "success": ("Success rate", "plays that improved the scoring outlook"),
    "third_share": ("Third downs faced", "share of snaps that were third downs"),
}


def deserved(
    F: DeservedFit, game_plays: pl.DataFrame, g: dict, home_code: str, away_code: str,
    lost_share: float,
) -> Deserved | None:  # fmt: skip
    """The meter for one game. `home_code`/`away_code` are the codes as printed in the plays."""
    tf = team_factors(game_plays, lost_share)
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
    for name in ("success", "third_share"):
        factors.append(_factor(name, h.get(name), a.get(name), None))
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
    nd = 2 if name == "giveaways" else 3
    r = lambda v: None if v is None else round(float(v), nd)
    lead = None
    if hv is not None and av is not None and round(hv, nd) != round(av, nd):
        better_high = name not in ("giveaways", "third_share")
        lead = "home" if (hv > av) == better_high else "away"
    return DeservedFactor(
        factor=name, label=label, note=note, home=r(hv), away=r(av), pts=pts,  # type: ignore[arg-type]
        weighted=pts is not None or name in FACTORS, leader=lead,  # type: ignore[arg-type]
    )  # fmt: skip
