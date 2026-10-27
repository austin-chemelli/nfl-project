"""Null-rate audit: how complete is each field, per season? The brief's first deliverable.

Writes marts/audit.parquet with (table, season, column, n_rows, n_null, null_rate) and prints a
pivot for the fields the tendency store and models depend on.
"""

from __future__ import annotations

import duckdb
from rich.console import Console
from rich.table import Table

from nfl.config import Paths

# Fields whose availability decides what we can build. Grouped for the printed report.
WATCH: dict[str, list[str]] = {
    "plays:situation": [
        "down",
        "ydstogo",
        "yardline_100",
        "score_differential",
        "half_seconds_remaining",
        "play_type",
        "shotgun",
        "no_huddle",
        "epa",
        "success",
        "wp",
    ],
    "plays:ftn": [
        "qb_location",
        "n_offense_backfield",
        "n_defense_box",
        "is_motion",
        "is_play_action",
        "is_rpo",
        "is_screen_pass",
        "n_blitzers",
        "n_pass_rushers",
        "read_thrown",
    ],
    "games": [
        "spread_line",
        "total_line",
        "home_moneyline",
        "kickoff_utc",
        "roof",
        "temp",
        "wind",
        "home_qb_name",
        "home_coach",
    ],
    "injuries": ["report_status", "practice_status", "report_primary_injury", "gsis_id"],
}


def _null_rates(
    con: duckdb.DuckDBPyConnection, path: str, table: str, columns: list[str], where: str = "true"
) -> list[tuple]:
    cols = [
        r[0]
        for r in con.execute(
            f"describe select * from read_parquet('{path}', hive_partitioning=true)"
        ).fetchall()
    ]
    columns = [c for c in columns if c in cols]
    if not columns:
        return []
    agg = ", ".join(f'count(*) - count("{c}") as "{c}"' for c in columns)
    rows = con.execute(
        f"select season, count(*) n, {agg} from read_parquet('{path}', hive_partitioning=true) where {where} group by 1 order by 1"
    ).fetchall()
    out = []
    for r in rows:
        season, n = r[0], r[1]
        for c, nnull in zip(columns, r[2:], strict=True):
            out.append((table, int(season), c, int(n), int(nnull), (nnull / n) if n else None))
    return out


def audit(paths: Paths, console: Console, season: int | None = None) -> None:
    con = duckdb.connect()
    plays = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    games = f"{paths.curated_table('games').as_posix()}/*/*.parquet"
    inj = f"{paths.curated_table('injuries').as_posix()}/*/*.parquet"

    rows: list[tuple] = []
    # Situational fields are only meaningful on real plays, FTN only on pass/run plays.
    rows += _null_rates(
        con, plays, "plays:situation", WATCH["plays:situation"], "play_type is not null"
    )
    rows += _null_rates(
        con,
        plays,
        "plays:ftn",
        WATCH["plays:ftn"],
        "play_type in ('pass','run') and season >= 2022",
    )
    rows += _null_rates(con, games, "games", WATCH["games"], "game_type = 'REG'")
    if paths.curated_table("injuries").exists():
        rows += _null_rates(con, inj, "injuries", WATCH["injuries"])

    paths.marts.mkdir(parents=True, exist_ok=True)
    con.execute(
        "create table audit(tbl varchar, season int, col varchar, n_rows bigint, n_null bigint, null_rate double)"
    )
    con.executemany("insert into audit values (?,?,?,?,?,?)", rows)
    con.execute(f"copy audit to '{(paths.marts / 'audit.parquet').as_posix()}' (format parquet)")

    seasons = sorted({r[1] for r in rows if season is None or r[1] == season})
    if len(seasons) > 6:
        seasons = seasons[-6:]
    for tbl, watch_cols in WATCH.items():
        t = Table(title=f"null rate: {tbl}", show_lines=False)
        t.add_column("column")
        for s in seasons:
            t.add_column(str(s), justify="right")
        by = {(r[1], r[2]): r[5] for r in rows if r[0] == tbl}
        for c in watch_cols:
            if not any((s, c) in by for s in seasons):
                continue
            cells = []
            for s in seasons:
                v = by.get((s, c))
                if v is None:
                    cells.append("[dim]-[/dim]")
                else:
                    style = "green" if v < 0.02 else "yellow" if v < 0.2 else "red"
                    cells.append(f"[{style}]{v:.1%}[/{style}]")
            t.add_row(c, *cells)
        console.print(t)
    console.print(f"[bold]audit:[/bold] {len(rows):,} rows -> marts/audit.parquet")
