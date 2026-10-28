"""`nfl lock`: the live, public, timestamped prediction run (architecture §4.2, ADR 0005/0010).

One lock = one slot of one week:
  thu  games kicking off Wednesday-Friday (Eastern): Thursday night, occasional Wed/Fri games
  sat  games kicking off Saturday-Tuesday (Eastern): Saturday, Sunday incl. international, Monday

Steps (`run`):
  1. refresh  current-season nflverse data (idempotent ingest), an Odds API snapshot (3 credits),
              curate (incl. lines), all feature families stamped with this build time
  2. score    every approach flavor with the frozen fits trained through season − 1, the global fit,
              the ensemble, and the reference models (market = vig-free moneyline as of the lock,
              Elo walked over every completed game, naive); features as of lock_ts strictly
  3. record   append prediction rows (is_backfill=false, slot, lock_ts), open paper bets
  4. publish  public/predictions/<season>/week_<ww>_<slot>_<lock ts>.json (+ .sha256), sorted keys
  5. commit / push (opt-in): commit only that file; push only if every unpushed commit is a lock
              commit (Austin's standing permission covers lock-only pushes)

A lock never touches games that have kicked off. Re-running a slot appends new rows and writes a new
file; grading uses the last lock before kickoff. `--dry-run` does 1–2 and writes the artifact under
marts/dryrun/ only: no appends, no bets, no commit.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from nfl.approaches import ensemble, fit
from nfl.approaches.engine import Model
from nfl.approaches.schema import load_all
from nfl.config import Paths, now_utc
from nfl.features import store
from nfl.models import elo as elo_model
from nfl.models import naive
from nfl.predict import PRED_SCHEMA, append_rows

ET = ZoneInfo("America/New_York")
SLOTS = {"thu": {2, 3, 4}, "sat": {5, 6, 0, 1}}  # Python weekday(): Mon=0 ... Sun=6
ARTIFACT_SCHEMA = "1"
PUBLIC_DIR = Path("public") / "predictions"
LOCK_PREFIX = "lock: "


# ---------------------------------------------------------------------------------------- slate


def slot_games(
    games: pl.DataFrame, season: int, week: int, slot: str, lock_ts: datetime
) -> pl.DataFrame:
    """The slot's games that have not kicked off at lock_ts (naive UTC)."""
    if slot not in SLOTS:
        raise ValueError(f"slot must be one of {sorted(SLOTS)}")
    g = games.filter((pl.col("season") == season) & (pl.col("week") == week)).with_columns(
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us"))
    )
    days = [
        k.replace(tzinfo=ZoneInfo("UTC")).astimezone(ET).weekday() if k is not None else None
        for k in g["kickoff_utc"].to_list()
    ]
    g = g.with_columns(pl.Series("_wd", days, dtype=pl.Int64))
    return (
        g.filter(pl.col("_wd").is_in(sorted(SLOTS[slot])) & (pl.col("kickoff_utc") > lock_ts))
        .drop("_wd")
        .sort("kickoff_utc", "game_id")
    )


def next_week(games: pl.DataFrame, now: datetime) -> tuple[int, int]:
    """(season, week) of the earliest game that hasn't kicked off."""
    up = games.filter(pl.col("kickoff_utc").dt.replace_time_zone(None) > now).sort("kickoff_utc")
    if up.is_empty():
        raise ValueError("no upcoming games in the schedule")
    return int(up["season"][0]), int(up["week"][0])


# --------------------------------------------------------------------------------------- scoring


@dataclass
class Scored:
    """One model's predictions for the slot."""

    model_id: str
    version: str
    frame: pl.DataFrame  # game_id, p_home, spread_home, logit?, contributions?


@dataclass
class LockResult:
    season: int
    week: int
    slot: str
    lock_ts: datetime
    games: pl.DataFrame
    scored: list[Scored] = field(default_factory=list)
    market: pl.DataFrame | None = None
    artifact: dict | None = None
    artifact_path: Path | None = None
    bets_opened: int = 0


def load_models(
    paths: Paths, trained_through: int
) -> tuple[list[tuple[str, Model, bool]], list[str]]:
    """[(model_id, model, is_ensemble_member)]: the one public line per approach + global."""
    out, missing = [], []
    for a in [*load_all().values()]:
        if a.id == "narrative":
            continue
        try:
            m = fit.load(paths, a.id, trained_through)
        except FileNotFoundError:
            missing.append(a.id)
            continue
        if m.meta.get("config_hash") != fit.config_hash(a):
            raise RuntimeError(
                f"{a.id}: the YAML changed since its fit (config hash mismatch); run `nfl fit` "
                "before locking, or the lock would publish stale weights"
            )
        out.append((a.id, m, not a.shadow))
    try:
        out.append(
            (ensemble.GLOBAL_ID, fit.load(paths, ensemble.GLOBAL_ID, trained_through), False)
        )
    except FileNotFoundError:
        missing.append(ensemble.GLOBAL_ID)
    return out, missing


