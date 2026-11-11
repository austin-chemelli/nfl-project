"""`nfl site`: the JSON contract every UI page reads (M5.1, architecture §3.7).

Streamlit (P1) and the React site (P2) read only these files, never parquet, so the contract is the
product boundary. Everything lands in marts/site/:

  meta.json                  schema version, generation time, data freshness, model registry
                             (labels, kinds), approaches (blurb, persona + fitted group weights),
                             the group registry
  slate_<season>_<ww>.json   one week: per game the market and every model's p_home / spread with a
                             status: 'locked' (a real lock before kickoff), 'backfill' (completed
                             game, frozen fits, synthetic lock), 'preview' (upcoming, scored now,
                             not a lock), or 'pregame' (kicked off with no lock or backfill yet:
                             scored as of an hour before kickoff, not part of the live record)
  game/<game_id>.json        one game: the slate row plus per-model contributions by group and
                             feature, home/away feature values, tendencies, injuries, narrative
  tracker.json               seasons scorecard, current-season cumulative log loss by week, backtest
                             summary with CIs, reliability bins, divergence buckets, ledger, weeks
                             tracked live
  audit.json                 data freshness and null-rate audit
  teams.json                 every team's latest value, percentile and rank per team-level feature,
                             record and games (ADR 0019; nfl.league.teams)

Numbers are rounded for display (4 decimals for probabilities); parquet keeps full precision.

Contract v2 (2026-10-27, `.notes/ui-feedback.md`): one model per approach (`<approach>`, ADR 0004
amendment); no log-odds anywhere: contributions are **points of win probability** (pp, how much the
home win probability would drop without that piece, so they add up only approximately); a team's
**edge** in a group is a percentile of all matchups 2005–2025; persona weights are **shares of a
100-point attention budget**; every feature and group ships a label, description and unit in
meta.json for hover help and formatting.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from nfl import market_books
from nfl.config import Paths, current_season, now_utc
from nfl.features import store
from nfl.features.groups import FEATURE_GROUP, GROUPS, HEADINGS, REGISTRY_VERSION
from nfl.league.teams import team_latest, teams_file

RETRO_PUBLISH_SEASONS = {2026}  # retros are published for these seasons only (ADR 0016)
SCHEMA_VERSION = "2"  # v2 2026-10-27: one line per approach; no log-odds; descriptions + units
PREVIEW = "preview"
LOCKED = "locked"
BACKFILL = "backfill"
PREGAME = "pregame"
PREGAME_LEAD = timedelta(hours=1)  # same offset as a synthetic backfill lock

REFERENCE = {"market_baseline": "Market", "elo_v0": "Elo", "home_naive": "Home team 57%"}
SPECIAL = {"ensemble": "Ensemble", "global": "Global fit (all features)"}
TENDENCY_SITUATIONS = ["all", "early_down", "third_down", "red_zone"]
FEATURE_BAND_MIN_TEAMS = 20  # below this a percentile of team values says little

# Labels for the tendency metrics (contract v2.1, 2026-10-28; previously hard-coded in the Streamlit
# page). `pair` links an offense metric to the defense metric it faces, for side-by-side charts.
TENDENCY_METRICS: dict[str, dict] = {
    "pass_rate": {"side": "off", "label": "Pass rate", "unit": "pct", "pair": "pass_rate_faced",
                  "help": "Share of plays that are passes (including sacks and scrambles)."},
    "pass_rate_faced": {"side": "def", "label": "Pass rate faced", "unit": "pct", "pair": "pass_rate",
                        "help": "Share of opponent plays that are passes."},
    "success_rate": {"side": "off", "label": "Success rate", "unit": "pct", "pair": "success_rate_allowed",
                     "help": "Share of plays that improve the scoring outlook (EPA above zero)."},
    "success_rate_allowed": {"side": "def", "label": "Success rate allowed", "unit": "pct", "pair": "success_rate",
                             "help": "Share of opponent plays that improve their scoring outlook; lower is better."},
    "epa_per_play": {"side": "off", "label": "EPA per play", "unit": "epa", "pair": "epa_per_play_allowed",
                     "help": "Expected points added per play; around 0 is average."},
    "epa_per_play_allowed": {"side": "def", "label": "EPA allowed per play", "unit": "epa", "pair": "epa_per_play",
                             "help": "Expected points the defense allows per play; lower is better."},
    "motion_rate": {"side": "off", "label": "Pre-snap motion", "unit": "pct", "pair": None,
                    "help": "Share of plays with a player in motion before the snap (FTN charting)."},
    "play_action_rate": {"side": "off", "label": "Play-action", "unit": "pct", "pair": None,
                         "help": "Share of passes with a play-action fake (FTN charting)."},
    "rpo_rate": {"side": "off", "label": "RPO rate", "unit": "pct", "pair": None,
                 "help": "Share of plays that are run-pass options (FTN charting)."},
    "screen_rate": {"side": "off", "label": "Screen rate", "unit": "pct", "pair": None,
                    "help": "Share of passes that are screens (FTN charting)."},
    "shotgun_rate": {"side": "off", "label": "Shotgun rate", "unit": "pct", "pair": None,
                     "help": "Share of plays with the QB in shotgun."},
    "under_center_rate": {"side": "off", "label": "Under center", "unit": "pct", "pair": None,
                          "help": "Share of plays with the QB under center (FTN charting)."},
    "no_huddle_rate": {"side": "off", "label": "No-huddle rate", "unit": "pct", "pair": None,
                       "help": "Share of plays run without a huddle."},
    "fourth_down_go_rate": {"side": "off", "label": "4th-down go rate", "unit": "pct", "pair": None,
                            "help": "Share of 4th downs the offense goes for it rather than punting or kicking."},
    "blitz_rate": {"side": "def", "label": "Blitz rate", "unit": "pct", "pair": None,
                   "help": "Share of opponent dropbacks with at least one blitzer (FTN charting)."},
    "pass_rushers_5plus_rate": {"side": "def", "label": "5+ pass rushers", "unit": "pct", "pair": None,
                                "help": "Share of opponent dropbacks with five or more rushers (FTN charting)."},
    "box_8plus_vs_run_rate": {"side": "def", "label": "8+ in the box vs runs", "unit": "pct", "pair": None,
                              "help": "Share of opponent runs faced with 8 or more defenders in the box."},
    "box_6minus_vs_run_rate": {"side": "def", "label": "Light box vs runs", "unit": "pct", "pair": None,
                               "help": "Share of opponent runs faced with 6 or fewer defenders in the box."},
}  # fmt: skip
TENDENCY_SITUATION_LABELS = {
    "all": "All plays", "early_down": "Early downs", "third_down": "Third down", "red_zone": "Red zone",
}  # fmt: skip


# ---------------------------------------------------------------------------------------- helpers


def _r(x, nd: int = 4):
    if x is None:
        return None
    try:
        return round(float(x), nd)
    except TypeError, ValueError:
        return x


def _ts(x: datetime | None) -> str | None:
    return None if x is None else x.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kw = {"separators": (",", ":")} if compact else {"indent": 1}
    path.write_text(json.dumps(obj, default=str, **kw))


def _read(paths: Paths, name: str) -> pl.DataFrame:
    f = paths.marts / f"{name}.parquet"
    return pl.read_parquet(f) if f.exists() else pl.DataFrame()


# --------------------------------------------------------------------------------------- registry


def model_registry() -> dict[str, dict]:
    from nfl.approaches.schema import load_all

    reg = {mid: {"label": lab, "kind": "reference"} for mid, lab in REFERENCE.items()}
    reg |= {mid: {"label": lab, "kind": mid} for mid, lab in SPECIAL.items()}
    for a in load_all().values():
        if a.id == "narrative":
            continue
        reg[a.id] = {"label": a.name, "kind": "approach", "approach": a.id}
    return reg


def _shares(W: dict[str, float]) -> dict[str, float]:
    """Signed share (%) of a 100-point attention budget."""
    tot = sum(abs(v) for v in W.values())
    return {g: _r(100 * v / tot, 1) for g, v in W.items()} if tot else {}


def _shifted(persona: dict, public: dict) -> float | None:
    """Attention points (of 100) that light fitting moved between groups: Σ|public − persona| / 2."""
    P, L = _shares(persona), _shares(public)
    if not (P and L):
        return None
    return _r(sum(abs((L.get(g) or 0) - (P.get(g) or 0)) for g in set(P) | set(L)) / 2, 1)


def approaches_meta(paths: Paths, season: int) -> list[dict]:
    """Per approach: blurb, attention budget (persona), the public line's budget after light fitting,
    what history alone would choose, and how confident the persona is relative to history."""
    from nfl.approaches import fit
    from nfl.approaches.schema import load_all

    out = []
    for a in load_all().values():
        if a.id == "narrative":
            continue
        persona = {g: w.w for g, w in a.groups.items()}
        public, history, confidence = {}, {}, None
        try:
            pub = fit.load(paths, a.id, season - 1)
            hist = fit.load(paths, f"{a.id}.fitted", season - 1)
            public = pub.meta.get("group_weights", {})
            history = hist.meta.get("group_weights", {})
            # Platt slope a on the public line: a < 1 means the persona's raw confidence is too high
            confidence = _r(pub.calib_a, 3)
        except FileNotFoundError:
            pass
        out.append(
            {
                "id": a.id,
                "name": a.name,
                "blurb": a.blurb,
                "emphasis": a.emphasis,
                "public_line": a.public,
                "home_field_why": a.intercept.why,
                "why": {g: w.why for g, w in a.groups.items()},
                "persona_share": _shares(persona),
                "history_shifted_points": _shifted(persona, public),
                "public_share": _shares(public),
                "history_share": _shares(history),
                "overrides": a.overrides,
                "calibration_scale": confidence,
                "trained_through": season - 1,
            }
        )
    return out


def groups_meta() -> dict:
    from nfl.features.groups import UNITS

    return {
        "registry_version": REGISTRY_VERSION,
        "headings": HEADINGS,
        "units": UNITS,
        "groups": [
            {
                "id": g.id,
                "name": g.name,
                "heading": g.heading,
                "meaning": g.meaning,
                "description": g.description,
                "game_level": g.game_level,
                "context_only": g.context_only,
                "members": [
                    {"feature": m.feature, "sign": m.sign, "adv": m.adv, "label": m.label,
                     "unit": m.unit, "description": m.description}
                    for m in g.members
                ],
            }
            for g in GROUPS.values()
        ],
    }  # fmt: skip


def freshness(paths: Paths) -> dict:
    out = {}
    for d in sorted(paths.raw.glob("*")):
        snaps = sorted(p.name.split("=", 1)[1] for p in d.glob("snapshot_ts=*"))
        if snaps:
            out[d.name] = snaps[-1]
    odds = sorted(
        p.name.split("=", 1)[1]
        for p in (paths.root / "raw" / "odds_api" / "live").glob("snapshot_ts=*")
    )
    if odds:
        out["odds_api"] = odds[-1]
    return out


# ------------------------------------------------------------------------------------ predictions


def best_rows(paths: Paths, games: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """One row per (game, model): the last lock before kickoff, else the backfill row. Adds status."""
    preds = _read(paths, "predictions")
    if preds.is_empty():
        return preds
    kick = games.select(
        "game_id", pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    )
    p = preds.join(kick, on="game_id").filter(pl.col("lock_ts") < pl.col("kickoff_utc"))
    live = p.filter(~pl.col("is_backfill")).sort("lock_ts").group_by("game_id", "model_id").last()
    back = p.filter(pl.col("is_backfill")).sort("lock_ts").group_by("game_id", "model_id").last()
    back = back.join(live.select("game_id", "model_id"), on=["game_id", "model_id"], how="anti")
    return pl.concat(
        [
            live.with_columns(pl.lit(LOCKED).alias("status")),
            back.with_columns(pl.lit(BACKFILL).alias("status")),
        ],
        how="vertical_relaxed",
    )


def _history(paths: Paths) -> pl.DataFrame:
    """Every season's games with the tz-naive `kickoff_utc` that `build()` applies. Elo replays
    all of it (B1, 2026-11-05: a one-season replay started every team at 1500 each September)."""
    return store.games_frame(paths).with_columns(
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    )


def preview_rows(
    paths: Paths, history: pl.DataFrame, slate: pl.DataFrame, now: datetime
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Score upcoming games without a lock, as of now. `history` is every season's games, so the
    reference Elo matches the lock. Returns (rows like predictions, market)."""
    from nfl import lock

    if slate.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    season = int(slate["season"][0])
    feats = store.read_features(paths, seasons=(season, season))
    models, _missing = lock.load_models(paths, season - 1)
    market = lock.market_at(feats, slate, now)
    scored = lock.score_approaches(models, feats, slate, now) + lock.score_reference(
        history, slate, market
    )
    rows = []
    for s in scored:
        f = s.frame
        if "contributions" not in f.columns:
            f = f.with_columns(pl.lit(None, dtype=pl.Utf8).alias("contributions"))
        rows.append(
            f.select("game_id", "p_home", "spread_home", "contributions").with_columns(
                pl.lit(s.model_id).alias("model_id"),
                pl.lit(now, dtype=pl.Datetime("us")).alias("lock_ts"),
                pl.lit(PREVIEW).alias("status"),
            )
        )
    return (pl.concat(rows) if rows else pl.DataFrame()), market


