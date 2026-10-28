"""Pure helpers for the Slate page: picks, divergence flags, correctness, disagreement ranking."""

from __future__ import annotations

from nfl.ui import data

DIVERGE = 0.05  # |model - market| in probability at which a cell is highlighted


def pick(game: dict, mid: str) -> dict | None:
    """The side a model favors: team, its win probability, divergence from the market, p_home."""
    m = game.get("models", {}).get(mid)
    if not m or m.get("p_home") is None:
        return None
    p = m["p_home"]
    home = p >= 0.5
    return {
        "team": game["home"] if home else game["away"],
        "p": p if home else 1 - p,
        "p_home": p,
        "div": m.get("divergence"),
        "home": home,
    }


def home_won(game: dict) -> bool | None:
    r = game.get("result")
    if not r or r.get("margin") in (None, 0):
        return None
    return r["margin"] > 0


def correct(game: dict, mid: str) -> bool | None:
    pk, won = pick(game, mid), home_won(game)
    return None if pk is None or won is None else pk["home"] == won


def status(game: dict) -> tuple[str, str | None]:
    """('preview'|'locked'|'backfill', lock_ts) from the ensemble row (any model as fallback)."""
    models = game.get("models", {})
    m = models.get("ensemble") or next(iter(models.values()), None)
    return (m["status"], m.get("lock_ts")) if m else ("preview", None)


def score_text(game: dict) -> str:
    r = game.get("result")
    if not r:
        return ""
    return f"{game['away']} {r['away_score']}, {game['home']} {r['home_score']}"


def disagreements(games: list[dict], n: int = 3) -> list[dict]:
    """Top-n games by spread between the four approaches' p_home (max - min)."""
    out = []
    for g in games:
        ps = {}
        for a in data.APPROACH_ORDER:
            m = g.get("models", {}).get(a)
            if m and m.get("p_home") is not None:
                ps[a] = m["p_home"]
        if len(ps) >= 2:
            hi, lo = max(ps, key=ps.get), min(ps, key=ps.get)
            out.append({"game": g, "spread": ps[hi] - ps[lo], "hi": hi, "lo": lo, "ps": ps})
    return sorted(out, key=lambda d: -d["spread"])[:n]


def side_text(game: dict, p_home: float) -> str:
    pk_home = p_home >= 0.5
    return (
        f"{game['home'] if pk_home else game['away']} {data.pct(p_home if pk_home else 1 - p_home)}"
    )