def score_approaches(
    models: list[tuple[str, Model, bool]],
    feats_long: pl.DataFrame,
    slate: pl.DataFrame,
    lock_ts: datetime,
) -> list[Scored]:
    """Pure: score the slate with each model using feature rows known strictly before lock_ts."""
    asof = store.as_of(
        feats_long.filter(pl.col("game_id").is_in(slate["game_id"].to_list())), lock_ts
    )
    vec = store.game_vectors(asof)
    ids = slate.select("game_id")
    out, members = [], []
    for mid, m, member in models:
        wide = ids.join(store.to_wide(vec, m.features), on="game_id", how="left")
        sc = m.score(wide)
        out.append(Scored(mid, f"{m.meta.get('config_hash', '')}", sc))
        if member:
            members.append(sc)
    if members:
        out.append(Scored(ensemble.ENSEMBLE_ID, "mean-public", ensemble.combine(members)))
    return out


def market_at(feats_long: pl.DataFrame, slate: pl.DataFrame, lock_ts: datetime) -> pl.DataFrame:
    """game_id, p_home (vig-free), spread_home, total, as_of, source: the market as of the lock."""
    m = store.as_of(
        feats_long.filter(
            pl.col("game_id").is_in(slate["game_id"].to_list())
            & pl.col("feature").is_in(
                ["market.p_home_vigfree", "market.spread_line", "market.total_line"]
            )
        ),
        lock_ts,
    )
    if m.is_empty():
        return pl.DataFrame(
            schema={"game_id": pl.Utf8, "p_home": pl.Float64, "spread_home": pl.Float64,
                    "total": pl.Float64, "as_of": pl.Datetime("us"), "source": pl.Utf8}
        )  # fmt: skip
    wide = m.pivot(on="feature", index="game_id", values="value", aggregate_function="first")
    meta = m.group_by("game_id").agg(
        pl.col("known_as_of").max().alias("as_of"), pl.col("source").first()
    )
    return wide.join(meta, on="game_id").select(
        "game_id",
        pl.col("market.p_home_vigfree").alias("p_home"),
        pl.col("market.spread_line").alias("spread_home"),
        pl.col("market.total_line").alias("total"),
        "as_of",
        "source",
    )


def score_reference(games: pl.DataFrame, slate: pl.DataFrame, market: pl.DataFrame) -> list[Scored]:
    """Market (vig-free moneyline as of the lock), Elo over all completed games, naive home."""
    from nfl.models import market as market_model

    out = []
    if not market.is_empty():
        mk = (
            slate.select("game_id")
            .join(market, on="game_id", how="inner")
            .filter(pl.col("p_home").is_not_null())
        )
        out.append(
            Scored(
                market_model.MODEL_ID,
                market_model.MODEL_VERSION,
                mk.select("game_id", "p_home", "spread_home", "total"),
            )
        )
    e = elo_model.Elo()
    done = games.filter(pl.col("result").is_not_null()).sort("kickoff_utc", "game_id")
    for g in done.iter_rows(named=True):
        e.new_season(g["season"])
        e.update(g["home_team"], g["away_team"], g["result"], (g["location"] or "Home") != "Home")
    rows = []
    for g in slate.iter_rows(named=True):
        e.new_season(g["season"])
        p = e.predict(g["home_team"], g["away_team"], (g["location"] or "Home") != "Home")
        rows.append((g["game_id"], p["p_home"], p["spread_home"]))
    out.append(Scored(elo_model.MODEL_ID, elo_model.MODEL_VERSION,
                      pl.DataFrame(rows, schema=["game_id", "p_home", "spread_home"], orient="row")))  # fmt: skip
    nv = naive.predict(None)
    out.append(
        Scored(
            naive.MODEL_ID,
            naive.MODEL_VERSION,
            slate.select("game_id").with_columns(
                pl.lit(nv["p_home"]).alias("p_home"), pl.lit(nv["spread_home"]).alias("spread_home")
            ),
        )
    )
    return out


# ------------------------------------------------------------------------------------- recording


