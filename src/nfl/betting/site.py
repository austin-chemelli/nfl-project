"""Site files for the betting guide (ADR 0033): `site/betting_math.json` (the public "Betting
math" page) and `site/betting_week.json` (the weekly card, its record and the closing lines the
bet log grades against; an unlisted page). Numbers come from `study.run()`, cached in
`marts/betting/study.json` and rerun whenever the model's backfill version changes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import polars as pl

from nfl.betting import guide, history, study
from nfl.config import Paths

STUDY_FILE = ("betting", "study.json")
MODEL = "student"  # the headline line (site.HEADLINE_ID)
MATH_SCHEMA = 1
WEEK_SCHEMA = 1


def study_path(paths: Paths):
    return paths.marts.joinpath(*STUDY_FILE)


def run_study(paths: Paths, model: str = MODEL) -> dict:
    """Run the study and store it (`nfl betting study`)."""
    out = study.run(paths, model) | {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    f = study_path(paths)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, default=str))
    tmp.replace(f)
    return out


def ensure_study(paths: Paths, model: str = MODEL) -> dict:
    """The stored study, rerun first if missing or built on another version of the models."""
    f = study_path(paths)
    current = history.model_versions(paths, tuple(dict.fromkeys((*history.APPROACHES, model))))
    stored = json.loads(f.read_text()) if f.exists() else None
    if stored and stored.get("model") == model and stored.get("model_versions") == current:
        return stored
    if stored and stored.get("failed_versions") == current:
        return stored  # this version already failed once: don't pay the rerun on every build
    try:
        return run_study(paths, model)
    except Exception:
        if stored is None:
            raise
        stored["failed_versions"] = current  # keep serving the last good study
        f.write_text(json.dumps(stored, indent=1, default=str))
        print("betting: study rerun failed; serving the stored study")
        return stored


def math_file(s: dict) -> dict:
    """The public page's numbers: the study minus internals."""
    wf = s["walk_forward"]
    return {
        "schema_version": MATH_SCHEMA,
        "generated_at": s.get("generated_at"),
        "model": s["model"],
        "model_version": s["model_versions"].get(s["model"]),
        "games": s["games"],
        "seasons": s["seasons"],
        "bands": s["price"]["bands"],
        "pick_winners": s["pick_winners"],
        "parlays": s["parlays"]["by_legs"],
        "vig_compounding": [r for r in s["vig_compounding"] if abs(r["hold"] - 0.0455) < 1e-9],
        "staking": s["staking"],
        "blend": s["blend"]["path"],
        "walk_forward": {k: wf[k] for k in ("rules_tried", "walk_forward_roi", "walk_forward_bets",
                                            "best_in_hindsight_roi", "median_rule_roi")}
        | {"seasons": [{"season": r["season"], "bets": r["bets"], "roi": r["roi"]} for r in wf["seasons"]],
           "positive_both_halves": len(wf["rules_positive_in_both_halves"])},
        "targeted": [{k: v for k, v in t.items()} for t in s["targeted"]],
        "key_margins": s["spreads_totals"]["key_margins"],
        "lands_on_3": s["spreads_totals"]["lands_on_3_when_spread_near_3"],
        "fees": s["fees"],
        "exchange_fee": s["kalshi_fee"],
        "rules": s["rules"],
    }  # fmt: skip


def _wind(feats: pl.DataFrame, now: datetime) -> dict[str, float]:
    """Latest forecast (or recorded) wind per game known at `now`."""
    if feats.is_empty():
        return {}
    w = feats.filter((pl.col("feature") == "weather.wind_mph") & pl.col("value").is_not_null())
    if "known_as_of" in w.columns:
        w = w.filter(pl.col("known_as_of").cast(pl.Datetime("us")) <= now).sort("known_as_of")
    return dict(w.group_by("game_id").last().select("game_id", "value").iter_rows())


def week_file(paths: Paths, games: pl.DataFrame, allrows: pl.DataFrame, lines: pl.DataFrame,
              feats: pl.DataFrame, week: int, now: datetime, s: dict) -> dict:  # fmt: skip
    season = int(games["season"].max())
    c = guide.card(games, allrows, lines, _wind(feats, now), s, week, now)
    return {
        "schema_version": WEEK_SCHEMA,
        "generated_at": now.isoformat() + "Z",
        "season": season,
        "rule_version": guide.RULE_VERSION,
        "model": s["model"],
        "model_version": s["model_versions"].get(s["model"]),
        "stake_pct": guide.STAKE_PCT,
        "max_targets": guide.MAX_TARGETS,
        "exchange_fee": guide.EXCHANGE_FEE,
        "card": c,
        "record": guide.live_record(paths, season, s),
        "rules": s["rules"],
        "closing": guide.closing_map(games, lines),
    }
