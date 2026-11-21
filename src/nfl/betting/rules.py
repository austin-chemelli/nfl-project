"""The betting guide's rules (ADR 0033, guide v1), shared by the study (which measures them on
history) and the card (which applies them to this week). Pure functions, no data.

Every side of every game (either team) gets one view from its price band and the gap between the
model's chance and the market's vig-free chance (in points of win chance):
- "avoid": priced -120 to -185 (the costliest common price), +185 or longer (long shots), or the
  model is LEAN_MAX+ above the market (its big disagreements lose: the market knows something
  the model doesn't, usually late news).
- "target": the model is LEAN_MIN to LEAN_MAX above the market at any other price; the strongest
  spot is an underdog at +120 to +185 ("lean_dog").
- "none": no view (the model agrees with the market, or rates the side lower): costs about the cut.
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
MAX_TARGETS = 4  # a week; underdog leans first, then the larger lean


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


def target_priority(why: str, gap: float) -> tuple[int, float]:
    """Sort key for the weekly cap: underdog leans first, then the larger lean."""
    return (0 if why == "lean_dog" else 1, -gap)


def cap_targets(items: list[dict], key) -> None:
    """Keep at most MAX_TARGETS 'target' items (in `key` order); demote the rest to 'none' with
    why 'over_cap', in place."""
    t = sorted((x for x in items if x["view"] == "target"), key=key)
    for x in t[MAX_TARGETS:]:
        x["view"], x["why"] = "none", "over_cap"