def pregame_rows(paths: Paths, games: pl.DataFrame, have: pl.DataFrame, now: datetime, game_ids: list[str] | None = None) -> pl.DataFrame:  # fmt: skip
    """Games that kicked off with neither a lock nor a backfill (a week before public locks, a
    missed lock, or the days before Tuesday's backfill), scored as of an hour before kickoff with
    the same models and only data known then, so the page shows what the models said. Labeled
    'pregame': never part of the live record. Limited to the current and previous week, unless
    `game_ids` names the games to score (the retro builder: no week window)."""
    started = games.filter(
        (pl.col("kickoff_utc") <= now) & ~pl.col("game_id").is_in(have["game_id"].to_list())
    )
    upcoming = games.filter(pl.col("kickoff_utc") > now)
    if started.is_empty():
        return pl.DataFrame()
    if game_ids is None:
        current = (
            int(upcoming["week"].min()) if not upcoming.is_empty() else int(games["week"].max())
        )
        started = started.filter(pl.col("week") >= current - 1)
    else:
        started = started.filter(pl.col("game_id").is_in(game_ids))
        if started.is_empty():
            return pl.DataFrame()
    out = []
    history = _history(paths)
    for (kick,), part in started.group_by(["kickoff_utc"]):
        rows, _ = preview_rows(paths, history, part, kick - PREGAME_LEAD)
        if not rows.is_empty():
            out.append(rows.with_columns(pl.lit(PREGAME).alias("status")))
    return pl.concat(out, how="vertical_relaxed") if out else pl.DataFrame()


