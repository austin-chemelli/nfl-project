"""M20.9 (ADR 0024): is the mapped spread good enough to show beside the win chance?

Each approach's spread is Φ⁻¹(p_home) × 13.5, the same mapping the market reference uses. For every
backfill game 2009–2025 with a closing spread and a result, the mean absolute error of each approach's
spread against the final margin, beside the closing spread's own. If the headline line's gap to the
market exceeds a point, a margin model earns its own task.

    uv run python scripts/spread_check.py
"""

from __future__ import annotations

import polars as pl

from nfl.config import get_paths
from nfl.features import store

LINES = ("traditionalist", "analyst", "sharp", "student", "global")


def main() -> None:
    p = get_paths()
    pred = pl.read_parquet(p.marts / "predictions.parquet").filter(
        pl.col("is_backfill")
        & pl.col("season").is_between(2009, 2025)
        & pl.col("model_id").is_in(LINES)
    )
    games = (
        store.games_frame(p, min_season=2009)
        .filter(pl.col("result").is_not_null() & pl.col("spread_line").is_not_null())
        .select("game_id", "result", "spread_line")
    )
    d = pred.join(games, on="game_id").filter(pl.col("spread_home").is_not_null())
    market = games.filter(pl.col("game_id").is_in(d["game_id"].unique().to_list()))
    m_mae = (market["result"] - market["spread_line"]).abs().mean()
    print(f"games: {market.height}; closing spread MAE vs margin: {m_mae:.2f}")
    for m in LINES:
        x = d.filter(pl.col("model_id") == m)
        if x.is_empty():
            continue
        mae = (x["result"] - x["spread_home"]).abs().mean()
        print(
            f"{m:15s} spread MAE {mae:.2f}  ({mae - m_mae:+.2f} vs the closing spread, n {x.height})"
        )


if __name__ == "__main__":
    main()
