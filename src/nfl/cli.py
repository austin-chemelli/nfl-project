"""`nfl` command line. Each subcommand is one pipeline job; jobs are composable and idempotent."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

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
        False, help="Score the approaches on completed games (needs `nfl fit`); default 2005-now."
    ),
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="With --backfill: just these approach ids (repeatable)."),
    ] = None,
) -> None:
    """Reference models (market, Elo, naive), or with --backfill the approaches."""
    if backfill:
        from nfl.approaches.run import backfill as run_backfill

        rng = _parse_range(seasons) if seasons != "2025-2026" else None
        n = run_backfill(get_paths(), rng, set(only) if only else None)
        console.print(
            f"[bold]predict --backfill:[/bold] {n:,} approach rows written {rng or 'all'}"
        )
        return
    from nfl.predict import predict as run

    n = run(get_paths(), _parse_range(seasons))
    console.print(f"[bold]predict:[/bold] {n:,} prediction rows appended")


@app.command()
def fit(
    seasons: str = typer.Option("2005-2026", help="Seasons to produce walk-forward fits for."),
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Just these approach ids (repeatable); the others' fits stay."),
    ] = None,
) -> None:
    """Select λ and write walk-forward fit artifacts for every approach and the global fit."""
    from nfl.approaches.run import fit_all

    table = fit_all(get_paths(), _parse_range(seasons), set(only) if only else None)
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


@narrative_app.command("run")
def narrative_run(
    season: int,
    week: int,
    game_ids: Annotated[
        list[str] | None, typer.Argument(help="Default: every game not yet kicked off.")
    ] = None,
    store: bool = typer.Option(True, help="Ingest the records (--no-store keeps drafts only)."),
) -> None:
    """Research games on the desktop model (search, fetch, extract, compose) and ingest them."""
    from nfl.llm.research import run_week

    runs = run_week(get_paths(), season, week, game_ids, store=store)
    t = Table(title=f"{season} week {week}: local narrative research")
    for c in ("game_id", "result", "pages kept", "facts", "dropped", "minutes"):
        t.add_column(c)
    for r in runs:
        t.add_row(
            r.game_id,
            "stored" if r.stored else ("ok (draft)" if r.ok else f"[red]{r.error}[/red]"),
            str(r.pages.get("kept", 0)),
            str(r.facts),
            str(sum(r.dropped.values())),
            f"{r.seconds / 60:.1f}",
        )
    console.print(t)
    for r in runs:  # plain lines: scripts/desktop-narrative.sh puts them in the failure email
        if not r.ok:
            print(f"FAILED {r.game_id.split('_', 2)[2]}: {r.error}")
    if not all(r.ok for r in runs):
        raise typer.Exit(1)


@narrative_app.command("week")
def narrative_week() -> None:
    """Print '<season> <week>' of the earliest game not yet kicked off (for scripts)."""
    from nfl.config import now_utc
    from nfl.llm.narrative import upcoming_week

    season, week = upcoming_week(get_paths(), now_utc().replace(tzinfo=None))
    print(season, week)


@narrative_app.command("check")
def narrative_check() -> None:
    """Exit 1 if an upcoming game has no local record since the last scheduled desktop pass
    (cloud job before each lock: the desktop was off, asleep or failed). Never touches the lock."""
    from nfl.config import now_utc
    from nfl.llm.narrative import missing_records

    season, week, since, missing = missing_records(get_paths(), now_utc().replace(tzinfo=None))
    if missing:
        console.print(f"[red]{season} week {week}: no local record since the pass at {since:%a %H:%M} UTC for {len(missing)} game(s): {', '.join(missing)}[/red]")  # fmt: skip
        raise typer.Exit(1)
    console.print(f"{season} week {week}: every upcoming game has a record since {since:%a %H:%M} UTC")  # fmt: skip


@narrative_app.command("recompose")
def narrative_recompose(
    debug: str = typer.Argument(help="A run's .debug.json under raw/narrative_local/."),
    tag: str = typer.Option(..., help="Experiment name: output goes to experiments/<tag>/."),
    model: str = typer.Option(None, help="Model for the writing jobs (default LLM_MODEL)."),
    think: str = typer.Option(
        None, help="job=effort,... e.g. matchup=low,team_trends=low (default: the pipeline's)."
    ),
    job_models: str = typer.Option(
        None, help="job=model,... for jobs on another model, or 'none' (default: the pipeline's)."
    ),
    rebuild: bool = typer.Option(
        False, help="Reuse the debug file's saved model outputs; rerun only the code checks."
    ),
) -> None:
    """Rerun only the QB and writing jobs of a saved run on its facts (minutes, not a full run)."""
    import json
    from pathlib import Path

    from nfl.llm.research import recompose

    def pairs(v: str | None) -> dict[str, str] | None:
        if v is None:
            return None
        return {} if v == "none" else dict(kv.split("=", 1) for kv in v.split(","))

    s = recompose(
        get_paths(), Path(debug), tag=tag, model=model, think=pairs(think),
        models=pairs(job_models), rebuild=rebuild,
    )  # fmt: skip
    console.print_json(json.dumps(s))


@narrative_app.command("compare")
def narrative_compare(
    files: Annotated[list[str], typer.Argument(help="Records or drafts of the same game.")],
    out: str = typer.Option(None, help="Write the markdown here (default: print)."),
) -> None:
    """Side-by-side metrics and texts for narrative records of one game (M6.2e)."""
    from pathlib import Path

    from nfl.llm.evals import compare_records

    md = compare_records([Path(f) for f in files])
    if out:
        Path(out).write_text(md)
        console.print(f"wrote {out}")
    else:
        console.print(md)


llm_app = typer.Typer(no_args_is_help=True, help="LLM client checks and the call log.")
app.add_typer(llm_app, name="llm")


@llm_app.command("ping")
def llm_ping(model: str = typer.Option(None, help="Default LLM_MODEL.")) -> None:
    """One schema-constrained call to the desktop model; logged as job 'ping'."""
    from pydantic import BaseModel

    from nfl.llm.client import LLMClient, LLMConfig

    class Ping(BaseModel):
        ok: bool
        team: str

    client = LLMClient(get_paths(), LLMConfig.from_env(model))
    r = client.complete(
        [
            {
                "role": "user",
                "content": "Set ok to true and name the NFL team that plays at Lambeau Field.",
            }
        ],
        job="ping",
        prompt_version="ping_v1",
        schema=Ping,
        max_tokens=200,
    )
    u = r.usage
    console.print(
        f"[bold]llm:[/bold] {r.model}: {r.parsed!r} in {r.latency_ms:,} ms "
        f"({u.input_tokens} in / {u.output_tokens} out, attempt {r.attempts})"
    )


@llm_app.command("calls")
def llm_calls(
    days: int = typer.Option(7, help="Trailing window."),
    tail: int = typer.Option(0, help="Instead: the last N calls in order (progress of a run)."),
) -> None:
    """Calls, tokens, latency and energy per job and model over the window; `--tail N` lists the
    latest calls one by one (a call appears when it finishes; a long run shows here as it goes)."""
    from datetime import timedelta

    import polars as pl

    from nfl.config import now_utc
    from nfl.llm.client import read_calls

    df = read_calls(get_paths()).filter(pl.col("ts") >= now_utc() - timedelta(days=days))
    if tail:
        t = Table(title=f"Last {tail} LLM calls (UTC)")
        for c in ("time", "job", "model", "game", "try", "ok", "sec", "out tokens", "error"):
            t.add_column(c)
        for r in df.sort("ts").tail(tail).iter_rows(named=True):
            t.add_row(
                f"{r['ts']:%H:%M:%S}", r["job"].removeprefix("narrative."), r["model"],
                (r["game_id"] or "").removeprefix(f"{r['ts']:%Y}_"), str(r["attempt"]),
                "yes" if r["ok"] else "[red]no[/red]", f"{r['latency_ms'] / 1000:.0f}",
                str(r["output_tokens"]), r["error"] or "",
            )  # fmt: skip
        console.print(t)
        return
    agg = (
        df.group_by("job", "model")
        .agg(
            pl.len().alias("calls"),
            (~pl.col("ok")).sum().alias("failed"),
            pl.col("input_tokens").sum().alias("tokens_in"),
            pl.col("output_tokens").sum().alias("tokens_out"),
            pl.col("latency_ms").median().cast(pl.Int64).alias("median_ms"),
            pl.col("energy_wh").sum().round(1).alias("wh"),
        )
        .sort("job", "model")
    )
    t = Table(title=f"LLM calls, last {days} days")
    for c in agg.columns:
        t.add_column(c)
    for row in agg.iter_rows():
        t.add_row(*["" if v is None else str(v) for v in row])
    console.print(t)


@app.command("daily")
def daily_cmd(
    odds: bool = typer.Option(True, help="Take an Odds API snapshot (3 credits)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="List the steps and exit."),
) -> None:
    """The Wed/Fri/Sat evening pass (ADR 0024): ingest, odds, curate, features, site. No grading."""
    from nfl import daily

    if dry_run:
        console.print("daily: " + " -> ".join(daily.plan(odds)))
        return
    daily.run(get_paths(), console, odds=odds)


@app.command("sql")
def sql_cmd(
    query: Annotated[str | None, typer.Argument(help="SQL over the catalog's views.")] = None,
    tables: bool = typer.Option(False, "--tables", help="List the views, rows and columns."),
    csv: Annotated[
        Path | None, typer.Option(help="Write the full result to this CSV file.")
    ] = None,
    parquet: Annotated[Path | None, typer.Option(help="Write it to this parquet file.")] = None,
    limit: int = typer.Option(40, help="Rows to print (the file gets all of them)."),
) -> None:
    """Query every table with SQL (ADR 0025): views over the parquet files, read-only.

    Point in time: `select * from features_asof(timestamp '2026-11-05 14:00')`, `game_vectors(ts)`."""
    from nfl import catalog

    paths = get_paths()
    con = catalog.connect(paths)
    if tables or not query:
        t = Table("view", "rows", "columns", "what it is")
        for d in catalog.describe(con):
            cols = ", ".join(d["columns"][:8]) + (" ..." if len(d["columns"]) > 8 else "")
            t.add_row(d["name"], f"{d['rows']:,}", cols, d["about"])
        console.print(t)
        if gone := catalog.missing(paths):
            console.print(f"no files yet: {', '.join(gone)}")
        return
    df = con.sql(query).pl()
    if csv:
        df.write_csv(csv)
    if parquet:
        df.write_parquet(parquet)
    t = Table(*df.columns)
    for row in df.head(limit).iter_rows():
        t.add_row(*("" if v is None else str(v) for v in row))
    console.print(t)
    console.print(f"{df.height:,} rows" + (f", first {limit} shown" if df.height > limit else ""))


models_app = typer.Typer(no_args_is_help=True, help="SQL models (ADR 0025, M23.3).")
app.add_typer(models_app, name="models")


@models_app.command("build")
def models_build(
    name: Annotated[str | None, typer.Argument(help="One model; default every model.")] = None,
) -> None:
    """Run src/nfl/sql/models/*.sql -> marts/derived/<name>.parquet (unchanged output not rewritten)."""
    from nfl.sql import runner

    try:
        results = runner.build(get_paths(), name)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    for r in results:
        console.print(f"{r.name}: {r.rows:,} rows, {r.status}")


candidates_app = typer.Typer(no_args_is_help=True, help="The candidates ledger (ADR 0026, M23.2).")
app.add_typer(candidates_app, name="candidates")


@candidates_app.command("run")
def candidates_run(
    only: Annotated[str | None, typer.Option("--only", help="One candidate id.")] = None,
    season_from: Annotated[int, typer.Option(help="First season of the residual tests.")] = 2006,
) -> None:
    """Screen every candidate through the gates; append changed results to marts/candidates.parquet."""
    from nfl import candidate_screen

    try:
        n = candidate_screen.run(get_paths(), only=only, season_from=season_from)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    console.print(f"candidates: {n} new row(s) appended")


@candidates_app.command("list")
def candidates_list(
    interesting: Annotated[bool, typer.Option("--interesting", help="Only flagged ones.")] = False,
) -> None:
    """The latest ledger row per candidate."""
    import polars as pl

    from nfl import candidate_screen

    df = candidate_screen.latest(get_paths())
    if interesting:
        df = df.filter(pl.col("interesting"))
    f = lambda v: "" if v is None else f"{v:+.2f}"
    ci = lambda r, k: "" if r[k] is None else f"{f(r[k])} [{f(r[k + '_lo'])},{f(r[k + '_hi'])}]"
    t = Table(
        "candidate", "kind", "verdict", "split", "future partial r", "vs Student", "vs market", "n"
    )
    for c in t.columns:
        c.no_wrap = True
    for r in df.sort(["interesting", "candidate"], descending=[True, False]).iter_rows(named=True):
        t.add_row(
            ("* " if r["interesting"] else "") + r["candidate"], r["kind"], r["verdict"],
            "" if r["split_half"] is None else f"{r['split_half']:.2f}",
            ci(r, "future_partial"), ci(r, "resid_st"), ci(r, "resid_mk"), str(r["resid_n"] or ""),
        )  # fmt: skip
    console.print(t)
    console.print("* = interesting. residual slopes are points per SD, positive = candidate helps.")


joblock_app = typer.Typer(no_args_is_help=True, help="One job at a time on the data (ADR 0025).")
app.add_typer(joblock_app, name="joblock")


@joblock_app.command("acquire")
def joblock_acquire(
    owner: str,
    proceed: bool = typer.Option(
        False, help="After waiting, run without the lock instead of failing."
    ),
) -> None:
    """Take the data lock (no-op without NFL_DATA_BUCKET); prints its generation for `release`."""
    import sys

    from nfl import joblock

    try:
        gen = joblock.acquire(owner, joblock.store_from_env(), proceed=proceed)
    except TimeoutError as e:
        print(e, file=sys.stderr)
        raise typer.Exit(1) from e
    except Exception as e:  # noqa: BLE001 - a broken lock must never stop the jobs: run without it
        print(f"joblock: could not take the lock ({e!r}); running without it", file=sys.stderr)
        gen = 0
    print(gen)


@joblock_app.command("release")
def joblock_release(generation: int) -> None:
    """Release the lock taken with `acquire` (its printed generation)."""
    from nfl import joblock

    joblock.release(generation, joblock.store_from_env())


@app.command("site")
def site_cmd(season: int = typer.Option(None, help="Default: current season.")) -> None:
    """Write the UI JSON contract (marts/site/): meta, slates, games, tracker, audit."""
    from nfl.site import build

    out = build(get_paths(), season)
    console.print(
        f"[bold]site:[/bold] {out['weeks']} weeks, {out['games']} games in {out['seconds']}s"
    )


@app.command("league")
def league_cmd(
    season: int = typer.Option(None, help="Default: current season."),
    snapshot: str = typer.Option(None, help="Also append a snapshot: refresh or lock."),
) -> None:
    """Standings, simulated playoff odds and leverage -> marts/site/league.json (ADR 0019)."""
    from nfl.league.build import build

    build(get_paths(), season, snapshot=snapshot)


@app.command("publish")
def publish_cmd(
    bucket: str = typer.Option(None, help="Public site bucket. Default: $NFL_SITE_BUCKET."),
    repo: str = typer.Option(None, help="Repo root holding public/predictions. Default: cwd."),
) -> None:
    """Upload marts/site/*.json and public/predictions/ to the public bucket (5-minute cache)."""
    from nfl.publish import publish

    res = publish(get_paths(), bucket, Path(repo) if repo else None)
    console.print(
        f"[bold]publish:[/bold] {len(res.uploaded)} uploaded, {len(res.skipped)} unchanged"
    )
    for name in res.uploaded:
        console.print(f"  {name}")


@app.command("scheme")
def scheme_cmd() -> None:
    """Team-season scheme rates (participation, 2016+) and QB-in-scenario tables -> marts/."""
    from nfl.scheme import build_scheme, qb_scenarios

    paths = get_paths()
    console.print(f"[bold]scheme:[/bold] {build_scheme(paths)}; qb: {qb_scenarios(paths)}")


@app.command("coaches")
def coaches_cmd() -> None:
    """Coordinator scheme profiles (participation 2016+) -> marts + site/coaches.json."""
    from nfl.coaches import build_profiles

    console.print(f"[bold]coaches:[/bold] {build_profiles(get_paths())}")


@app.command("hypotheses")
def hypotheses_cmd() -> None:
    """What history says each feature is worth (coef, 90% CI, verdict) -> marts + site JSON."""
    from nfl.hypotheses import build

    console.print(f"[bold]hypotheses:[/bold] {build(get_paths())}")


@app.command("diy-matrix")
def diy_matrix_cmd() -> None:
    """Precompute group composites per game for the build-your-own page -> marts + site JSON."""
    from nfl.approaches.diy import build_matrix

    console.print(f"[bold]diy-matrix:[/bold] {build_matrix(get_paths())}")


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
    show = ["market_baseline", "traditionalist", "analyst", "sharp", "student", "student_v2", "elo_v0"]  # fmt: skip
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


players_app = typer.Typer(no_args_is_help=True, help="Player-level data (ADR 0027).")
app.add_typer(players_app, name="players")


@players_app.command("status")
def players_status(
    season_from: int = typer.Option(2013, help="First season (snap counts start in 2013)"),
    season_to: int = typer.Option(2025, help="Last season"),
) -> None:
    """How often a player on the final injury report plays, by status and position group."""
    import polars as pl
    from rich.table import Table

    from nfl.players.status import CURRENT_ERA_FROM, build

    r = build(get_paths(), (season_from, season_to))
    t = Table(title=f"Played at least one snap, {CURRENT_ERA_FROM}+ (final report)")
    for h in ("status", "group", "n", "played", "90% interval"):
        t.add_column(h, justify="right" if h != "status" else "left")
    for row in r.filter(pl.col("era") == f"{CURRENT_ERA_FROM}+").iter_rows(named=True):
        t.add_row(row["status"], row["pos_group"], f"{row['n']:,}", f"{row['rate']:.1%}",
                  f"{row['lo']:.1%} to {row['hi']:.1%}")  # fmt: skip
    console.print(t)
    console.print(
        f"[bold]status-to-play:[/bold] {r.height} rows -> marts/derived/status_to_play.parquet"
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


retro_app = typer.Typer(no_args_is_help=True, help="Game retrospectives (ADR 0016).")
app.add_typer(retro_app, name="retro")


@retro_app.command("expectations")
def retro_expectations(
    start: int = typer.Option(2015, help="First season of the window."),
    end: int = typer.Option(2025, help="Last season of the window."),
) -> None:
    """Build league expectations from history -> marts/retro/expectations.json."""
    from nfl.retro.expectations import build, write

    paths = get_paths()
    exp = build(paths, (start, end))
    out = write(paths, exp)
    t = Table(title=f"expectations {exp.version} ({start}-{end})")
    for c in ("cell", "key", "rate", "n", "value"):
        t.add_column(c, justify="left" if c in ("cell", "key") else "right")
    for name in ("third_down", "fourth_down", "field_goal"):
        for b in getattr(exp, name):
            t.add_row(name, b.key, f"{b.rate:.3f}", f"{b.n:,}", f"{b.value:.2f}")
    t.add_row("extra_point", "", f"{exp.extra_point_rate:.3f}", f"{exp.extra_point_n:,}", "")
    t.add_row("fumble_lost", "", f"{exp.fumble_lost_share:.3f}", f"{exp.fumble_n:,}",
              f"{exp.value_fumble_lost:.2f}")  # fmt: skip
    t.add_row("interception", "", "", "", f"{exp.value_interception:.2f}")
    t.add_row("penalty_yard", "", "", "", f"{exp.value_penalty_yard:.4f}")
    t.add_row("st_big_plays", "", f"{exp.special_teams_big_plays_pg:.3f}", "",
              f"{exp.value_special_teams_big_play:.2f}")  # fmt: skip
    pl_ = exp.played_like
    t.add_row("played_like", f"b0={pl_.intercept:.3f}", f"b_epa={pl_.b_epa:.2f}",
              f"{pl_.n:,}", f"b_succ={pl_.b_success:.2f}")  # fmt: skip
    console.print(t)
    console.print(f"wrote {out}")


@retro_app.command("build")
def retro_build(
    game_ids: Annotated[list[str] | None, typer.Argument(help="Game ids (default: all).")] = None,
    season: int = typer.Option(None, help="Season (default: current)."),
    week: int = typer.Option(None, help="Only this week."),
    force: bool = typer.Option(False, "--force", help="Rebuild even if up to date."),
) -> None:
    """Build game retrospectives -> marts/retro/season=S/<game_id>.json."""
    from nfl.config import current_season
    from nfl.retro.game import build
    from nfl.retro.week import write_recap
    from nfl.site import write_retro

    paths, season = get_paths(), season or current_season()
    try:
        rep = build(paths, season, week, game_ids or None, force)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from e
    for wk in sorted(rep.weeks):
        write_recap(paths, season, wk)
    published = write_retro(paths, season)
    console.print(f"recaps for weeks {sorted(rep.weeks)}; {len(published)} site files")
    console.print(
        f"wrote {len(rep.written)} retros; {rep.up_to_date} up to date; "
        f"{rep.skipped} finished games skipped (no plays)"
    )


@retro_app.command("daily")
def retro_daily(
    season: int = typer.Option(None, help="Season (default: current)."),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="Skip the nflverse ingest."),
) -> None:
    """The 07:00 ET job: ingest + curate the current season, build retros and recaps, site files."""
    from nfl.retro.daily import run

    r = run(get_paths(), season, fetch=not no_fetch)
    console.print(
        f"retro daily {r.season}: wrote {len(r.written)} retros (weeks {r.weeks}); "
        f"{r.up_to_date} up to date; {r.skipped} skipped; {r.site_files} site files"
        + ("; built expectations" if r.built_expectations else "")
    )


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
