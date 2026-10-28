"""Team-season scheme rates from participation + plays (M1.16, first part).

Outputs (marts/):
  scheme_team_season.parquet  long format: season, team, side ('off'|'def'), metric, n, rate
  scheme_qb_season.parquet    per (season, team, side): primary passer and EPA/dropback by scenario

Offense rows are over the team's own plays; defense rows over opponents' plays against the team.
Coverage/man/zone/two-high metrics come from charted dropbacks only (~half of pass plays), time to
throw and pressure from charted dropbacks. Provider changed from NGS (<= 2022) to FTN (>= 2023), so
level shifts across 2022/2023 are expected (see the audit); fits should carry a season dummy.
"""

from __future__ import annotations

import duckdb
import polars as pl

from nfl.config import Paths

SCRIM = "in_plays and play_type in ('pass','run')"
DROPBACK = f"{SCRIM} and qb_dropback = 1"
HEAVY = "(off_te >= 2 or off_rb >= 2)"

# metric -> (numerator expression, row filter); rate = avg(numerator) over rows passing the filter.
OFFENSE: dict[str, tuple[str, str]] = {
    "pers_11_share": ("(off_personnel = '11')::int", f"{SCRIM} and off_personnel is not null"),
    "pers_12_share": ("(off_personnel = '12')::int", f"{SCRIM} and off_personnel is not null"),
    "pers_21_share": ("(off_personnel = '21')::int", f"{SCRIM} and off_personnel is not null"),
    "pers_heavy_share": (f"{HEAVY}::int", f"{SCRIM} and off_personnel is not null"),
    "shotgun_share": ("shotgun::int", f"{SCRIM} and shotgun is not null"),
    "pass_rate_11": ('"pass"::int', f"{SCRIM} and off_personnel = '11'"),
    "pass_rate_12": ('"pass"::int', f"{SCRIM} and off_personnel = '12'"),
    "pass_rate_21": ('"pass"::int', f"{SCRIM} and off_personnel = '21'"),
    "pass_rate_heavy": ('"pass"::int', f"{SCRIM} and off_personnel is not null and {HEAVY}"),
    "time_to_throw": ("time_to_throw", f"{DROPBACK} and time_to_throw is not null"),
    "pressure_allowed_rate": ("was_pressure::int", f"{DROPBACK} and was_pressure is not null"),
}
# EPA / success per dropback by the coverage or pressure scenario the offense faced.
_SCENARIOS: dict[str, str] = {
    "vs_man": "man_zone = 'MAN'",
    "vs_zone": "man_zone = 'ZONE'",
    "vs_two_high": "two_high",
    "vs_single_high": "two_high is not null and not two_high",
    "vs_pressure": "was_pressure",
    "vs_no_pressure": "was_pressure is not null and not was_pressure",
}
for _name, _cond in _SCENARIOS.items():
    OFFENSE[f"epa_{_name}"] = (
        "epa",
        f"{DROPBACK} and epa is not null and coalesce({_cond}, false)",
    )
    OFFENSE[f"success_{_name}"] = (
        "success",
        f"{DROPBACK} and success is not null and coalesce({_cond}, false)",
    )

_COVERS = {
    "0": "COVER_0",
    "1": "COVER_1",
    "2": "COVER_2",
    "3": "COVER_3",
    "4": "COVER_4",
    "6": "COVER_6",
}
_OTHER_COVERS = "('COVER_0','COVER_1','COVER_2','COVER_3','COVER_4','COVER_6','2_MAN')"
DEFENSE: dict[str, tuple[str, str]] = {
    "man_rate": ("(man_zone = 'MAN')::int", f"{DROPBACK} and man_zone is not null"),
    "two_high_rate": ("two_high::int", f"{DROPBACK} and two_high is not null"),
    **{
        f"cover_{k}_share": (f"(coverage = '{v}')::int", f"{DROPBACK} and coverage is not null")
        for k, v in _COVERS.items()
    },
    "cover_2_man_share": ("(coverage = '2_MAN')::int", f"{DROPBACK} and coverage is not null"),
    "cover_other_share": (
        f"(coverage not in {_OTHER_COVERS})::int",
        f"{DROPBACK} and coverage is not null",
    ),
    "blitz_rate": (
        "(number_of_pass_rushers >= 5)::int",
        f"{DROPBACK} and number_of_pass_rushers is not null",
    ),
    "pressure_rate": ("was_pressure::int", f"{DROPBACK} and was_pressure is not null"),
    "nickel_share": ("(def_package = 'nickel')::int", f"{SCRIM} and def_package is not null"),
    "dime_share": ("(def_package = 'dime')::int", f"{SCRIM} and def_package is not null"),
    "base_share": ("(def_package = 'base')::int", f"{SCRIM} and def_package is not null"),
    "epa_allowed_vs_11": ("epa", f"{SCRIM} and epa is not null and off_personnel = '11'"),
    "epa_allowed_vs_heavy": (
        "epa",
        f"{SCRIM} and epa is not null and off_personnel is not null and {HEAVY}",
    ),
    "epa_allowed_man": ("epa", f"{DROPBACK} and epa is not null and man_zone = 'MAN'"),
    "epa_allowed_zone": ("epa", f"{DROPBACK} and epa is not null and man_zone = 'ZONE'"),
    "epa_allowed_two_high": (
        "epa",
        f"{DROPBACK} and epa is not null and coalesce(two_high, false)",
    ),
    "epa_allowed_single_high": (
        "epa",
        f"{DROPBACK} and epa is not null and two_high is not null and not two_high",
    ),
}