def prediction_rows(res: LockResult, data_snapshot: str, sha: str) -> pl.DataFrame:
    parts = []
    base = res.games.select(
        "game_id", pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64), "total_line"
    )
    for s in res.scored:
        f = s.frame
        for c, t in (("contributions", pl.Utf8), ("total", pl.Float64)):
            if c not in f.columns:
                f = f.with_columns(pl.lit(None, dtype=t).alias(c))
        parts.append(
            base.join(
                f.select("game_id", "p_home", "spread_home", "total", "contributions"), on="game_id"
            )
            .select(
                "game_id",
                "season",
                "week",
                pl.lit(s.model_id).alias("model_id"),
                pl.lit(f"{sha}+{s.version}").alias("model_version"),
                pl.lit(res.lock_ts, dtype=pl.Datetime("us")).alias("lock_ts"),
                pl.lit(data_snapshot).alias("data_snapshot_ts"),
                "p_home",
                "spread_home",
                pl.coalesce(pl.col("total"), pl.col("total_line").cast(pl.Float64)).alias("total"),
                pl.lit(13.5).alias("sd_margin"),
                pl.lit(False).alias("is_backfill"),
                pl.lit(res.slot).alias("slot"),
                "contributions",
            )
            .cast(PRED_SCHEMA)
        )
    return pl.concat(parts) if parts else pl.DataFrame(schema=PRED_SCHEMA)


def build_artifact(
    res: LockResult, sha: str, data_snapshot: str, odds_snapshot: str | None
) -> dict:
    """The public record. Rounded to 4 decimals so it reads cleanly; the parquet keeps full precision."""
    by_game: dict[str, dict] = {}
    for g in res.games.iter_rows(named=True):
        by_game[g["game_id"]] = {
            "game_id": g["game_id"],
            "kickoff_utc": g["kickoff_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "away": g["away_team"],
            "home": g["home_team"],
            "market": None,
            "models": {},
        }
    if res.market is not None:
        for m in res.market.iter_rows(named=True):
            if m["game_id"] in by_game:
                by_game[m["game_id"]]["market"] = {
                    "p_home_vigfree": _r(m["p_home"]),
                    "spread_home": _r(m["spread_home"]),
                    "total": _r(m["total"]),
                    "as_of": m["as_of"].strftime("%Y-%m-%dT%H:%M:%SZ") if m["as_of"] else None,
                    "source": m["source"],
                }
    for s in res.scored:
        for r in s.frame.iter_rows(named=True):
            if r["game_id"] in by_game:
                by_game[r["game_id"]]["models"][s.model_id] = {
                    "p_home": _r(r["p_home"]),
                    "spread_home": _r(r["spread_home"]),
                }
    return {
        "schema_version": ARTIFACT_SCHEMA,
        "season": res.season,
        "week": res.week,
        "slot": res.slot,
        "lock_ts": res.lock_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_version": sha,
        "data_snapshot": data_snapshot,
        "odds_snapshot": odds_snapshot,
        "conventions": "p_home = home win probability; spread_home > 0 = home favored (points)",
        "games": [
            by_game[k] for k in sorted(by_game, key=lambda k: (by_game[k]["kickoff_utc"], k))
        ],
    }


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), 4)


def write_artifact(root: Path, art: dict) -> tuple[Path, str]:
    """Deterministic JSON + its SHA-256 next to it. Returns (path, hex digest)."""
    stamp = art["lock_ts"].replace("-", "").replace(":", "")
    d = root / str(art["season"])
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"week_{art['week']:02d}_{art['slot']}_{stamp}.json"
    body = (json.dumps(art, indent=1, sort_keys=True) + "\n").encode()
    path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    path.with_suffix(".json.sha256").write_text(f"{digest}  {path.name}\n")
    return path, digest


# ------------------------------------------------------------------------------------------ git


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def commit_lock(repo: Path, files: list[Path], message: str) -> str:
    """Commit exactly `files`. Refuses if anything else is staged. Returns the new short sha."""
    staged = [l for l in _git("diff", "--cached", "--name-only", cwd=repo).splitlines() if l]
    rel = {str(f.resolve().relative_to(repo.resolve())) for f in files}
    other = [s for s in staged if s not in rel]
    if other:
        raise RuntimeError(f"refusing to commit a lock: other files are staged: {other[:5]}")
    _git("add", "--", *sorted(rel), cwd=repo)
    _git("commit", "-m", message, "--", *sorted(rel), cwd=repo)
    return _git("rev-parse", "--short", "HEAD", cwd=repo).strip()


def unpushed_non_lock_commits(repo: Path, remote_ref: str = "origin/main") -> list[str]:
    """Commits not on the remote that aren't pure lock commits (subject `lock: ...` and only files
    under public/predictions/)."""
    bad = []
    for sha in _git("rev-list", f"{remote_ref}..HEAD", cwd=repo).split():
        subject = _git("log", "-1", "--format=%s", sha, cwd=repo).strip()
        files = [
            f for f in _git("show", "--name-only", "--format=", sha, cwd=repo).splitlines() if f
        ]
        if not subject.startswith(LOCK_PREFIX) or any(
            not f.startswith(str(PUBLIC_DIR) + "/") for f in files
        ):
            bad.append(f"{sha[:7]} {subject}")
    return bad


