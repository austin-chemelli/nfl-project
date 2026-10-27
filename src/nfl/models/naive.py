"""Naive baseline: home team wins ~57% with a 2-point edge. The floor every model must beat."""

MODEL_ID = "home_naive"
MODEL_VERSION = "0.1"


def predict(total_line: float | None) -> dict:
    return {
        "p_home": 0.57,
        "spread_home": 2.0,
        "total": float(total_line) if total_line is not None else 44.0,
        "sd_margin": 13.5,
    }
