"""Market baseline: the closing line is the forecast. Every other model is measured against this.

v0.2 (2026-10-27): p_home is the vig-free moneyline probability when both moneylines exist, else
Φ(spread / 13.5). v0.1 used Φ(spread / 13.5) only, which is miscalibrated by ~0.0015 log loss; a
calibrated persona leaning on the spread "beat the market" by exactly that amount. The moneyline
is what the market itself prices, so it is the fair reference.
"""

from __future__ import annotations

from math import erf, sqrt

MODEL_ID = "market_baseline"
MODEL_VERSION = "0.2"
SD_MARGIN = 13.5  # historical sd of NFL margin around the spread


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _implied(odds: float) -> float:
    return -odds / (-odds + 100.0) if odds < 0 else 100.0 / (odds + 100.0)


def predict(
    spread_line: float | None,
    total_line: float | None,
    home_ml: float | None = None,
    away_ml: float | None = None,
) -> dict | None:
    """spread_line follows nflverse convention: positive = home favored by that many points."""
    if spread_line is None:
        return None
    if home_ml and away_ml:
        ph, pa = _implied(home_ml), _implied(away_ml)
        p = ph / (ph + pa)
    else:
        p = norm_cdf(spread_line / SD_MARGIN)
    return {
        "p_home": p,
        "spread_home": float(spread_line),
        "total": float(total_line) if total_line is not None else None,
        "sd_margin": SD_MARGIN,
    }