def push_locks(repo: Path) -> None:
    _git("fetch", "-q", "origin", cwd=repo)
    bad = unpushed_non_lock_commits(repo)
    if bad:
        raise RuntimeError(
            "not pushing: unpushed commits other than lock commits (push them yourself first): "
            + "; ".join(bad[:5])
        )
    _git("push", "origin", "HEAD:main", cwd=repo)


# ------------------------------------------------------------------------------------------- run


def refresh(paths: Paths, season: int, odds: bool = True) -> str | None:
    """Current-season ingest + odds snapshot + curate + all features. Returns the odds snapshot ts."""
    from nfl.curate import curate
    from nfl.features.build import build_all
    from nfl.ingest import ingest

    ingest(
        paths,
        seasons={d: (season, season) for d in ("pbp", "ftn_charting", "injuries", "depth_charts")},
    )
    snap = None
    if odds:
        from nfl import odds as odds_mod

        snap = odds_mod.snapshot(paths).snapshot_ts
    curate(paths)
    build_all(paths)
    return snap


def run(
    paths: Paths,
    slot: str,
    season: int | None = None,
    week: int | None = None,
    *,
    dry_run: bool = False,
    do_refresh: bool = True,
    odds: bool = True,
    commit: bool = False,
    push: bool = False,
    repo: Path | None = None,
) -> LockResult:
    from nfl import ledger
    from nfl.approaches.run import git_sha

    repo = repo or Path.cwd()
    if commit and not dry_run:
        dirty = _git(
            "status", "--porcelain", "--", "src", "pyproject.toml", "uv.lock", cwd=repo
        ).strip()
        if dirty:
            raise RuntimeError(
                "refusing to commit a lock from uncommitted code (the artifact's code_version would "
                f"lie); commit first. Dirty: {dirty.splitlines()[:5]}"
            )
    games = store.games_frame(paths)
    now = now_utc().replace(tzinfo=None)
    if season is None or week is None:
        season, week = next_week(games, now)
    odds_snap = refresh(paths, season, odds=odds) if do_refresh else None
    games = store.games_frame(paths)
    lock_ts = now_utc().replace(tzinfo=None, microsecond=0)  # strictly after every feature stamp
    slate = slot_games(games, season, week, slot, lock_ts)
    res = LockResult(season, week, slot, lock_ts, slate)
    if slate.is_empty():
        return res

    feats = store.read_features(paths, seasons=(season, season))
    models, missing = load_models(paths, season - 1)
    if missing:
        raise RuntimeError(
            f"missing fit artifacts trained through {season - 1}: {missing} (run nfl fit)"
        )
    res.market = market_at(feats, slate, lock_ts)
    res.scored = score_approaches(models, feats, slate, lock_ts) + score_reference(
        games, slate, res.market
    )

    sha = git_sha()
    data_snap = _latest_raw_snapshot(paths)
    res.artifact = build_artifact(res, sha, data_snap, odds_snap)
    out_root = (paths.marts / "dryrun") if dry_run else (repo / PUBLIC_DIR)
    res.artifact_path, digest = write_artifact(out_root, res.artifact)
    if dry_run:
        return res

    append_rows(paths, prediction_rows(res, data_snap, sha))
    before = ledger.load_bets(paths).filter(~pl.col("is_backfill")).height
    ledger.open_bets(paths)
    res.bets_opened = ledger.load_bets(paths).filter(~pl.col("is_backfill")).height - before
    if commit:  # the public record first; nothing after this may block it (review 2026-10-28)
        msg = f"{LOCK_PREFIX}{season} W{week:02d} {slot}\n\nsha256 {digest}"
        commit_lock(repo, [res.artifact_path, res.artifact_path.with_suffix(".json.sha256")], msg)
        if push:
            push_locks(repo)
    try:
        from nfl.site import build as build_site

        build_site(
            paths, season
        )  # the UI shows the lock right away (statuses flip preview -> locked)
    except Exception as e:  # noqa: BLE001 - the lock is already recorded; the UI can be rebuilt
        warnings.warn(f"site rebuild after lock failed: {e!r}; run `nfl site`", stacklevel=2)
    return res


def _latest_raw_snapshot(paths: Paths) -> str:
    snaps = sorted(p.name.split("=", 1)[1] for p in paths.raw.glob("*/snapshot_ts=*"))
    return snaps[-1] if snaps else "unknown"