def _part_glob(paths: Paths) -> str:
    return f"{paths.curated_table('participation').as_posix()}/*/*.parquet"


def rates_sql(source: str) -> str:
    """UNION ALL of one grouped aggregate per (side, metric) over relation `source`."""
    parts = []
    for side, team_col, metrics in (("off", "posteam", OFFENSE), ("def", "defteam", DEFENSE)):
        for metric, (num, filt) in metrics.items():
            parts.append(
                f"select season, {team_col} as team, '{side}' as side, '{metric}' as metric, "
                f"count(*) as n, avg({num}) as rate from {source} "
                f"where {team_col} is not null and ({filt}) group by 1, 2"
            )
    return " union all ".join(parts)


def team_season_rates(paths: Paths) -> pl.DataFrame:
    """Long frame (season, team, side, metric, n, rate); every rate carries its sample size n."""
    src = f"read_parquet('{_part_glob(paths)}', hive_partitioning=true)"
    con = duckdb.connect()
    return con.sql(f"{rates_sql(src)} order by 1, 2, 3, 4").pl()


# EPA/dropback scenarios for the QB table.
_QB_SCEN = {
    "all": "true",
    "man": "man_zone = 'MAN'",
    "zone": "man_zone = 'ZONE'",
    "pressure": "was_pressure",
    "no_pressure": "was_pressure is not null and not was_pressure",
}


def qb_scenarios_sql(source: str) -> str:
    """Primary passer (most dropbacks) per team-season and EPA/dropback by scenario.

    side 'off': the team's own primary passer, over his dropbacks. side 'def': no passer; EPA per
    dropback the defense allowed under its own man/zone/pressure calls.
    """
    sel = []
    for k, cond in _QB_SCEN.items():
        sel.append(f"count(*) filter (where coalesce({cond}, false)) as n_{k}")
        sel.append(f"avg(epa) filter (where coalesce({cond}, false)) as epa_{k}")
    aggs = ", ".join(sel)
    return f"""
    with d as (
        select * from {source} where {DROPBACK} and epa is not null and posteam is not null
    ),
    qb as (
        select season, posteam as team, passer_player_id, any_value(passer_player_name) as passer_player_name,
               count(*) as dropbacks,
               row_number() over (partition by season, posteam order by count(*) desc, passer_player_id) as rk
        from d where passer_player_id is not null group by season, posteam, passer_player_id
    )
    select d.season, d.posteam as team, 'off' as side, qb.passer_player_id, qb.passer_player_name,
           qb.dropbacks as qb_dropbacks, {aggs}
    from d join qb on qb.season = d.season and qb.team = d.posteam
               and qb.passer_player_id = d.passer_player_id and qb.rk = 1
    group by d.season, d.posteam, qb.passer_player_id, qb.passer_player_name, qb.dropbacks
    union all
    select season, defteam as team, 'def' as side, null, null, null, {aggs}
    from d where defteam is not null group by season, defteam
    order by 1, 2, 3
    """


def qb_scenarios(paths: Paths) -> pl.DataFrame:
    src = f"read_parquet('{_part_glob(paths)}', hive_partitioning=true)"
    return duckdb.connect().sql(qb_scenarios_sql(src)).pl()


def build_scheme(paths: Paths) -> tuple[int, int]:
    """Write both scheme marts. Returns (team-season rate rows, qb rows)."""
    paths.marts.mkdir(parents=True, exist_ok=True)
    rates = team_season_rates(paths)
    rates.write_parquet(paths.marts / "scheme_team_season.parquet")
    qb = qb_scenarios(paths)
    qb.write_parquet(paths.marts / "scheme_qb_season.parquet")
    return rates.height, qb.height
