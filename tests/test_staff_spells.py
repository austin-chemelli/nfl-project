import polars as pl

from nfl import coaches
from nfl.coaches import CONFIRMED, EVIDENCE, ROLE_COLUMNS, coordinators_view, load_spells, staff_at
from nfl.config import get_paths
from nfl.features.store import games_frame

from .conftest import requires_data


def spell(role, person, start=1, end=None, team="LV", season=2024, note=None):
    return {
        "season": season, "team": team, "role": role, "person": person, "start_week": start,
        "end_week": end, "evidence": "news", "source_url": "https://example.com", "note": note,
    }  # fmt: skip


def frame(*rows):
    return pl.DataFrame(list(rows), schema=coaches._SPELL_SCHEMA)


HANDOFF = frame(
    spell("HC", "Antonio Pierce"),
    spell("OC", "Luke Getsy", end=9),
    spell("OC", "Scott Turner", start=10, note="Getsy fired"),
    spell("OFF_PC", "Luke Getsy", end=9),
    spell("OFF_PC", "Scott Turner", start=10),
    spell("DC", "Patrick Graham"),
)


def people(df, role):
    return df.filter(pl.col("role") == role)["person"].to_list()


def test_staff_at_follows_the_week():
    assert people(staff_at(2024, "LV", 9, HANDOFF), "OFF_PC") == ["Luke Getsy"]
    assert people(staff_at(2024, "LV", 10, HANDOFF), "OFF_PC") == ["Scott Turner"]
    assert people(staff_at(2024, "LV", 21, HANDOFF), "OFF_PC") == ["Scott Turner"]  # playoffs
    assert people(staff_at(2024, "LV", 10, HANDOFF), "DC") == ["Patrick Graham"]


def test_staff_at_accepts_old_franchise_codes():
    s = frame(spell("HC", "Jack Del Rio", team="OAK", season=2017))
    assert people(staff_at(2017, "LV", 3, s), "HC") == ["Jack Del Rio"]
    assert people(staff_at(2017, "OAK", 3, s), "HC") == ["Jack Del Rio"]


def test_view_takes_the_end_of_season_person():
    v = coordinators_view(HANDOFF).row(0, named=True)
    assert v["offensive_coordinator"] == "Scott Turner"
    assert v["off_play_caller"] == "Scott Turner"
    assert v["def_play_caller"] is None
    assert v["changed_midseason"] is True
    assert v["notes"] == "Getsy fired"


def test_head_coach_change_alone_is_not_a_unit_change():
    s = frame(spell("HC", "A", end=5), spell("HC", "B", start=6), spell("OC", "C"))
    v = coordinators_view(s).row(0, named=True)
    assert v["head_coach"] == "B"
    assert v["changed_midseason"] is False


def test_co_coordinators_resolve_to_the_first_row():
    s = frame(spell("HC", "A"), spell("DC", "First"), spell("DC", "Second"))
    assert coordinators_view(s)["defensive_coordinator"].to_list() == ["First"]
    assert len(people(staff_at(2024, "LV", 1, s), "DC")) == 2


def test_table_values_are_valid():
    s = load_spells()
    assert set(s["role"]) <= set(ROLE_COLUMNS)
    assert set(s["evidence"]) <= set(EVIDENCE)
    assert s["person"].null_count() == 0
    assert s["source_url"].null_count() == 0
    assert s["start_week"].is_between(1, 18).all()
    bad = s.filter(pl.col("end_week").is_not_null() & (pl.col("end_week") < pl.col("start_week")))
    assert bad.is_empty(), bad.select("season", "team", "role", "person").to_dicts()
    assert set(CONFIRMED) < set(EVIDENCE)


def test_one_head_coach_and_one_caller_at_a_time():
    s = load_spells().filter(pl.col("role").is_in(["HC", "OFF_PC", "DEF_PC"]))
    keys = ["season", "team", "role"]
    x = s.sort(*keys, "start_week").with_columns(
        pl.col("start_week").shift(-1).over(keys).alias("next_start")
    )
    overlap = x.filter(
        pl.col("next_start").is_not_null()
        & (pl.col("end_week").is_null() | (pl.col("end_week") >= pl.col("next_start")))
    )
    assert overlap.is_empty(), overlap.select(*keys, "person").to_dicts()


def test_every_team_season_starts_with_a_head_coach():
    s = load_spells().filter(pl.col("role") == "HC")
    first = s.group_by("season", "team").agg(pl.col("start_week").min())
    assert first.height == 352
    assert (first["start_week"] == 1).all()


def test_a_caller_who_left_with_no_known_successor_still_counts_as_a_change():
    s = frame(spell("HC", "A"), spell("OFF_PC", "B", end=13))
    assert coordinators_view(s)["changed_midseason"].to_list() == [True]


@requires_data
def test_head_coaches_match_the_schedule_through_2023():
    """An independent check on the table. The schedule's coach field goes stale from 2024."""
    games = games_frame(get_paths(), min_season=2016).filter(
        (pl.col("season") <= 2023) & (pl.col("game_type") == "REG")
    )
    sched = pl.concat(
        [games.select("season", "week", pl.col(f"{s}_team").alias("team"),
                      pl.col(f"{s}_coach").alias("coach")) for s in ("home", "away")]
    ).sort("week").group_by("season", "team").agg(pl.col("coach").last())  # fmt: skip
    view = coaches.load_coordinators().select("season", "team", "head_coach")
    both = view.join(sched, on=["season", "team"])
    assert both.height == 256
    typo = {"Jay Rosburg": "Jerry Rosburg"}  # nflverse, DEN 2022
    bad = both.filter(pl.col("head_coach") != pl.col("coach").replace(typo))
    assert bad.is_empty(), bad.to_dicts()
