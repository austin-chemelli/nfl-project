"""Plot and table helpers shared by the tracker and method pages (Plotly styling, table views)."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nfl.ui import data


def text_color() -> str:
    return data.NEUTRAL[data.theme()]["market"]


def style(fig: go.Figure, height: int = 380, xtitle: str | None = None, ytitle: str | None = None):
    """Transparent background, text and grid in neutral tokens, one y-axis, legend on top."""
    tc, grid = text_color(), data.NEUTRAL[data.theme()]["grid"]
    fig.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": tc, "size": 13},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        hoverlabel={"font_size": 13},
    )
    fig.update_xaxes(gridcolor=grid, zerolinecolor=grid, title=xtitle, linecolor=grid)
    fig.update_yaxes(gridcolor=grid, zerolinecolor=grid, title=ytitle, linecolor=grid)
    return fig


def line(model_id: str, **kw) -> dict:
    """Scatter line kwargs for a model: approach hue, persona dashed, 2px."""
    return {"line": {"color": data.color(model_id), "dash": data.dash(model_id), "width": 2}, **kw}


def table_view(df: pd.DataFrame, label: str = "Table view") -> None:
    with st.expander(label):
        st.dataframe(df, width="stretch", hide_index=True)


def humanize_age(snapshot: str | None, now: datetime | None = None) -> str:
    """'20261027T224658Z' -> '3 hours ago' (relative to now, UTC)."""
    if not snapshot:
        return "–"
    try:
        ts = datetime.strptime(snapshot, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return snapshot
    s = int(((now or datetime.now(UTC)) - ts).total_seconds())
    if s < 90:
        return "just now"
    for unit, n in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= n:
            v = s // n
            return f"{v} {unit}{'s' if v != 1 else ''} ago"
    return "just now"


NOISE = 0.005  # log-loss differences below this are indistinguishable at these sample sizes
BUCKET_WORDS = {
    "0-2.5": "by less than 2.5 points",
    "2.5-5": "by 2.5 to 5 points",
    "5-10": "by 5 to 10 points",
    "10+": "by 10+ points",
}


def short_name(name: str) -> str:
    """'The Traditionalist' -> 'the Traditionalist' for mid-sentence use."""
    return name[0].lower() + name[1:] if name.startswith("The ") else name


def ll_vs_market(ll: float | None, market: float | None) -> str:
    """Log loss in plain words, always next to the market's."""
    if ll is None:
        return "–"
    if market is None:
        return f"{ll:.3f}"
    d = ll - market
    if abs(d) < NOISE:
        gap = "about the same as the market"
    else:
        gap = f"about {abs(d):.3f} {'worse' if d > 0 else 'better'} than the market"
    return (
        f"{ll:.3f}, {gap} ({market:.3f}); differences under {NOISE} are noise at this sample size"
    )


def fold_reliability(rows: list[dict]) -> list[dict]:
    """Re-express home-win bins as 'the favorite side': predicted >= 50% vs how often it won.

    Mirrored bins (e.g. 25% home and 75% home) are pooled, so "a team given 75%" is one point.
    Returns [{'mean_p','hit_rate','n'}] sorted by mean_p.
    """
    pooled: dict[int, list[float]] = {}
    for r in rows:
        p, h, n = float(r["mean_p"]), float(r["hit_rate"]), int(r["n"])
        if p < 0.5:
            p, h = 1 - p, 1 - h
        k = round(p * 10) if p < 0.95 else 10  # tenth-wide cells: 5=50-55 ... 9=85-95
        c = pooled.setdefault(k, [0.0, 0.0, 0])
        c[0] += p * n
        c[1] += h * n
        c[2] += n
    return [
        {"mean_p": c[0] / c[2], "hit_rate": c[1] / c[2], "n": int(c[2])}
        for _, c in sorted(pooled.items())
        if c[2]
    ]


def calibration_verdict(rows: list[dict], name: str) -> str:
    """One line: well calibrated, or the gap on its ~70% calls (60-80% window, both sides pooled)."""
    pts = [r for r in fold_reliability(rows) if 0.6 <= r["mean_p"] < 0.8]
    n = sum(r["n"] for r in pts)
    if n < 50:
        return f"{name}: too few 60-80% calls to judge."
    p = sum(r["mean_p"] * r["n"] for r in pts) / n
    h = sum(r["hit_rate"] * r["n"] for r in pts) / n
    gap = h - p
    calls = f"its {100 * p:.0f}% calls won {100 * h:.0f}% (n = {n:,})"
    if gap < -0.03:
        return f"{name}: overconfident, {calls}."
    if gap > 0.03:
        return f"{name}: underconfident, {calls}."
    return f"{name}: well calibrated, {calls}."


def divergence_sentence(row: dict, name: str) -> str:
    """'In 1,158 games where X disagreed with the market by 10+ points, its side won 40%...'"""
    words = BUCKET_WORDS.get(row["bucket"], f"by {row['bucket']} points")
    return (
        f"In {int(row['n']):,} games where {name} disagreed with the market {words}, its side "
        f"won {100 * row['lean_win_rate']:.0f}% of the time; the market expected "
        f"{100 * row['market_expected_rate']:.0f}%."
    )


def market_wins_when_apart(rows: list[dict]) -> tuple[int, int]:
    """(# approach-buckets where the market scored better, # checked) over the 5+ point buckets."""
    big = [r for r in rows if r["bucket"] in ("5-10", "10+")]
    wins = sum(1 for r in big if r["market_log_loss"] < r["model_log_loss"])
    return wins, len(big)


def persona_history_headline(a: dict, names: dict[str, str] | None = None) -> str:
    """'History would move 8.7 of the Traditionalist's 100 attention points; the biggest gap: Form, 15 vs 6'."""
    name = short_name(a["name"])
    shift = a.get("history_shifted_points")
    P, H = a.get("persona_share", {}), a.get("history_share", {})
    gaps = {k: abs(P.get(k, 0) - H.get(k, 0)) for k in set(P) | set(H)}
    out = ""
    if shift is not None:
        out = f"History would move {shift:.0f} of {name}'s 100 attention points"
    if gaps:
        k = max(gaps, key=gaps.__getitem__)
        label = (names or {}).get(k, k.replace("_", " ").title())
        gap = f"the biggest gap: {label}, {P.get(k, 0):.0f} vs {H.get(k, 0):.0f}"
        out = f"{out}; {gap}" if out else gap
    return out + "." if out else ""


def calibration_scale_sentence(scale: float | None) -> str:
    """a < 1 -> 'about X% more confident than history supports', X = (1/a - 1) * 100."""
    if not scale:
        return ""
    if scale < 0.98:
        return f"Its raw probabilities were about {100 * (1 / scale - 1):.0f}% more confident than history supports, so they are shrunk before scoring."
    if scale > 1.02:
        return f"Its raw probabilities were about {100 * (1 - 1 / scale):.0f}% less confident than history supports, so they are stretched before scoring."
    return "Its confidence already matches history, so no rescaling was needed."
