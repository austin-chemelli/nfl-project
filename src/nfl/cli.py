"""`nfl` command line. Each subcommand is one pipeline job; jobs are composable and idempotent."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from nfl.config import get_paths

app = typer.Typer(no_args_is_help=True, help="NFL matchup breakdown and predictor (POC).")
console = Console()


def _parse_range(s: str | None) -> tuple[int, int] | None:
    if not s:
        return None
    lo, _, hi = s.partition("-")
    return int(lo), int(hi or lo)


@app.command()
def ingest(
    datasets: str = typer.Option(None, help="Comma-separated subset, e.g. 'schedules,pbp'."),
    pbp: str = typer.Option(None, help="Season range for pbp, e.g. 2010-2026."),
    ftn: str = typer.Option(None, help="Season range for FTN charting."),
    injuries: str = typer.Option(None, help="Season range for injuries."),
    depth_charts: str = typer.Option(None, help="Season range for depth charts."),
    force: bool = typer.Option(False, help="Re-download even if present and unchanged."),
) -> None:
    """Download upstream nflverse files into raw snapshots."""
    from nfl.ingest import ingest as run

    seasons = {
        k: v
        for k, v in {
            "pbp": _parse_range(pbp),
            "ftn_charting": _parse_range(ftn),
            "injuries": _parse_range(injuries),
            "depth_charts": _parse_range(depth_charts),
        }.items()
        if v
    }
    ds = datasets.split(",") if datasets else None
    results = run(get_paths(), ds, seasons, force)
    counts: dict[str, int] = {}
    for _, _, status in results:
        counts[status] = counts.get(status, 0) + 1
    for ds_name, season, status in results:
        if status.startswith("http") or status == "written":
            console.print(f"  {ds_name} {season or ''}: {status}")
    console.print(f"[bold]ingest:[/bold] {counts}")


@app.command()
def curate(
    seasons: str = typer.Option(None, help="Season range to rebuild, default all present."),
) -> None:
    """Build curated tables (games, plays, injuries, depth_charts) from the latest raw snapshots."""
    from nfl.curate import curate as run

    summary = run(get_paths(), _parse_range(seasons))
    t = Table("table", "season", "rows")
    for table, season, n in summary:
        t.add_row(table, str(season), f"{n:,}")
    console.print(t)


@app.command()
def audit(season: int = typer.Option(None, help="Single season to show; default all.")) -> None:
    """Null-rate audit of curated columns per season. Writes marts/audit.parquet."""
    from nfl.audit import audit as run

    run(get_paths(), console, season)


@app.command()
def tendencies() -> None:
    """Aggregate team tendencies (offense and defense) per season and situation."""
    from nfl.tendencies import build as run

    n = run(get_paths())
    console.print(f"[bold]tendencies:[/bold] {n:,} rows -> marts/tendencies.parquet")


@app.command()
def predict(
    seasons: str = typer.Option("2025-2026", help="Seasons to predict (walk-forward)."),
    backfill: bool = typer.Option(
        False, help="Score the approaches on completed games (needs `nfl fit`); default 2005-2025."
    ),
) -> None:
    """Reference models (market, Elo, naive), or with --backfill the approaches + ensemble."""
    if backfill:
        from nfl.approaches.run import backfill as run_backfill

        rng = _parse_range(seasons) if seasons != "2025-2026" else (2005, 2025)
        n = run_backfill(get_paths(), rng)
        console.print(f"[bold]predict --backfill:[/bold] {n:,} approach rows written {rng}")
        return
    from nfl.predict import predict as run

    n = run(get_paths(), _parse_range(seasons))
    console.print(f"[bold]predict:[/bold] {n:,} prediction rows appended")


@app.command()
def fit(
    seasons: str = typer.Option("2005-2026", help="Seasons to produce walk-forward fits for."),
) -> None:
    """Select λ and write walk-forward fit artifacts for every approach and the global fit."""
    from nfl.approaches.run import fit_all

    table = fit_all(get_paths(), _parse_range(seasons))
    t = Table(title="fit: validation log loss by λ (2022-2024)")
    for col in ("approach", "λ", "val log loss", "n", ""):
        t.add_column(col)
    for row in table.iter_rows(named=True):
        t.add_row(
            row["approach"],
            f"{row['lambda']:g}",
            f"{row['val_log_loss']:.4f}",
            str(row["n"]),
            "chosen" if row["chosen"] else "",
        )
    console.print(t)


odds_app = typer.Typer(
    no_args_is_help=True, help="The Odds API snapshots (free tier: 500 credits/mo)."
)
app.add_typer(odds_app, name="odds")


@odds_app.command("snapshot")
def odds_snapshot() -> None:
    """Fetch current NFL lines (3 credits) and rebuild curated/lines."""
    from nfl import odds
    from nfl.features.store import games_frame

    paths = get_paths()
    m = odds.snapshot(paths)
    n = odds.curate_lines(paths, games_frame(paths))
    console.print(
        f"[bold]odds:[/bold] {m.n_events} events at {m.snapshot_ts}; {n:,} line rows; "
        f"credits used {m.requests_used}, remaining {m.requests_remaining}"
    )


@odds_app.command("status")
def odds_status() -> None:
    """Credits used this month and snapshots on disk (no API call)."""
    from nfl import odds

    paths = get_paths()
    snaps = sorted(odds.raw_dir(paths, "live").glob("snapshot_ts=*"))
    console.print(
        f"snapshots: {len(snaps)} (latest {snaps[-1].name.split('=')[1] if snaps else '-'}); "
        f"credits used (last call): {odds.last_usage(paths)}; soft cap {odds.MONTHLY_SOFT_CAP}"
    )


@app.command("ledger")
def ledger_cmd(
    season_from: int = typer.Option(2022, help="First season to print in the summary."),
) -> None:
    """Open paper bets at each model's last lock, settle completed ones, print the record."""
    import polars as pl

    from nfl import ledger

    paths = get_paths()
    live, back = ledger.open_bets(paths)
    settled = ledger.settle(paths)
    summ = ledger.summary(settled)
    summ.write_parquet(paths.marts / "ledger_summary.parquet")
    console.print(f"[bold]ledger:[/bold] {live} new live bets, {back:,} backfill bets (derived)")
    agg = (
        summ.filter(pl.col("season") >= season_from)
        .group_by("model_id", "is_backfill")
        .agg(
            pl.col("bets").sum(),
            pl.col("wins").sum(),
            pl.col("losses").sum(),
            pl.col("units").sum(),
            (pl.col("units").sum() / pl.col("bets").sum()).alias("roi"),
            pl.when(pl.col("n_clv").sum() > 0)
            .then((pl.col("mean_clv").fill_null(0) * pl.col("n_clv")).sum() / pl.col("n_clv").sum())
            .alias("clv"),
        )
        .sort("is_backfill", "roi", descending=[False, True])
    )
    t = Table(title=f"paper ledger, {season_from}+ (1 unit flat; backfill uses nflverse lines)")
    for col in ("model", "kind", "bets", "W-L", "units", "ROI", "CLV"):
        t.add_column(col, justify="right")
    for r in agg.iter_rows(named=True):
        t.add_row(
            r["model_id"],
            "backfill" if r["is_backfill"] else "live",
            str(r["bets"]),
            f"{r['wins']}-{r['losses']}",
            f"{r['units']:+.1f}",
            f"{r['roi']:+.1%}",
            f"{r['clv']:+.3f}" if r["clv"] is not None else "-",
        )
    console.print(t)


