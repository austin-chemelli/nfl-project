import polars as pl

from nfl.coaches import coordinator_seasons, load_coordinators
from nfl.config import get_paths
from nfl.features.store import games_frame

from .conftest import requires_data

SEASONS = range(2016, 2027)


def test_shape_and_uniqueness():
    df = load_coordinators()
    assert df.height == 352
    assert df.select("season", "team").unique().height == 352
    assert sorted(df["season"].unique().to_list()) == list(SEASONS)
    assert (df.group_by("season").len()["len"] == 32).all()
    assert df["source_url"].null_count() == 0
    assert df["head_coach"].null_count() == 0


def test_no_empty_strings_and_midseason_has_notes():
    df = load_coordinators()
    for c in df.columns:
        if df[c].dtype == pl.Utf8:
            assert not (df[c].str.strip_chars() == "").any(), c
    changed = df.filter(pl.col("changed_midseason"))
    assert changed["notes"].null_count() == 0


def test_oc_dc_present_2020_2025_or_explained():
    df = load_coordinators().filter(pl.col("season").is_between(2020, 2025))
    missing = df.filter(
        pl.col("offensive_coordinator").is_null() | pl.col("defensive_coordinator").is_null()
    )
    assert missing["notes"].null_count() == 0, missing.select("season", "team").to_dicts()


def test_coordinator_seasons():
    reid = coordinator_seasons("andy reid")
    assert reid.height >= 10
    assert set(reid["team"]) == {"KC"}
    assert coordinator_seasons("Nobody Real").is_empty()


@requires_data
def test_team_codes_match_schedule_per_season():
    games = games_frame(get_paths(), min_season=2016)
    sched = (
        pl.concat(
            [
                games.select("season", pl.col("home_team").alias("team")),
                games.select("season", pl.col("away_team").alias("team")),
            ]
        )
        .unique()
        .filter(pl.col("season").is_in(list(SEASONS)))
    )
    df = load_coordinators().select("season", "team")
    assert df.join(sched, on=["season", "team"], how="anti").is_empty()
    assert sched.join(df, on=["season", "team"], how="anti").is_empty()
