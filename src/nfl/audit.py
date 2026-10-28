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
    "participation": [
        "_joined_to_plays",
        "off_personnel",
        "def_package",
        "offense_formation",
        "defenders_in_box",
        "number_of_pass_rushers",
        "was_pressure",
        "time_to_throw",
        "man_zone",
        "coverage",
        "two_high",
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


_PART_DROPBACK_COLS = ["number_of_pass_rushers", "was_pressure", "time_to_throw", "man_zone"]
_PART_COVERAGE_COLS = ["coverage", "two_high"]
_PART_SCRIM_COLS = [
    "off_personnel",
    "def_package",
    "offense_formation",
    "defenders_in_box",
]


def _participation_rows(con: duckdb.DuckDBPyConnection, paths: Paths) -> list[tuple]:
    """Participation null rates per season, denominators matched to where a field can exist.

    Personnel/formation/box over matched pass+run plays; pressure, rushers, time to throw, man/zone
    and coverage over matched dropbacks. `_joined_to_plays` is the share of participation rows that
    found a play (n_null = unmatched). Charting provider is NGS <= 2022, FTN >= 2023.
    """
    path = f"{paths.curated_table('participation').as_posix()}/*/*.parquet"
    scrim = "in_plays and play_type in ('pass','run')"
    rows = _null_rates(con, path, "participation", _PART_SCRIM_COLS, scrim)
    dropback = f"{scrim} and qb_dropback = 1"
    rows += _null_rates(
        con, path, "participation", _PART_DROPBACK_COLS + _PART_COVERAGE_COLS, dropback
    )
    joined = con.execute(
        f"select season, count(*), count(*) filter (where not in_plays) "
        f"from read_parquet('{path}', hive_partitioning=true) group by 1 order by 1"
    ).fetchall()
    rows += [
        ("participation", int(sn), "_joined_to_plays", int(n), int(nu), nu / n if n else None)
        for sn, n, nu in joined
    ]
    return rows


def _provider_levels(con: duckdb.DuckDBPyConnection, paths: Paths) -> list[tuple]:
    """League-wide levels per season, to eyeball the NGS (<= 2022) -> FTN (>= 2023) jump."""
    path = f"{paths.curated_table('participation').as_posix()}/*/*.parquet"
    return con.execute(
        f"""select season, any_value(provider),
            avg((man_zone = 'MAN')::int) filter (where man_zone is not null),
            avg(two_high::int) filter (where two_high is not null),
            avg((number_of_pass_rushers >= 5)::int),
            avg(was_pressure::int), avg(time_to_throw),
            avg((def_package = 'nickel')::int) filter (where def_package is not null)
            from read_parquet('{path}', hive_partitioning=true)
            where in_plays and play_type in ('pass','run') and qb_dropback = 1 group by 1 order by 1"""
    ).fetchall()


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
    if paths.curated_table("participation").exists():
        rows += _participation_rows(con, paths)
    if paths.curated_table("injuries").exists():
        rows += _null_rates(con, inj, "injuries", WATCH["injuries"])

    paths.marts.mkdir(parents=True, exist_ok=True)
    con.execute(
        "create table audit(tbl varchar, season int, col varchar, n_rows bigint, n_null bigint, null_rate double)"
    )
    con.executemany("insert into audit values (?,?,?,?,?,?)", rows)
    con.execute(f"copy audit to '{(paths.marts / 'audit.parquet').as_posix()}' (format parquet)")

    all_seasons = sorted({r[1] for r in rows if season is None or r[1] == season})
    for tbl, watch_cols in WATCH.items():
        tbl_seasons = [s for s in all_seasons if any(r[0] == tbl and r[1] == s for r in rows)]
        seasons = tbl_seasons if tbl == "participation" else tbl_seasons[-6:]
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
    if paths.curated_table("participation").exists():
        lv = Table(title="participation: league levels on dropbacks (provider change 2022 -> 2023)")
        for h in ("season", "provider", "man", "two-high", "5+ rush", "pressure", "ttt", "nickel"):
            lv.add_column(h, justify="right")
        for sn, prov, *vals in _provider_levels(con, paths):
            lv.add_row(str(sn), prov, *("-" if v is None else f"{v:.3f}" for v in vals))
        console.print(lv)
    console.print(f"[bold]audit:[/bold] {len(rows):,} rows -> marts/audit.parquet")