narrative_app = typer.Typer(no_args_is_help=True, help="Narrative records (LLM research contract).")
app.add_typer(narrative_app, name="narrative")


@narrative_app.command("slate")
def narrative_slate(season: int, week: int) -> None:
    """Games to research this week with kickoff (UTC), venue, current line, QBs and coaches."""
    from nfl.llm.narrative import slate

    df = slate(get_paths(), season, week)
    t = Table(title=f"{season} week {week}: {df.height} games")
    for c in df.columns:
        t.add_column(c)
    for row in df.iter_rows():
        t.add_row(*["" if v is None else str(v) for v in row])
    console.print(t)


@narrative_app.command("ingest")
def narrative_ingest(file: str) -> None:
    """Validate a narrative record JSON and store it under marts/narrative/."""
    from pathlib import Path

    from nfl.llm.narrative import ingest

    out = ingest(get_paths(), Path(file))
    console.print(f"[bold]narrative:[/bold] stored {out}")


@narrative_app.command("example")
def narrative_example() -> None:
    """Print a complete, valid example record (the schema by example)."""
    import json

    from nfl.llm.narrative import example

    print(json.dumps(example(), indent=1))


@narrative_app.command("list")
def narrative_list(season: int = typer.Option(None)) -> None:
    """Records on disk: game, producer, known_as_of, claims."""
    from nfl.llm.narrative import load_records

    recs = load_records(get_paths(), (season, season) if season else None)
    t = Table(title=f"{len(recs)} narrative records")
    for c in ("game_id", "producer", "model", "known_as_of", "claims", "prompt"):
        t.add_column(c)
    for r in recs:
        t.add_row(
            r.game_id, r.producer, r.model, str(r.known_as_of), str(len(r.claims)), r.prompt_version
        )
    console.print(t)


@app.command("readme")
def readme_cmd() -> None:
    """Rewrite the README scorecard section from the marts (run after `nfl grade`)."""
    from pathlib import Path

    from nfl.readme import update

    changed = update(get_paths(), Path("README.md"))
    console.print("README scorecard " + ("updated" if changed else "unchanged"))


