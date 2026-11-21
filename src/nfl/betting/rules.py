"""The betting guide's rules (ADR 0033, guide v1), shared by the study (which measures them on
history) and the card (which applies them to this week). Pure functions, no data.

Every side of every game (either team) is placed in a cell: its price band x where the model
stands against the market's vig-free chance (below, same, lean, big; GAP_CELLS). Then:
- "avoid": priced -120 to -185 (the costliest common price), +185 or longer (long shots), or the
  model is LEAN_MAX+ above the market (its big disagreements lose: the market knows something
  the model doesn't, usually late news).
- "target": the week's MAX_TARGETS best of the rest that the model backs (at or above the
  market: cells same and lean), ranked by their cell's return since 2006
  (shrunk toward the average by SHRINK_K bets, so a small cell can't top the list on luck).
  There is always a list; the grade says how good the history behind each one is.
- "none": everything else.
"""

from __future__ import annotations

# price bands on the vig-free chance, with the American prices they correspond to
BANDS = [
    (0.80, 1.01, "heavy_fav", "Heavy favorite", "-400 or shorter"),
    (0.65, 0.80, "big_fav", "Big favorite", "-185 to -400"),
    (0.55, 0.65, "fav", "Favorite", "-120 to -185"),
    (0.45, 0.55, "coin", "Coin flip", "-120 to +120"),
    (0.35, 0.45, "dog", "Underdog", "+120 to +185"),
    (0.20, 0.35, "big_dog", "Big underdog", "+185 to +400"),
    (0.00, 0.20, "long", "Long shot", "+400 or longer"),
]
BANDS_ORDER = [b[2] for b in BANDS]

LEAN_MIN = 0.02  # the model at least 2 points above the market...
LEAN_MAX = 0.06  # ...and less than 6 (beyond that the market has been right)
AVOID_BANDS = ("fav", "big_dog", "long")
MAX_TARGETS = 5  # a week, ranked by their cell's history
SHRINK_K = 200  # bets of the overall average mixed into each cell's return
GRADES = ((0.02, "A"), (-0.01, "B"))  # shrunk cell return at least this -> grade; else "C"


def band_of(p: float) -> str:
    for lo, hi, key, *_ in BANDS:
        if lo <= p < hi:
            return key
    return BANDS[0][2]


def side_view(p_model: float, p_market: float) -> tuple[str, str]:
    """(view, why) for one side: view 'target' | 'avoid' | 'none'; why one of 'lean_dog', 'lean',
    'mid_fav', 'long', 'big_gap', 'no_view'. The price band decides first, then the gap."""
    band = band_of(p_market)
    gap = p_model - p_market
    if band == "fav":
        return "avoid", "mid_fav"
    if band in ("big_dog", "long"):
        return "avoid", "long"
    if gap >= LEAN_MAX:
        return "avoid", "big_gap"
    if gap >= LEAN_MIN:
        return "target", "lean_dog" if band == "dog" else "lean"
    return "none", "no_view"


def cell_of(gap: float) -> str:
    """Where the model stands against the market, for the history cells."""
    if gap < -LEAN_MIN:
        return "below"
    if gap < LEAN_MIN:
        return "same"
    if gap < LEAN_MAX:
        return "lean"
    return "big"


def grade(score: float | None) -> str:
    if score is None:
        return "C"
    for lo, g in GRADES:
        if score >= lo:
            return g
    return "C"


ELIGIBLE_CELLS = ("same", "lean")  # a target is a side the model backs: at or above the market


def pick_targets(items: list[dict], key) -> None:
    """Rank every eligible item (not avoid, the model at or above the market) by `key` (best
    first) and make the top MAX_TARGETS 'target', every other non-avoid 'none', in place. Items
    carry 'view' (from side_view) and 'cell'."""
    for x in items:
        if x["view"] != "avoid":
            x["view"] = "none"
    ok = sorted((x for x in items if x["view"] != "avoid" and x["cell"] in ELIGIBLE_CELLS), key=key)
    for x in ok[:MAX_TARGETS]:
        x["view"] = "target"