def display_rows(paths: Paths, games: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """Exactly the prediction rows the game pages show: locks/backfill, plus previews of the next
    two upcoming weeks, plus 'pregame' rows for games that kicked off unlocked. `games` is one
    season with a tz-naive `kickoff_utc`. Empty frame when there are no predictions at all."""
    rows = best_rows(paths, games, now)
    have = (
        rows.select("game_id").unique()
        if not rows.is_empty()
        else pl.DataFrame(schema={"game_id": pl.Utf8})
    )
    upcoming = games.filter(
        (pl.col("kickoff_utc") > now) & ~pl.col("game_id").is_in(have["game_id"].to_list())
    )
    # preview only the next two weeks: further out, nothing has been built for those games yet
    if not upcoming.is_empty():
        first = int(upcoming["week"].min())
        upcoming = upcoming.filter(pl.col("week") <= first + 1)
    prev, _ = preview_rows(paths, _history(paths), upcoming, now)
    pre = pregame_rows(paths, games, have, now)
    allrows = pl.concat(
        [r.select("game_id", "model_id", "p_home", "spread_home", "contributions", "lock_ts", "status")
         for r in (rows, prev, pre) if not r.is_empty()],
        how="vertical_relaxed",
    ) if any(not r.is_empty() for r in (rows, prev, pre)) else pl.DataFrame()  # fmt: skip
    return allrows


def write_retro(paths: Paths, season: int) -> list[str]:
    """Copy validated game retros and recaps from marts/retro to site/retro/<game_id>.json and
    site/recap_<season>_<ww>.json (published seasons only). Invalid files are skipped.
    Returns the site-relative names written."""
    from pydantic import ValidationError

    from nfl.retro.schema import RetroGame, WeekRecap

    if season not in RETRO_PUBLISH_SEASONS:
        return []
    src = paths.marts / "retro" / f"season={season}"
    out: list[str] = []
    for f in sorted(src.glob("*.json")) if src.exists() else []:
        is_recap = f.name.startswith("recap_")
        try:
            rec = (WeekRecap if is_recap else RetroGame).model_validate_json(f.read_text())
        except ValidationError:
            continue
        name = f"recap_{season}_{rec.week:02d}.json" if is_recap else f"retro/{rec.game_id}.json"
        _write(paths.site / name, rec.model_dump(mode="json"))
        out.append(name)
    return out


def market_rows(paths: Paths, games: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """The market per game as the game page shows it (game_id, p_home, spread_home, total, as_of,
    source): odds snapshot or schedule line as of kickoff. Empty frame when there is none."""
    return _market_by_game(paths, games, now)


def _market_by_game(paths: Paths, games: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """The market per game: the latest feature rows before kickoff (completed) or now (upcoming)."""
    from nfl import lock

    season = int(games["season"].max())
    feats = store.read_features(paths, seasons=(season, season), families=["market"])
    out = []
    g = games.with_columns(pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")))
    locks = g.select(
        "game_id",
        pl.min_horizontal(pl.col("kickoff_utc"), pl.lit(now, dtype=pl.Datetime("us"))).alias(
            "lock_ts"
        ),
    )
    for (lts,), part in locks.group_by(["lock_ts"]):
        out.append(
            lock.market_at(feats, g.filter(pl.col("game_id").is_in(part["game_id"].to_list())), lts)
        )
    return (
        pl.concat([o for o in out if not o.is_empty()])
        if any(not o.is_empty() for o in out)
        else pl.DataFrame()
    )


# ------------------------------------------------------------------------------- market movement


def _season_lines(paths: Paths, season: int, now: datetime) -> pl.DataFrame:
    """Every book's quotes for the season, only snapshots taken before `now`."""
    from nfl.odds import read_lines

    lines = read_lines(paths, (season, season))
    if lines.is_empty():
        return lines
    return lines.filter(pl.col("snapshot_ts") <= pl.lit(now, dtype=pl.Datetime("us")))


def _line_paths(lines: pl.DataFrame) -> dict[str, list[dict]]:
    """Per game, the pre-kickoff consensus path (ADR 0024)."""
    from nfl import market_history

    if lines.is_empty():
        return {}
    out: dict[str, list[dict]] = {}
    for r in market_history.paths(lines).iter_rows(named=True):
        out.setdefault(r["game_id"], []).append(r)
    return out


def _lock_times(paths: Paths, season: int) -> dict[str, datetime]:
    """The live lock of each game's headline line, if it has one."""
    pred = _read(paths, "predictions")
    if pred.is_empty():
        return {}
    live = pred.filter(
        (pl.col("season") == season) & ~pl.col("is_backfill") & (pl.col("model_id") == HEADLINE_ID)
    )
    return {r["game_id"]: r["lock_ts"] for r in live.group_by("game_id").agg(pl.col("lock_ts").max()).iter_rows(named=True)}  # fmt: skip


def _window_sources(paths: Paths, games: pl.DataFrame, season: int, now: datetime) -> dict:
    """QB1 changes and injury-status changes for the season, as seen up to `now` (ADR 0024, M20.3)."""
    from nfl import market_events

    try:
        depth = pl.concat(
            [
                pl.read_parquet(f)
                for f in (paths.curated_table("depth_charts") / f"season={season}").glob(
                    "*.parquet"
                )
            ],
            how="diagonal_relaxed",
        )
    except ValueError:  # no files
        depth = pl.DataFrame()
    qbs = [q for q in market_events.qb_changes(depth) if q["ts"] <= now]
    snaps = [(ts, df) for ts, df in market_events.load_injury_snapshots(paths, season) if ts <= now]
    done = games.filter(
        pl.col("kickoff_utc") + market_events.GAME_LENGTH <= pl.lit(now, dtype=pl.Datetime("us"))
    )
    return {
        "qbs": qbs,
        "injuries": market_events.injury_transitions(snaps),
        "results": market_events.results(done),
    }


def _game_events(g, points, window, starters, lock_ts) -> list[dict]:
    from nfl import market_events

    ev = market_events.game_events(
        g, points, window["qbs"], window["injuries"],
        starters.get((g["game_id"], g["home_team"]), set()) | starters.get((g["game_id"], g["away_team"]), set()),
        lock_ts, window.get("results", []),
    )  # fmt: skip
    return [{**e, "ts": _ts(e["ts"])} for e in ev]


def _strong_calls(paths: Paths, season: int) -> tuple[dict[str, list[dict]], dict]:
    """Per game, its strong calls with outcomes; and the tracker block: record per approach, newest first list."""
    import json

    from nfl import strong_calls

    calls = strong_calls.grade_all(paths)  # the append-only record, graded now: never a stale file
    first = None
    if not calls.is_empty():
        first = calls["lock_ts"].min()
        calls = strong_calls.last_lock(calls.filter(pl.col("season") == season))
    by_game: dict[str, list[dict]] = {}
    items = []
    for r in (
        calls.sort("lock_ts", descending=True).iter_rows(named=True) if not calls.is_empty() else []
    ):
        x = {
            "game_id": r["game_id"], "week": r["week"], "model_id": r["model_id"], "lock_ts": _ts(r["lock_ts"]),
            "side": r["side"], "team": r["team"], "p_home": _r(r["p_home"]), "market_p": _r(r["market_p"]),
            "spread_home": _r(r["spread_home"], 1), "market_spread": _r(r["market_spread"], 1),
            "top_groups": json.loads(r["top_groups"] or "[]"),
            "assumption": json.loads(r["assumption"]) if r["assumption"] else None,
            "what_if_p_home": _r(r["what_if_p_home"]), "sentence": r["sentence"],
            "result": r.get("result"), "log_loss": _r(r.get("log_loss")),
            "market_log_loss": _r(r.get("market_log_loss")), "closing_toward": r.get("closing_toward"),
        }  # fmt: skip
        by_game.setdefault(r["game_id"], []).append(x)
        items.append(x)
    record = {"gap": strong_calls.STRONG_GAP, "first_lock": _ts(first), "record": strong_calls.record(calls),
              "calls": items}  # fmt: skip
    return by_game, record


def _today(paths: Paths, now: datetime) -> dict[str, dict]:
    """Per upcoming game, the latest preview score of each approach (ADR 0024): not a lock, never graded."""
    from nfl import previews

    p = previews.latest(paths)
    out: dict[str, dict] = {}
    for r in p.filter(pl.col("scored_at") <= pl.lit(now, dtype=pl.Datetime("us"))).iter_rows(
        named=True
    ):
        d = out.setdefault(r["game_id"], {"scored_at": _ts(r["scored_at"]), "models": {}})
        d["models"][r["model_id"]] = {
            "p_home": _r(r["p_home"]),
            "spread_home": _r(r["spread_home"], 1),
        }
        d["scored_at"] = max(d["scored_at"], _ts(r["scored_at"]))
    return out


def _safe(fn, default, *args):
    """fn(*args), or `default` with a printed warning: for page data that must never stop a build."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001
        print(f"site: {getattr(fn, '__name__', 'step')} failed, continuing: {e!r}")
        return default


def _swings(paths: Paths, games: pl.DataFrame, season: int, now: datetime, feats: pl.DataFrame,
            injuries: list[dict]) -> dict[str, list[dict]]:  # fmt: skip
    """Per upcoming game, what could swing it (ADR 0024, M20.6): the quarterback what-if, rescored with
    the locked artifacts, plus listed factors. A failure costs the what-ifs, never the site build."""
    try:
        return _swings_unsafe(paths, games, season, now, feats, injuries)
    except Exception as e:  # noqa: BLE001
        print(f"site: swings failed, continuing: {e!r}")
        return {}


def _swings_unsafe(paths, games, season, now, feats, injuries) -> dict[str, list[dict]]:
    from nfl import coaches, lock, swings
    from nfl.features.strength import load_plays_all, team_games
    from nfl.models.elo import TEAM_ALIASES
    from nfl.previews import HORIZON

    k = pl.col("kickoff_utc")
    up = games.filter(
        (k > pl.lit(now, dtype=pl.Datetime("us")))
        & (k <= pl.lit(now + HORIZON, dtype=pl.Datetime("us")))
    )
    if up.is_empty() or feats.is_empty():
        return {}
    try:
        models, _ = lock.load_models(paths, season - 1)
    except RuntimeError:
        models = []
    allg = store.games_frame(paths)
    plays = load_plays_all(paths, int(allg["season"].min()))
    tg = (
        team_games(allg)
        .with_columns(pl.col("team").replace(TEAM_ALIASES).alias("ckey"))
        .select("game_id", "team", "ckey", "season", "kickoff_utc")
    )
    d = paths.curated_table("depth_charts") / f"season={season}"
    files = list(d.glob("*.parquet")) if d.exists() else []
    depth = (
        pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
        if files
        else pl.DataFrame()
    )
    chart = swings.depth_qbs(depth, now)
    starts = swings.recent_starters(plays, allg.filter(pl.col("season") == season), now)
    full = swings.full_names(depth)
    for st in starts.values():  # charted full names over play-by-play's "L.Jackson"
        st["names"] = {q: full.get(q, n) for q, n in st["names"].items()}
    asof = store.as_of(feats.filter(pl.col("game_id").is_in(up["game_id"].to_list())), now)
    spells = coaches.load_spells()

    # every candidate quarterback, computed in as few passes as there are candidates per team
    cand = {}
    for g in up.iter_rows(named=True):
        for team in (g["home_team"], g["away_team"]):
            c = swings.candidates(
                chart.get(TEAM_ALIASES.get(team, team), []),
                starts.get(TEAM_ALIASES.get(team, team), {}),
            )
            cand[(g["game_id"], team)] = c
    values: dict[tuple[str, str], dict[str, dict]] = {}
    for i in range(max((len(c) for c in cand.values()), default=0)):
        rows = [(gid, team, list(c)[i]) for (gid, team), c in cand.items() if len(c) > i]
        named = pl.DataFrame(
            rows, schema={"game_id": pl.Utf8, "team": pl.Utf8, "qb1": pl.Utf8}, orient="row"
        )
        for (gid, team), v in swings.qb_values(tg, plays, named).items():
            q = named.filter((pl.col("game_id") == gid) & (pl.col("team") == team))["qb1"][0]
            values.setdefault((gid, team), {})[q] = v

    out: dict[str, list[dict]] = {}
    for g in up.iter_rows(named=True):
        gid, items = g["game_id"], []
        rows = asof.filter(pl.col("game_id") == gid)
        report = {
            i["gsis_id"]: i["status"]
            for i in injuries
            if i["week"] == g["week"] and i["team"] in (g["home_team"], g["away_team"])
        }
        for side, team in (("home", g["home_team"]), ("away", g["away_team"])):
            key = TEAM_ALIASES.get(team, team)
            c, v = cand.get((gid, team), {}), values.get((gid, team), {})
            stored = rows.filter(
                (pl.col("side") == side) & (pl.col("feature") == "strength.qb_epa")
            )["value"]
            assumed = swings.assumed_qb(stored[0] if stored.len() else None, v)
            alt = swings.alternative(chart.get(key, []), starts.get(key, {}), report, assumed)
            if alt is None or not models or alt[0] not in v:
                continue
            q, why = alt
            qb1 = (chart.get(key) or [(None, None)])[0][0]
            mod = swings.apply(rows, side, {**v[q], "availability.qb1_out": 0.0 if q == qb1 else 1.0,
                                            "availability.qb_change": 0.0 if q == starts.get(key, {}).get("last") else 1.0})  # fmt: skip
            base = swings.rescore(models, rows, gid, now)
            what = swings.rescore(models, mod, gid, now)
            items.append({
                "kind": "qb", "team": team, "why": why,
                "assumed": {"qb": assumed, "name": c.get(assumed, assumed), "status": report.get(assumed),
                            "p_home": {m: _r(p) for m, p in base.items()}},
                "alternative": {"qb": q, "name": c.get(q, q), "status": report.get(q),
                                "p_home": {m: _r(p) for m, p in what.items()}},
            })  # fmt: skip
        # listed factors: key starters in doubt, staff changes this week, a short week
        for i in injuries:
            # the positions the availability family weights at 2 (the quarterback has the what-if above)
            if i["week"] == g["week"] and i["team"] in (g["home_team"], g["away_team"]) \
                    and i["status"] in swings.DOUBT and i["pos"] in ("T", "DE", "OLB"):  # fmt: skip
                items.append(
                    {
                        "kind": "injury",
                        "team": i["team"],
                        "text": f"{i['player']} ({i['pos']}) {i['status'].lower()}",
                    }
                )
        for r in spells.filter((pl.col("season") == season) & (pl.col("start_week") == g["week"])
                               & pl.col("team").replace(TEAM_ALIASES).is_in([TEAM_ALIASES.get(t, t) for t in (g["home_team"], g["away_team"])])).iter_rows(named=True):  # fmt: skip
            if r["role"] in ("HC", "OFF_PC", "DEF_PC") and r["evidence"] in coaches.CONFIRMED:
                what = {
                    "HC": "head coach",
                    "OFF_PC": "offensive play-caller",
                    "DEF_PC": "defensive play-caller",
                }[r["role"]]
                items.append(
                    {
                        "kind": "coaching",
                        "team": r["team"],
                        "text": f"{r['person']}'s first game as {what}",
                    }
                )
        for side, team in (("home", g["home_team"]), ("away", g["away_team"])):
            rd = rows.filter(
                (pl.col("side") == side) & (pl.col("feature") == "environment.rest_days")
            )["value"]
            if rd.len() and rd[0] is not None and rd[0] < swings.SHORT_REST:
                items.append(
                    {
                        "kind": "rest",
                        "team": team,
                        "text": f"{team} on a short week ({int(rd[0])} days' rest)",
                    }
                )
        wx = {
            f: v
            for f, v in rows.filter(pl.col("feature").str.starts_with("weather."))
            .select("feature", "value")
            .iter_rows()
        }
        text = swings.weather_text(
            wx.get("weather.temp_f"), wx.get("weather.wind_mph"), wx.get("weather.precip_pct")
        )
        if text:
            items.append({"kind": "weather", "team": None, "text": text})
        if items:
            out[gid] = items
    return out


def _totals(paths: Paths, games: pl.DataFrame) -> tuple[dict[str, dict], dict | None]:
    """(game_id -> last locked total, the tracker block). A failure costs the totals, not the site."""
    from nfl.approaches import totals

    try:
        rows = totals.load(paths)
        last = rows.sort("lock_ts").group_by("game_id", maintain_order=True).last()
        by_game = {r["game_id"]: r for r in last.iter_rows(named=True)}
        return by_game, totals.summary(totals.grade(paths, games), rows)
    except Exception as e:  # noqa: BLE001
        print(f"site: totals failed, continuing: {e!r}")
        return {}, None


def _expected_score(t: dict | None, detail: dict) -> dict | None:
    """The locked total split by the headline line's spread at that lock (ADR 0024): context."""
    if t is None or t["total"] is None:
        return None
    sp = (detail.get("models") or {}).get(HEADLINE_ID, {}).get("spread_home")
    out = {"total": _r(t["total"], 1), "sd": _r(t["sd_total"], 1), "market_total": _r(t["market_total"], 1),
           "lock_ts": _ts(t["lock_ts"]), "home": None, "away": None}  # fmt: skip
    if sp is not None:
        out["home"], out["away"] = _r((t["total"] + sp) / 2, 1), _r((t["total"] - sp) / 2, 1)
    return out


def _line_point(p: dict) -> dict:
    return {"ts": _ts(p["snapshot_ts"]), "spread_home": _r(p["spread_home"], 2),
            "total": _r(p["total"], 2), "p_home": _r(p["p_home"]), "n_books": p["n_books"]}  # fmt: skip


def _books_out(b: dict | None) -> dict | None:
    """Each book's line at the latest pre-kickoff snapshot and where they disagree (M20.13)."""
    if b is None:
        return None
    rows = [{k: (_r(v, 4) if k == "p_home" else v) for k, v in r.items()} for r in b["books"]]
    return {**b, "snapshot_ts": _ts(b["snapshot_ts"]), "books": rows}


def _line_move(points: list[dict], lock_ts: datetime | None) -> dict | None:
    from nfl import market_history

    s = market_history.summary(points, lock_ts)
    if s is None:
        return None
    return {
        "first_seen": _ts(s["first_seen"]), "latest": _ts(s["latest"]), "n_points": s["n_points"],
        "lock_ts": _ts(lock_ts) if lock_ts else None,
        "since_first": s["since_first"], "since_lock": s["since_lock"], "last_day": s["last_day"],
    }  # fmt: skip


# ------------------------------------------------------------------------------------------ build


def write_league(paths: Paths, season: int, snapshot: str | None) -> None:
    """ADR 0019: a failure here must never stop a site build, and a lock's site build runs after the
    push. A Polars panic isn't an Exception, so it's named. The page keeps the last file."""
    try:
        from nfl.league.build import build as build_league

        build_league(paths, season, snapshot=snapshot)
    except (Exception, pl.exceptions.PanicException) as e:  # noqa: BLE001
        print(f"site: league.json failed, continuing: {e!r}")


def write_team_files(
    paths: Paths, season: int, week: int, games: pl.DataFrame, claims: tuple | None = None
) -> None:
    """ADR 0021: staff and tendency files for the team pages, one per team, for the current season
    only. Like the league's, a failure here never stops a site build; the last files stay.

    `coaches.json` isn't rebuilt here on purpose: it has no evidence filter, so it stays a manual
    `nfl coaches` until M17.9 gives it one."""
    if season != current_season():
        return
    try:
        from nfl.staff_context import team_files

        def label(metric: str) -> dict:
            d = TENDENCY_METRICS[metric]
            return {
                "label": d["label"],
                "help": d["help"],
                "unit": d["unit"],
                "lo": "less",
                "hi": "more",
            }

        avail = _safe(_availability, {}, paths, season, week, claims)
        for team, body in team_files(paths, season, week, games, label).items():
            body["availability"] = avail.get(team)  # ADR 0027, M24.4: additive
            _write(paths.site / "team" / f"{team}.json", body, compact=True)
    except (Exception, pl.exceptions.PanicException) as e:  # noqa: BLE001
        print(f"site: team files failed, continuing: {e!r}")


def build(paths: Paths, season: int | None = None, league_snapshot: str | None = None) -> dict:
    t0 = time.perf_counter()
    season = season or current_season()
    now = now_utc().replace(tzinfo=None, microsecond=0)
    site = paths.site
    games = (
        store.games_frame(paths)
        .filter(pl.col("season") == season)
        .with_columns(pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")))
    )
    reg = model_registry()

    allrows = display_rows(paths, games, now)
    market = _market_by_game(paths, games, now)
    # the market pieces (ADR 0024) are additive page data: a failure costs that piece, never the build
    season_lines = _safe(_season_lines, pl.DataFrame(), paths, season, now)
    lines = _safe(_line_paths, {}, season_lines)
    books = _safe(market_books.by_game, {}, season_lines)
    locks = _safe(_lock_times, {}, paths, season)
    window = _safe(_window_sources, {}, paths, games, season, now)

    feats = store.read_features(paths, seasons=(season, season))
    tend = _read(paths, "tendencies")
    injuries = _injuries(paths, season)
    swing = _swings(paths, games, season, now, feats, injuries)
    calls_by_game, calls_record = _safe(_strong_calls, ({}, None), paths, season)
    claims, claims_by_game, claims_record = _safe(
        _player_claims, (None, {}, None), paths, games, season
    )
    lineups = _safe(_lineups, {}, paths, games, season, injuries, now)
    today = _safe(_today, {}, paths, now)
    matchup_ctx = _safe(_matchup_ctx, None, paths)  # ADR 0028: Engine and ledger, once per build
    conditions = _safe(_conditions_frame, None, paths)
    totals_by_game, totals_record = _totals(paths, games)
    from nfl.llm.narrative import load_records

    narr = {r.game_id: r for r in load_records(paths, (season, season))}
    edges = group_edges(paths, games, feats, season, now)
    charted, starters = _depth_context(paths, games, season, now)
    card_ctx = {
        "starts": _qb_starts(games),
        "charted": charted,
        "starters": starters,
        "listed": _listed(injuries),
        "prev_game": _prev_game_weeks(games),
        "ranks": _contrast_ranks(tend, season),
        "weather": feats.filter(pl.col("feature") == WEATHER_FEATURE) if not feats.is_empty() else feats,
    }  # fmt: skip

    n_weeks = 0
    for (week,), wk in games.group_by(["week"], maintain_order=True):
        wk = wk.sort("kickoff_utc", "game_id")
        slate_games = []
        for g in wk.iter_rows(named=True):
            row = _game_row(g, allrows, market, reg)
            row["card"] = _card(g, edges, injuries, now, **card_ctx)
            points = lines.get(g["game_id"], [])
            row["line_move"] = _safe(_line_move, None, points, locks.get(g["game_id"]))
            slate_games.append(row)
            detail = row | _game_detail(g, allrows, feats, tend, injuries, narr, now, edges)
            detail["market_history"] = _safe(lambda pts: [_line_point(p) for p in pts], [], points)
            detail["books"] = _safe(_books_out, None, books.get(g["game_id"]))
            detail["swings"] = swing.get(g["game_id"], [])
            detail["strong_calls"] = calls_by_game.get(g["game_id"], [])
            detail["key_players"] = claims_by_game.get(g["game_id"])  # ADR 0027: context, M24.4
            detail["lineups"] = lineups.get(g["game_id"])  # ADR 0027: the formation map, M24.5
            detail["today"] = today.get(g["game_id"])
            detail["matchups"] = _safe(game_matchups, None, matchup_ctx, g)
            detail["paths"] = _safe(game_paths, None, conditions, g)
            detail["paths_outcome"] = _safe(game_paths_outcome, None, conditions, g)
            detail["expected_score"] = _safe(
                _expected_score, None, totals_by_game.get(g["game_id"]), detail
            )
            detail["market_events"] = _safe(
                _game_events,
                [],
                g,
                points,
                window,
                card_ctx["starters"],
                locks.get(g["game_id"]),
            )
            _write(site / "game" / f"{g['game_id']}.json", detail)
        _write(
            site / f"slate_{season}_{int(week):02d}.json",
            {"schema_version": SCHEMA_VERSION, "season": season, "week": int(week),
             "generated_at": _ts(now), "games": slate_games},
        )  # fmt: skip
        n_weeks += 1

    current_week = (
        int(games.filter(pl.col("kickoff_utc") > now)["week"].min())
        if not games.filter(pl.col("kickoff_utc") > now).is_empty()
        else int(games["week"].max())
    )
    _write(
        site / "meta.json",
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _ts(now),
            "season": season,
            "current_week": current_week,
            "weeks": sorted(int(w) for w in games["week"].unique().to_list()),
            "freshness": freshness(paths),
            "models": reg,
            "approaches": approaches_meta(paths, season),
            "groups": groups_meta(),
            "tendency_metrics": TENDENCY_METRICS,
            "tendency_situations": TENDENCY_SITUATION_LABELS,
            "split_defs": split_defs(),
            "feature_bands": feature_bands(feats, games, now),
            "last_lock": _last_lock(paths),
        },
    )
    _write(
        site / "tracker.json",
        tracker(paths, season, reg)
        | {"strong_calls": calls_record, "totals": totals_record, "player_claims": claims_record},
    )
    _write(site / "audit.json", audit(paths))
    try:  # additive page data (ADR 0019): a failure must never stop the site build
        teams = teams_file(feats, games, now, current_week)
        if teams is not None:
            _write(site / "teams.json", teams, compact=True)  # 236 KB at indent=1, 178 KB compact
    except Exception as e:  # noqa: BLE001
        print(f"site: teams.json failed, continuing: {e!r}")
    write_team_files(paths, season, current_week, games, claims)
    try:
        write_retro(paths, season)
    except Exception as e:  # noqa: BLE001  retros must never break the site build
        print(f"site: write_retro failed, continuing: {e!r}")
    write_league(paths, season, league_snapshot)  # last: the simulation holds up nothing above
    return {"weeks": n_weeks, "games": games.height, "seconds": round(time.perf_counter() - t0, 1)}


def feature_bands(feats: pl.DataFrame, games: pl.DataFrame, now: datetime) -> dict[str, dict]:
    """League spread per team-level feature for the game page's Details tab: p10, the quartiles and
    p90 of each team's value entering its next game (`team_latest`; ADR 0019). One band per feature
    for the whole season, so an old game's values sit on today's league, display only."""
    import numpy as np

    if feats.is_empty() or games.is_empty():
        return {}
    latest = team_latest(feats, games, now)
    out: dict[str, dict] = {}
    for (feature,), part in latest.group_by(["feature"]):
        if part.height >= FEATURE_BAND_MIN_TEAMS:
            pcts = np.percentile(part["value"].to_numpy(), (10, 25, 50, 75, 90))
            out[feature] = dict(zip(("lo", "q1", "med", "q3", "hi"), map(_r, pcts), strict=True))
    return dict(sorted(out.items()))


def group_edges(
    paths: Paths, games: pl.DataFrame, feats: pl.DataFrame, season: int, now: datetime
) -> dict[str, dict]:
    """Per game and group: which team has the edge and how big it is, as a percentile of all
    matchup edges 2005–2025 (|composite| rank), using the same composites as the DIY page."""
    import numpy as np

    from nfl.approaches import diy

    mfile = paths.marts / "diy" / "matrix.parquet"
    if not mfile.exists() or games.is_empty():
        return {}
    ref = pl.read_parquet(mfile).filter(~pl.col("warmup").cast(pl.Boolean))
    locks = games.select(
        "game_id",
        pl.min_horizontal(pl.col("kickoff_utc"), pl.lit(now, dtype=pl.Datetime("us"))).alias(
            "lock_ts"
        ),
    )
    vec = store.game_vectors(store.as_of(feats, locks))
    allf = sorted(vec["feature"].unique().to_list())
    wide = games.select("game_id").join(store.to_wide(vec, allf), on="game_id", how="left")
    try:
        comp = diy._composites(paths, wide, season, season - 1)
    except FileNotFoundError:
        return {}
    out: dict[str, dict] = {}
    teams = dict(
        zip(games["game_id"], zip(games["home_team"], games["away_team"], strict=True), strict=True)
    )
    for j, gid_group in enumerate(diy.GROUP_IDS):
        col = f"c_{gid_group}"
        if col not in ref.columns:
            continue
        r = np.sort(np.abs(ref[col].to_numpy()))
        if not r.any():
            continue  # live-only group (no history)
        for i, gid in enumerate(wide["game_id"].to_list()):
            c = float(comp[i, j])
            pct = 100.0 * np.searchsorted(r, abs(c), side="right") / len(r)
            home, away = teams[gid]
            out.setdefault(gid, {})[gid_group] = {
                "favors": None if abs(c) < 1e-9 else (home if c > 0 else away),
                "strength_pct": _r(pct, 0),
            }
    return out


def _last_lock(paths: Paths) -> dict | None:
    p = _read(paths, "predictions")
    if p.is_empty():
        return None
    live = p.filter(~pl.col("is_backfill"))
    if live.is_empty():
        return None
    r = live.sort("lock_ts").row(-1, named=True)
    return {
        "lock_ts": _ts(r["lock_ts"]),
        "season": r["season"],
        "week": r["week"],
        "slot": r["slot"],
    }


def _game_row(g: dict, allrows: pl.DataFrame, market: pl.DataFrame, reg: dict) -> dict:
    gid = g["game_id"]
    mk = market.filter(pl.col("game_id") == gid) if not market.is_empty() else pl.DataFrame()
    m = mk.row(0, named=True) if mk.height else None
    models = {}
    if not allrows.is_empty():
        for r in allrows.filter(pl.col("game_id") == gid).iter_rows(named=True):
            if r["model_id"] not in reg:
                continue
            p = r["p_home"]
            models[r["model_id"]] = {
                "p_home": _r(p),
                "spread_home": _r(r["spread_home"], 1),
                "status": r["status"],
                "lock_ts": _ts(r["lock_ts"]),
                "divergence": _r(p - m["p_home"])
                if (m and m["p_home"] is not None and p is not None)
                else None,
            }
    result = g.get("result")
    return {
        "game_id": gid,
        "season": g["season"],
        "week": g["week"],
        "kickoff_utc": _ts(g["kickoff_utc"]),
        "away": g["away_team"],
        "home": g["home_team"],
        "stadium": g.get("stadium"),
        "roof": g.get("roof"),
        "neutral_site": (g.get("location") or "Home") != "Home",
        "away_qb": g.get("away_qb_name"),
        "home_qb": g.get("home_qb_name"),
        "result": None if result is None else {"home_score": g.get("home_score"), "away_score": g.get("away_score"), "margin": result},
        "market": None if m is None else {
            "p_home": _r(m["p_home"]), "spread_home": _r(m["spread_home"], 1), "total": _r(m["total"], 1),
            "as_of": _ts(m["as_of"]), "source": m["source"],
        },
        "models": models,
    }  # fmt: skip


# (offense metric, offense label, high rate is the extreme?, defense metric, defense label)
CONTRASTS = [
    ("pass_rate", "pass-heavy", True, "blitz_rate", "blitz-heavy"),
    ("screen_rate", "screen-heavy", True, "blitz_rate", "blitz-heavy"),
    ("pass_rate", "run-heavy", False, "box_8plus_vs_run_rate", "box-stacking"),
    ("play_action_rate", "play-action-heavy", True, "box_8plus_vs_run_rate", "box-stacking"),
    ("no_huddle_rate", "up-tempo", True, "blitz_rate", "blitz-heavy"),
]
CONTRAST_TOP = 5  # both sides must rank this high among the league's teams
CONTRAST_MIN_TEAMS = 24
WEATHER_FEATURE = "narrative.weather_concern"
HEADLINE_ID = "student"  # the headline line (D5); the web's HEADLINE in lib/models.ts
USUAL_QB_MIN_STARTS = 3  # fewer, or a tie, and "usually" would name whoever filled in


def _contrast_ranks(tend: pl.DataFrame, season: int) -> dict[tuple[str, str, bool], dict[str, int]]:
    """(side, metric, high is extreme) -> {canonical team: rank, 1 = most extreme}. Metrics with
    fewer than CONTRAST_MIN_TEAMS teams are left out. Computed once per build."""
    from nfl.models.elo import TEAM_ALIASES

    if tend.is_empty():
        return {}
    t = tend.filter(
        (pl.col("season") == season) & (pl.col("situation") == "all") & pl.col("rate").is_not_null()
    )
    wanted = {("off", m, hi) for m, _, hi, _, _ in CONTRASTS}
    wanted |= {("def", dm, True) for _, _, _, dm, _ in CONTRASTS}
    ranks: dict[tuple[str, str, bool], dict[str, int]] = {}
    for side, metric, high in wanted:
        x = t.filter((pl.col("side") == side) & (pl.col("metric") == metric))
        rates = {TEAM_ALIASES.get(r["team"], r["team"]): r["rate"] for r in x.iter_rows(named=True)}
        if len(rates) < CONTRAST_MIN_TEAMS:
            continue
        order = sorted(rates, key=lambda k: (-rates[k] if high else rates[k], k))
        ranks[(side, metric, high)] = {k: i + 1 for i, k in enumerate(order)}
    return ranks


def _contrast(ranks: dict, g: dict) -> dict | None:
    """The starkest (offense, defense) pair in this game, or None. Lowest rank sum wins; ties go
    to the earlier CONTRASTS entry, then away offense first."""
    from nfl.models.elo import TEAM_ALIASES

    best = None
    for i, (om, ol, high, dm, dl) in enumerate(CONTRASTS):
        o_ranks, d_ranks = ranks.get(("off", om, high)), ranks.get(("def", dm, True))
        if not o_ranks or not d_ranks:
            continue
        for j, (off, dfn) in enumerate(((g["away_team"], g["home_team"]), (g["home_team"], g["away_team"]))):  # fmt: skip
            ro = o_ranks.get(TEAM_ALIASES.get(off, off))
            rd = d_ranks.get(TEAM_ALIASES.get(dfn, dfn))
            if ro is None or rd is None or ro > CONTRAST_TOP or rd > CONTRAST_TOP:
                continue
            key = (ro + rd, i, j)
            if best is None or key < best[0]:
                best = (key, {"offense": off, "defense": dfn, "off_label": ol, "def_label": dl,
                              "off_rank": ro, "def_rank": rd})  # fmt: skip
    return None if best is None else best[1]


def _qb_starts(games: pl.DataFrame) -> dict[str, list[tuple[datetime, str]]]:
    """team -> [(kickoff, starting QB name)] in kickoff order, home and away starts together."""
    starts: dict[str, list[tuple[datetime, str]]] = {}
    for g in games.sort("kickoff_utc", "game_id").iter_rows(named=True):
        for team, qb in ((g["home_team"], g.get("home_qb_name")), (g["away_team"], g.get("away_qb_name"))):  # fmt: skip
            if qb:
                starts.setdefault(team, []).append((g["kickoff_utc"], qb))
    return starts


def _depth_context(
    paths: Paths, games: pl.DataFrame, season: int, now: datetime
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], set[str]]]:
    """From the model's own depth-chart lookup: (game_id, team) -> charted QB1 by name for games
    not yet kicked off, and (game_id, team) -> the ids of everyone listed first at a position,
    special teams excluded. Both empty without depth charts, so the card claims nothing."""
    import duckdb

    from nfl.features import availability

    chart_dir = paths.curated_table("depth_charts") / f"season={season}"
    if games.is_empty() or not any(chart_dir.glob("*.parquet")):
        return {}, {}
    depth = availability.load_depth(paths)
    starters: dict[tuple[str, str], set[str]] = {}
    for r in availability.charted_starters(games, depth, now).iter_rows(named=True):
        starters.setdefault((r["game_id"], r["team"]), set()).add(r["gsis_id"])
    upcoming = games.filter(pl.col("kickoff_utc") > now)
    if upcoming.is_empty():
        return {}, starters
    # oldest first, so the latest spelling of a name wins whatever the file order
    ids = duckdb.sql(
        f"select gsis_id, player_name from read_parquet('{chart_dir.as_posix()}/*.parquet') "
        "where gsis_id is not null and player_name is not null order by dt nulls first"
    ).fetchall()
    return _named_qbs(availability.charted_qb1(upcoming, depth, now), dict(ids)), starters


def _named_qbs(charted: pl.DataFrame, names: dict[str, str]) -> dict[tuple[str, str], str]:
    """`charted_qb1`'s player ids as names; an id with no name is left out."""
    return {
        (r["game_id"], r["team"]): names[r["qb1"]]
        for r in charted.iter_rows(named=True)
        if r["qb1"] in names
    }


def _usual_qb(starts: dict, team: str, cut: datetime) -> str | None:
    """The team's clear regular before `cut`: the most starts, at least USUAL_QB_MIN_STARTS and
    more than anyone else, or None. Pass min(kickoff, now): an unplayed game's name is a projection."""
    count: dict[str, int] = {}
    for ts, qb in starts.get(team, []):
        if ts < cut:
            count[qb] = count.get(qb, 0) + 1
    top = max(count.values(), default=0)
    leaders = [q for q, n in count.items() if n == top]
    return leaders[0] if top >= USUAL_QB_MIN_STARTS and len(leaders) == 1 else None


def _last_qb(starts: dict, team: str, cut: datetime) -> str | None:
    """The team's most recent starter before `cut`: a QB already in the job isn't news."""
    played = [qb for ts, qb in starts.get(team, []) if ts < cut]
    return played[-1] if played else None


def _missing(i: dict) -> bool:
    return bool(i["player"]) and any(k in (i["status"] or "").lower() for k in ("out", "doubtful"))


def _listed(injuries: list[dict]) -> set[tuple[str, str, int]]:
    """(team, player, week) for every Out or Doubtful row."""
    return {(i["team"], i["player"], i["week"]) for i in injuries if _missing(i)}


def _prev_game_weeks(games: pl.DataFrame) -> dict[tuple[str, int], int]:
    """(team, week) -> the week of that team's previous game, so a bye doesn't look like a gap."""
    weeks: dict[str, list[int]] = {}
    for g in games.sort("week").iter_rows(named=True):
        for t in (g["home_team"], g["away_team"]):
            weeks.setdefault(t, []).append(int(g["week"]))
    return {(t, w): ws[i - 1] for t, ws in weeks.items() for i, w in enumerate(ws) if i}


def _card(
    g, edges, injuries, now, starts, ranks, weather, charted, *, starters, listed, prev_game
) -> dict:
    """The slate card block (U4): why-this-game data, as known at the same cut `_game_detail` uses."""
    gid, teams = g["game_id"], (g["home_team"], g["away_team"])
    cut = min(g["kickoff_utc"], now)
    wx = None
    if not weather.is_empty():
        fv = store.as_of(weather.filter(pl.col("game_id") == gid), cut)
        if fv.height:
            wx = _r(fv["value"][0])
    return {
        "edges": (edges or {}).get(gid, {}),
        "injuries": [
            {
                "team": i["team"],
                "player": i["player"],
                "pos": i["pos"],
                "status": i["status"],
                "starter": i.get("gsis_id") in starters.get((gid, i["team"]), ()),
                # against the team's last game, not the calendar: a bye isn't a return, and a
                # player back for a week and hurt again is news
                "new": (i["team"], i["player"], prev_game.get((i["team"], i["week"])))
                not in listed,
            }
            for i in injuries
            if i["week"] == g["week"] and i["team"] in teams and _missing(i)
        ],
        "usual_qb": {
            "home": _usual_qb(starts, g["home_team"], cut),
            "away": _usual_qb(starts, g["away_team"], cut),
        },
        "last_qb": {
            "home": _last_qb(starts, g["home_team"], cut),
            "away": _last_qb(starts, g["away_team"], cut),
        },
        "charted_qb": {
            "home": charted.get((gid, g["home_team"])),
            "away": charted.get((gid, g["away_team"])),
        },
        "weather_concern": wx,
        "contrast": _contrast(ranks, g),
    }


def _pp(total_logit: float, piece: float) -> float:
    """Points of home win probability this piece is worth: p(with it) − p(without it), ×100."""
    from scipy.special import expit

    return _r(100 * (expit(total_logit) - expit(total_logit - piece)), 1)


def _contributions_pp(c: dict) -> dict:
    """Per-model breakdown in win-probability points. Pieces interact, so they add up only
    approximately to the model's distance from 50%."""
    from scipy.special import expit

    L = sum(c.values())
    by_group: dict[str, dict] = {}
    for f, v in c.items():
        if f == "home_field":
            continue
        grp = FEATURE_GROUP.get(f, "other")
        d = by_group.setdefault(grp, {"_logit": 0.0, "features": {}})
        d["_logit"] += v
        d["features"][f] = _pp(L, v)
    for d in by_group.values():
        d["pp"] = _pp(L, d.pop("_logit"))
        d["features"] = {f: x for f, x in d["features"].items() if x}
    return {
        "p_home": _r(expit(L)),
        "home_field_pp": _pp(L, c.get("home_field", 0.0)),
        "groups": by_group,
    }


def _game_detail(g, allrows, feats, tend, injuries, narr, now, edges=None) -> dict:
    gid = g["game_id"]
    contrib = {}
    if not allrows.is_empty():
        for r in allrows.filter(
            (pl.col("game_id") == gid) & pl.col("contributions").is_not_null()
        ).iter_rows(named=True):
            contrib[r["model_id"]] = _contributions_pp(json.loads(r["contributions"]))
    # feature values as known at the game's lock (kickoff for completed, now for upcoming)
    cut = min(g["kickoff_utc"], now)
    fv = store.as_of(feats.filter(pl.col("game_id") == gid), cut)
    values: dict[str, dict] = {}
    for r in fv.iter_rows(named=True):
        d = values.setdefault(r["feature"], {"group": FEATURE_GROUP.get(r["feature"])})
        d[r["side"]] = _r(r["value"])
    return {
        "contributions": contrib,
        "edges": (edges or {}).get(gid, {}),
        "features": values,
        "tendencies": _tendencies(tend, g),
        "injuries": [
            i
            for i in injuries
            if i["week"] == g["week"] and i["team"] in (g["home_team"], g["away_team"])
        ],
        "narrative": json.loads(narr[gid].model_dump_json()) if gid in narr else None,
    }


# ------------------------------------------------------------------ matchups and paths (ADR 0028, M25.3)

MATCHUPS_MIN_WEEK = 3  # fewer than two earlier weeks: nothing worth showing
OPPONENT_TIER_MIN_WEEK = 4  # the opponent-tier flag is null before Week 4 (team_split_week)
OPPONENT_TIER_SPLITS = ("vs_top10_def", "vs_top10_off")
LEDE_BADGE = {
    "stable": "one of the more reliable kinds of number we show",
    "some": "a moderately reliable kind of number we show",
    "noise": "the least reliable kind of number we show",
}


def split_defs() -> dict[str, dict]:
    """meta.json `split_defs`: id -> label, definition, chooser, no_edge (a reason, '' when the split
    gets an edge), from the registry in splits.py."""
    from nfl import splits

    return {
        s.id: {"label": s.label, "definition": s.definition, "chooser": s.chooser, "no_edge": s.no_edge}
        for s in splits.SPLITS
    }  # fmt: skip


def _matchup_ctx(paths: Paths):
    """The matchup engine (it caches per season and week) and the candidates ledger, once per build."""
    from nfl import catalog, matchups

    return matchups.Engine(catalog.connect(paths)), matchups.load_ledger(paths)


def _conditions_frame(paths: Paths) -> pl.DataFrame:
    from nfl import catalog
    from nfl import paths as upset

    return upset.load_conditions(catalog.connect(paths))


def _matchup_row(r: dict) -> dict:
    return {
        "split": r["split"], "label": r["label"], "chooser": r["chooser"], "has_edge": r["has_edge"],
        "opp_rate": _r(r["opp_rate"], 3), "opp_rate_lo": _r(r["opp_rate_lo"], 3),
        "opp_rate_q1": _r(r["opp_rate_q1"], 3), "opp_rate_med": _r(r["opp_rate_med"], 3),
        "opp_rate_q3": _r(r["opp_rate_q3"], 3), "opp_rate_hi": _r(r["opp_rate_hi"], 3),
        "rate_faced": _r(r["rate_faced"], 3), "n_with": r["n_with"], "n_without": r["n_without"],
        "epa_with": _r(r["epa_with"], 3), "epa_without": _r(r["epa_without"], 3),
        "shrunk_gap": _r(r["shrunk_gap"], 3), "league_gap": _r(r["league_gap"], 3),
        "edge_pts_pg": _r(r["edge_pts_pg"], 2), "favours": r["favours"],
        "reliability": r["reliability"], "note": r["note"],
    }  # fmt: skip


def matchups_lede(sides: list[dict]) -> str | None:
    """A template naming the largest edge by absolute points among the rows that have one. Every
    number in it is the record's own (`edge_pts_pg`, 2 dp)."""
    best = None
    for sd in sides:
        for r in sd["rows"]:
            e = r["edge_pts_pg"]
            if (
                r["has_edge"]
                and e is not None
                and (best is None or abs(e) > abs(best[1]["edge_pts_pg"]))
            ):
                best = (sd, r)
    if best is None:
        return None
    sd, r = best
    # positive edge = favours the offense (matchups.py)
    fav = r.get("favours") or ("offense" if r["edge_pts_pg"] > 0 else "defense")
    if r["chooser"] == "offense":  # the offense's habit against the defense's matchup
        who = f"{sd['defense']}'s defense against {sd['offense']}'s {r['label'].lower()}"
    else:
        who = f"{sd['defense']}'s {r['label'].lower()} against {sd['offense']}'s offense"
    return (
        f"The matchup that matters most: {who}, worth {abs(r['edge_pts_pg'])} points a game "
        f"to {sd['offense'] if fav == 'offense' else sd['defense']}, "
        f"and {LEDE_BADGE[r['reliability']]}."
    )


def game_matchups(ctx, g: dict) -> dict | None:
    """The game's `matchups` section; None before Week 3. A past game and an upcoming one both read
    the game's own week (the engine reads weeks before it)."""
    if ctx is None or int(g["week"]) < MATCHUPS_MIN_WEEK:
        return None
    engine, ledger = ctx
    edges = engine.matchup_edges(g, int(g["week"]), ledger).to_dict()
    hide = OPPONENT_TIER_SPLITS if edges["as_of_week"] < OPPONENT_TIER_MIN_WEEK else ()
    sides = [
        {
            "offense": sd["offense"], "defense": sd["defense"],
            "rows": [_matchup_row(r) for r in sd["rows"] if r["split"] not in hide],
        }
        for sd in edges["sides"]
    ]  # fmt: skip
    return {"as_of_week": edges["as_of_week"], "sides": sides, "lede": matchups_lede(sides)}


def game_paths(cond: pl.DataFrame | None, g: dict) -> dict | None:
    """`paths`: how the underdog wins, as of the game's week; None without a line or a dog."""
    from nfl import paths as upset

    if cond is None:
        return None
    p = upset.upset_paths(g, int(g["week"]), cond)
    return None if p is None else p.to_dict()


def game_paths_outcome(cond: pl.DataFrame | None, g: dict) -> dict | None:
    """`paths_outcome`: for a finished game, which conditions the dog met and how it ended."""
    from nfl import paths as upset

    if cond is None or g.get("result") is None:
        return None
    o = upset.paths_outcome(g["game_id"], cond)
    return None if o is None else o.to_dict()


_LEAGUE_CACHE: dict[int, dict] = {}


def _league_rates(tend: pl.DataFrame, season: int) -> dict:
    """(side, situation, metric) -> play-weighted league average rate for the season."""
    if season not in _LEAGUE_CACHE:
        lg = (
            tend.filter(pl.col("season") == season)
            .group_by("side", "situation", "metric")
            .agg(((pl.col("rate") * pl.col("n")).sum() / pl.col("n").sum()).alias("lg"))
        )
        _LEAGUE_CACHE[season] = {
            (r["side"], r["situation"], r["metric"]): r["lg"] for r in lg.iter_rows(named=True)
        }
    return _LEAGUE_CACHE[season]


def _tendencies(tend: pl.DataFrame, g: dict) -> list[dict]:
    if tend.is_empty():
        return []
    from nfl.models.elo import TEAM_ALIASES

    teams = {g["home_team"]: "home", g["away_team"]: "away"}
    canon = {TEAM_ALIASES.get(t, t): side for t, side in teams.items()}
    league = _league_rates(tend, g["season"])
    t = tend.filter(
        (pl.col("season") == g["season"]) & pl.col("situation").is_in(TENDENCY_SITUATIONS)
        & pl.col("team").replace(TEAM_ALIASES).is_in(list(canon))
    )  # fmt: skip
    return [
        {"team_side": canon[TEAM_ALIASES.get(r["team"], r["team"])],
         "side": r["side"], "situation": r["situation"], "metric": r["metric"],
         "rate": _r(r["rate"]), "raw_rate": _r(r.get("raw_rate")), "n": r["n"],
         "league_rate": _r(league.get((r["side"], r["situation"], r["metric"])))}
        for r in t.iter_rows(named=True)
    ]  # fmt: skip


def _injuries(paths: Paths, season: int) -> list[dict]:
    import duckdb

    d = paths.curated_table("injuries") / f"season={season}"
    if not d.exists():
        return []
    df = duckdb.sql(
        f"select week, team, gsis_id, full_name, position, report_status, practice_status, report_primary_injury "
        f"from read_parquet('{d.as_posix()}/*.parquet') where report_status is not null"
    ).pl()
    return [
        {"week": r["week"], "team": r["team"], "gsis_id": r["gsis_id"], "player": r["full_name"], "pos": r["position"],
         "status": r["report_status"], "practice": r["practice_status"], "injury": r["report_primary_injury"]}
        for r in df.iter_rows(named=True)
    ]  # fmt: skip


# --------------------------------------------------------------------------------- player claims


def _player_claims(paths: Paths, games: pl.DataFrame, season: int):
    """(claims, game_id -> key players, the tracker block) for the season (ADR 0027, M24.4)."""
    from nfl.players import claims as pc

    c = pc.load(paths).filter(pl.col("season") == season)
    results = {
        r["game_id"]: r["result"]
        for r in games.filter(pl.col("result").is_not_null()).iter_rows(named=True)
    }
    passes = pc.load_passes(paths).filter(pl.col("season") == season)
    return (c, passes), pc.key_players(c, passes), pc.record(c, pc.load_grades(paths), results)


def _availability(paths: Paths, season: int, week: int, claims: tuple | None) -> dict:
    """team -> its availability panel for `week` (ADR 0027): top starters by value and statuses."""
    from nfl.players import claims as pc
    from nfl.players.value import week_values

    values = week_values(paths, season, [week])
    if values.is_empty():
        return {}
    c, passes = claims or (pl.DataFrame(schema=pc.SCHEMA), pl.DataFrame(schema=pc.PASS_SCHEMA))
    return {t: pc.availability(values, c, passes, t) for t in values["team"].unique().to_list()}


def _lineups(paths: Paths, games: pl.DataFrame, season: int, injuries: list[dict], now) -> dict:
    """game_id -> {home, away} formation-map lineups for the unplayed games of the next two weeks
    (ADR 0027, M24.5; two so Monday, before the last game of a week, already maps the next): the
    latest depth chart before now, values, the game week's statuses. Context, never a lock."""
    import duckdb

    from nfl.players import claims as pc
    from nfl.players import lineup
    from nfl.players.value import week_values

    upcoming = games.filter(pl.col("kickoff_utc") > now)
    chart_dir = paths.curated_table("depth_charts") / f"season={season}"
    if upcoming.is_empty() or not any(chart_dir.glob("*.parquet")):
        return {}
    weeks = sorted(upcoming["week"].unique().to_list())[:2]
    depth = duckdb.sql(
        "select team, dt, pos_grp, pos_abb, cast(pos_slot as bigint) as pos_slot, "
        "cast(pos_rank as bigint) as pos_rank, gsis_id, player_name "
        f"from read_parquet('{chart_dir.as_posix()}/*.parquet', union_by_name=true) "
        "where dt is not null"
    ).pl()
    values = week_values(paths, season, weeks)
    if values.is_empty():
        return {}
    rates = pc.play_rates(pc.rate_table(paths))
    wk = upcoming.filter(pl.col("week").is_in(weeks))
    return lineup.lineups(wk, depth, values, injuries, rates, now)


# ---------------------------------------------------------------------------------------- tracker


def tracker(paths: Paths, season: int, reg: dict) -> dict:
    sc = _read(paths, "scorecard")
    graded = _read(paths, "graded")
    summ = _read(paths, "summary")
    rel = _read(paths, "reliability")
    div = _read(paths, "divergence")
    settled = _read(paths, "bets_settled")
    out: dict = {"schema_version": SCHEMA_VERSION, "season": season}
    if not sc.is_empty():
        s = sc.filter((pl.col("scope") == "season") & pl.col("model_id").is_in(list(reg)))
        out["seasons"] = [
            {"season": r["season"], "model_id": r["model_id"], "n": r["n_games"], "log_loss": _r(r["log_loss"]),
             "brier": _r(r["brier"]), "ece": _r(r.get("ece")), "spread_mae": _r(r["spread_mae"], 2)}
            for r in s.sort("season", "model_id").iter_rows(named=True)
        ]  # fmt: skip
    if not graded.is_empty():
        cur = graded.filter((pl.col("season") == season) & pl.col("model_id").is_in(list(reg)))
        wk = (
            cur.group_by("model_id", "week").agg(pl.col("log_loss").sum().alias("s"), pl.len().alias("n"),
                                                 (~pl.col("is_backfill")).any().alias("live"),
                                                 (~pl.col("is_backfill")).sum().alias("n_live"))
            .sort("model_id", "week")
            .with_columns((pl.col("s").cum_sum() / pl.col("n").cum_sum()).over("model_id").alias("cum"))
        )  # fmt: skip
        out["current_season"] = [
            {"model_id": r["model_id"], "week": r["week"], "n": r["n"], "cum_log_loss": _r(r["cum"]), "live": r["live"], "n_live": r["n_live"]}
            for r in wk.iter_rows(named=True)
        ]  # fmt: skip
        live = graded.filter(~pl.col("is_backfill"))
        out["weeks_tracked"] = {
            r["model_id"]: r["weeks"]
            for r in live.group_by("model_id").agg(pl.concat_str(["season", "week"]).n_unique().alias("weeks")).iter_rows(named=True)
        }  # fmt: skip
    if not summ.is_empty():
        out["backtest"] = [
            {k: (_r(v) if isinstance(v, float) else v) for k, v in r.items()}
            for r in summ.filter(pl.col("model_id").is_in(list(reg))).iter_rows(named=True)
        ]
    if not rel.is_empty():
        agg = (
            rel.filter(pl.col("model_id").is_in(list(reg)))
            .group_by("model_id", "bin")
            .agg(pl.col("n").sum(), ((pl.col("mean_p") * pl.col("n")).sum() / pl.col("n").sum()).alias("mean_p"),
                 ((pl.col("hit_rate") * pl.col("n")).sum() / pl.col("n").sum()).alias("hit_rate"))
            .sort("model_id", "bin")
        )  # fmt: skip
        out["reliability"] = [
            {"model_id": r["model_id"], "bin": int(r["bin"]), "n": r["n"], "mean_p": _r(r["mean_p"]), "hit_rate": _r(r["hit_rate"])}
            for r in agg.iter_rows(named=True)
        ]  # fmt: skip
    if not div.is_empty():
        out["divergence"] = [
            {k: (_r(v) if isinstance(v, float) else v) for k, v in r.items()}
            for r in div.filter(pl.col("model_id").is_in(list(reg))).iter_rows(named=True)
        ]
    out["ledger"] = []  # the contract requires the key, so an empty ledger can't error the page
    if not settled.is_empty():
        from nfl import ledger

        keep = pl.col("model_id").is_in(list(reg))
        out["ledger"] = [
            {"model_id": r["model_id"], "kind": BACKFILL if r["is_backfill"] else "live", "bets": r["bets"],
             "wins": r["wins"], "losses": r["losses"], "pushes": r["pushes"], "units": _r(r["units"], 2),
             "roi": _r(r["roi"]), "roi_lo": _r(r["roi_lo"]), "roi_hi": _r(r["roi_hi"]),
             "no_edge_roi": _r(r["no_edge_roi"]), "win_rate": _r(r["win_rate"]),
             "need_rate": _r(r["need_rate"]), "clv": _r(r["clv"])}
            for r in ledger.line_stats(settled).filter(keep).iter_rows(named=True)
        ]  # fmt: skip
        out["ledger_seasons"] = [
            {"model_id": r["model_id"], "season": r["season"], "bets": r["bets"], "live_bets": r["live_bets"],
             "units": _r(r["units"], 2), "no_edge_units": _r(r["no_edge_units"], 2)}
            for r in ledger.season_stats(settled).filter(keep).iter_rows(named=True)
        ]  # fmt: skip
    return out


def audit(paths: Paths) -> dict:
    a = _read(paths, "audit")
    out = {"schema_version": SCHEMA_VERSION, "freshness": freshness(paths)}
    if not a.is_empty():
        out["null_rates"] = [
            {k: (_r(v) if isinstance(v, float) else v) for k, v in r.items()}
            for r in a.iter_rows(named=True)
        ]
    return out