@app.command("lock")
def lock_cmd(
    slot: str = typer.Option(..., help="thu (Wed-Fri kickoffs) or sat (Sat-Mon kickoffs)."),
    season: int = typer.Option(None, help="Default: the week of the next game."),
    week: int = typer.Option(None),
    dry_run: bool = typer.Option(False, help="Compute and write to marts/dryrun/ only."),
    refresh: bool = typer.Option(True, help="Ingest + odds + curate + features first."),
    odds: bool = typer.Option(True, help="Take an Odds API snapshot (3 credits) during refresh."),
    commit: bool = typer.Option(False, help="Commit the public lock file (only that file)."),
    push: bool = typer.Option(False, help="Push, only if every unpushed commit is a lock commit."),
) -> None:
    """Lock predictions for one slot of a week: record, publish, optionally commit and push."""
    from nfl.lock import run

    if push and not commit:
        raise typer.BadParameter("--push requires --commit")
    res = run(get_paths(), slot, season, week, dry_run=dry_run, do_refresh=refresh, odds=odds,
              commit=commit, push=push)  # fmt: skip
    if res.games.is_empty():
        console.print(
            f"[yellow]lock: no {slot} games left to lock in {res.season} week {res.week}[/]"
        )
        return
    show = ["market_baseline", "traditionalist.fitted", "analyst.fitted", "sharp.persona",
            "student.fitted", "ensemble", "elo_v0"]  # fmt: skip
    t = Table(title=f"{'DRY RUN ' if dry_run else ''}lock {res.season} W{res.week:02d} {slot} "
                    f"at {res.lock_ts:%Y-%m-%d %H:%M}Z: P(home win)")  # fmt: skip
    t.add_column("game")
    for m in show:
        t.add_column(
            m.replace(".fitted", "").replace(".persona", " (p)").replace("_baseline", ""),
            justify="right",
        )
    by = {
        s.model_id: dict(zip(s.frame["game_id"], s.frame["p_home"], strict=True))
        for s in res.scored
    }
    for g in res.games.iter_rows(named=True):
        cells = [
            f"{by.get(m, {}).get(g['game_id']):.2f}"
            if by.get(m, {}).get(g["game_id"]) is not None
            else "-"
            for m in show
        ]
        t.add_row(f"{g['away_team']} @ {g['home_team']}", *cells)
    console.print(t)
    console.print(f"artifact: {res.artifact_path}")
    if not dry_run:
        console.print(
            f"predictions appended for {len(res.scored)} models; live bets opened: {res.bets_opened}"
        )
        console.print(
            "committed" + (" and pushed" if push else "")
            if commit
            else "not committed (use --commit)"
        )


weekly_app = typer.Typer(no_args_is_help=True, help="The weekly jobs (see docs/runbook.md).")
app.add_typer(weekly_app, name="weekly")


@weekly_app.command("refresh")
def weekly_refresh(
    odds: bool = typer.Option(True, help="Take an Odds API snapshot (3 credits)."),
) -> None:
    """Current-season ingest, odds, curate, tendencies, features, grade, ledger. No refit."""
    from nfl.weekly import refresh

    refresh(get_paths(), console, odds=odds)


@app.command()
def features(
    seasons: str = typer.Option("1999-2026", help="Season range to write, e.g. 1999-2026."),
    families: str = typer.Option(None, help="Comma-separated subset, e.g. 'strength,form'."),
) -> None:
    """Build feature families into marts/features/ (upsert; idempotent)."""
    from nfl.features.build import build_all

    rep = build_all(
        get_paths(),
        _parse_range(seasons),
        families.split(",") if families else None,
    )
    t = Table(title="features")
    for c in ("family", "feature", "rows", "null %", "s"):
        t.add_column(c, justify="right" if c in ("rows", "null %", "s") else "left")
    for fam, feat, n, null_share, secs, _ in rep.iter_rows():
        t.add_row(fam, feat, f"{n:,}", f"{null_share:.1%}", f"{secs:.1f}")
    console.print(t)
    if rep.height and rep["missing_builders"][0]:
        console.print(f"[yellow]builders not present yet: {rep['missing_builders'][0]}[/]")


@app.command()
def grade() -> None:
    """Grade completed games, write marts/scorecard.parquet, and export site JSON."""
    from nfl.grade import grade as run

    run(get_paths(), console)


@app.command()
def ui() -> None:
    """Launch the Streamlit explorer (disposable POC UI)."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], check=False)


@app.command()
def run_all() -> None:
    """ingest -> curate -> audit -> tendencies -> predict -> grade."""
    from nfl.audit import audit as run_audit
    from nfl.curate import curate as run_curate
    from nfl.grade import grade as run_grade
    from nfl.ingest import ingest as run_ingest
    from nfl.predict import predict as run_predict
    from nfl.tendencies import build as run_tendencies

    paths = get_paths()
    console.rule("ingest")
    run_ingest(paths)
    console.rule("curate")
    run_curate(paths)
    console.rule("audit")
    run_audit(paths, console)
    console.rule("tendencies")
    run_tendencies(paths)
    console.rule("predict")
    run_predict(paths, (2022, 2026))
    console.rule("grade")
    run_grade(paths, console)
