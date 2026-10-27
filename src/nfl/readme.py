"""`nfl readme`: rewrite the scorecard section of README.md from the marts (M4.5).

Only the text between the markers is touched. Two tables: the live record (graded locks,
is_backfill=false) and the 2005–2025 backtest summary with season-bootstrap CIs. Idempotent.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from nfl.config import Paths

START = "<!-- scorecard:start -->"
END = "<!-- scorecard:end -->"
SHOW = [
    "market_baseline",
    "sharp.persona",
    "ensemble",
    "traditionalist.fitted",
    "analyst.fitted",
    "student.fitted",
    "traditionalist.persona",
    "analyst.persona",
    "elo_v0",
    "home_naive",
]
LABELS = {
    "market_baseline": "Market (vig-free moneyline)",
    "sharp.persona": "The Sharp",
    "ensemble": "Ensemble",
    "traditionalist.fitted": "The Traditionalist (fitted)",
    "analyst.fitted": "The Analyst (fitted)",
    "student.fitted": "The Student (fitted)",
    "traditionalist.persona": "The Traditionalist (persona)",
    "analyst.persona": "The Analyst (persona)",
    "elo_v0": "Elo",
    "home_naive": "Home team 57%",
}


def section(paths: Paths) -> str:
    out = [START, ""]
    graded = paths.marts / "graded.parquet"
    live = (
        pl.read_parquet(graded).filter(~pl.col("is_backfill"))
        if graded.exists()
        else pl.DataFrame()
    )
    out.append("### Live record")
    out.append("")
    if live.is_empty():
        out.append(
            "No graded live locks yet. Lock files are committed under `public/predictions/` before kickoff."
        )
    else:
        agg = live.group_by("model_id").agg(
            pl.len().alias("n"), pl.col("log_loss").mean(), pl.col("brier").mean()
        )
        out += ["| Model | Games | Log loss | Brier |", "|---|---|---|---|"]
        for mid in SHOW:
            r = agg.filter(pl.col("model_id") == mid)
            if r.height:
                out.append(
                    f"| {LABELS[mid]} | {r['n'][0]} | {r['log_loss'][0]:.4f} | {r['brier'][0]:.4f} |"
                )
        out.append("")
        out.append(
            "Lower is better. A season of live games cannot rank models; see the backtest for intervals."
        )
    out.append("")
    summ_p = paths.marts / "summary.parquet"
    if summ_p.exists():
        s = pl.read_parquet(summ_p)
        first, last = int(s["first_season"].min()), int(s["last_season"].max())
        out.append(
            f"### Backtest, {first}–{min(last, 2025)} (walk-forward: each season scored by models trained only on earlier seasons)"
        )
        out += ["", "| Model | Games | Log loss | Δ vs market (90% CI) |", "|---|---|---|---|"]
        for mid in SHOW:
            r = s.filter(pl.col("model_id") == mid)
            if not r.height:
                continue
            d = r["d_vs_market"][0]
            ci = (
                ""
                if mid == "market_baseline" or d is None
                else f"{d:+.4f} ({r['d_lo'][0]:+.4f} to {r['d_hi'][0]:+.4f})"
            )
            out.append(f"| {LABELS[mid]} | {r['n_games'][0]:,} | {r['log_loss'][0]:.4f} | {ci} |")
    out += ["", END]
    return "\n".join(out)


def update(paths: Paths, readme: Path) -> bool:
    text = readme.read_text()
    if START not in text or END not in text:
        raise ValueError(f"{readme} has no scorecard markers")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new = head + section(paths) + tail
    if new != text:
        readme.write_text(new)
        return True
    return False
