"""Shared UI helpers: loaders for the site JSON contract (nfl.site), labels, palette, formatting.

Pages import from here and read only marts/site/*.json (never parquet), the same files the React
site will read. Palette = the dataviz reference instance (validated categorical order, light and
dark steps); color follows the approach, never its rank; persona flavors use the same hue dashed;
reference lines are neutral gray.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from nfl.config import get_paths

ET = ZoneInfo("America/New_York")
SITE: Path = get_paths().site

# categorical slots 1-5 in the validated order (blue, orange, aqua, yellow, magenta)
_LIGHT = {"analyst": "#2a78d6", "traditionalist": "#eb6834", "sharp": "#1baf7a",
          "student": "#eda100", "ensemble": "#e87ba4"}  # fmt: skip
_DARK = {"analyst": "#3987e5", "traditionalist": "#d95926", "sharp": "#199e70",
         "student": "#c98500", "ensemble": "#d55181"}  # fmt: skip
NEUTRAL = {"light": {"market": "#52514e", "ref": "#8a8984", "grid": "#e4e3df", "mid": "#f0efec"},
           "dark": {"market": "#c3c2b7", "ref": "#8a8984", "grid": "#383835", "mid": "#383835"}}  # fmt: skip
DIVERGING = {"neg": "#e34948", "mid_light": "#f0efec", "mid_dark": "#383835", "pos": "#2a78d6"}
APPROACH_ORDER = ["traditionalist", "analyst", "sharp", "student"]
SITE_MISSING = "No site data yet. Run `uv run nfl site` (after `nfl grade`)."


def theme() -> str:
    t = getattr(getattr(st.context, "theme", None), "type", None)
    return "dark" if t == "dark" else "light"


def color(model_id: str) -> str:
    """Hue for a model: approach hue for persona/fitted, magenta for ensemble, gray for references."""
    pal = _DARK if theme() == "dark" else _LIGHT
    base = model_id.split(".", 1)[0]
    if base in pal:
        return pal[base]
    if model_id == "market_baseline":
        return NEUTRAL[theme()]["market"]
    return NEUTRAL[theme()]["ref"]


def dash(model_id: str) -> str:
    """Line style: approaches solid, reference lines dotted (one line per approach, contract v2)."""
    return "dot" if model_id in ("elo_v0", "home_naive", "global") else "solid"


@st.cache_data(show_spinner=False, ttl=60)
def _load(name: str):
    f = SITE / name
    return json.loads(f.read_text()) if f.exists() else None


def meta() -> dict | None:
    return _load("meta.json")


def slate(season: int, week: int) -> dict | None:
    return _load(f"slate_{season}_{week:02d}.json")


def game(game_id: str) -> dict | None:
    return _load(f"game/{game_id}.json")


def tracker() -> dict | None:
    return _load("tracker.json")


def audit() -> dict | None:
    return _load("audit.json")


def hypotheses() -> dict | None:
    return _load("hypotheses.json")


def label(model_id: str) -> str:
    m = meta() or {}
    return m.get("models", {}).get(model_id, {}).get("label", model_id)


def approaches() -> list[dict]:
    m = meta() or {}
    by = {a["id"]: a for a in m.get("approaches", [])}
    return [by[a] for a in APPROACH_ORDER if a in by]


def groups() -> list[dict]:
    m = meta() or {}
    return m.get("groups", {}).get("groups", [])


def pct(p: float | None, nd: int = 0) -> str:
    return "–" if p is None else f"{100 * p:.{nd}f}%"


def spread(s: float | None, home: str, away: str) -> str:
    """Book-style line from the home spread (+ = home favored): 'BUF −3.5'."""
    if s is None:
        return "–"
    if abs(s) < 0.25:
        return "pick'em"
    team = home if s > 0 else away
    return f"{team} −{abs(s):g}"


def kickoff_et(ts: str | None) -> str:
    if not ts:
        return "–"
    k = datetime.fromisoformat(ts).astimezone(ET)
    return k.strftime("%a %b %-d, %-I:%M %p ET")


def require(obj, msg: str = SITE_MISSING):
    if obj is None:
        st.info(msg)
        st.stop()
    return obj


# ------------------------------------------------------------------ contract v2: labels, help, units


def member(feature: str) -> dict:
    """Registry entry for a feature: label, description, unit, group, sign (empty dict if unknown)."""
    for g in groups():
        for m in g.get("members", []):
            if m["feature"] == feature:
                return m | {"group": g["id"], "group_name": g["name"]}
    return {}


def group(gid: str) -> dict:
    for g in groups():
        if g["id"] == gid:
            return g
    return {"id": gid, "name": gid.replace("_", " ").title(), "description": ""}


def help_text(feature_or_group: str) -> str:
    """Hover help for a feature or a group id (use as `help=` on Streamlit widgets/metrics)."""
    m = member(feature_or_group)
    if m:
        return m["description"]
    return group(feature_or_group).get("description", "")


def fmt(value: float | None, unit: str | None) -> str:
    """Format a raw feature value by its registry unit (never log-odds)."""
    if value is None:
        return "–"
    v = float(value)
    match unit:
        case "pct":
            return f"{100 * v:.0f}%"
        case "pp":
            return f"{v:+.1f} pts"
        case "prob_diff":
            return f"{100 * v:+.1f} pts"
        case "points":
            return f"{v:+.1f}"
        case "rating":
            return f"{v:.0f}"
        case "epa":
            return f"{v:+.3f}"
        case "days" | "count" | "seasons":
            return f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}"
        case "km":
            return f"{v:,.0f} km"
        case "hours":
            return f"{v:+.0f} h"
        case "seconds":
            return f"{v:.2f} s"
        case "yards":
            return f"{v:.0f} yds"
        case "flag":
            return "yes" if v >= 0.5 else "no"
        case _:
            return f"{v:.2f}"


def pp(x: float | None) -> str:
    """Win-probability points with a sign: '+3.9 pts'."""
    return "–" if x is None else f"{x:+.1f} pts"
