"""Coordinator scheme profiles: percentiles, priors (no leakage), consistency, site JSON."""

import json

import polars as pl
import pytest

from nfl import coaches
from nfl.config import get_paths

from .conftest import requires_data


def _rates():
    # 4 teams in 2020: man rates .1 .2 .3 .4 (n large); one team below MIN_N is excluded
    rows = [(2020, t, "def", "man_rate", 500, r) for t, r in
            [("AAA", 0.1), ("BBB", 0.2), ("CCC", 0.3), ("DDD", 0.4)]]  # fmt: skip
    rows.append((2020, "EEE", "def", "man_rate", 10, 0.9))
    rows.append((2020, "AAA", "def", "not_a_metric", 500, 0.5))
    return pl.DataFrame(
        rows, schema=["season", "team", "side", "metric", "n", "rate"], orient="row"
    )


def test_within_season_percentile_and_league_mean():
    out = coaches.league_percentiles(_rates()).sort("rate")
    assert out["team"].to_list() == ["AAA", "BBB", "CCC", "DDD"]  # low n and unknown metric out
    assert out["pct"].to_list() == pytest.approx([0.125, 0.375, 0.625, 0.875])
    assert out["league_mean"].to_list() == pytest.approx([0.25] * 4)


def test_percentile_is_per_season():
    r = pl.concat(
        [
            _rates().filter(pl.col("n") > 100),
            _rates()
            .filter(pl.col("n") > 100)
            .with_columns(
                pl.lit(2021, dtype=pl.Int64).alias("season"), (pl.col("rate") + 0.3).alias("rate")
            ),
        ]
    )
    out = coaches.league_percentiles(r)
    # the same ordering in both seasons: a league-wide level shift (provider change) is invisible
    a = out.filter(pl.col("season") == 2020).sort("team")["pct"].to_list()
    b = out.filter(pl.col("season") == 2021).sort("team")["pct"].to_list()
    assert a == pytest.approx(b)


def _prof(person, season, team, pct, dev, side="def", metric="man_rate"):
    return {"person": person, "side": side, "season": season, "team": team, "metric": metric,
            "pct": pct, "dev": dev}  # fmt: skip


def test_priors_use_only_earlier_seasons():
    rows = pl.DataFrame(
        [
            _prof("X", 2020, "AAA", 0.2, -0.1),
            _prof("X", 2021, "AAA", 0.8, 0.1),
            _prof("X", 2022, "AAA", 1.0, 0.3),
        ]
    )
    p = coaches.priors(rows, 2022)
    w1, w0 = 1.0, 0.7  # 2021 counts 1, 2020 counts 0.7
    assert p["prior_pct"][0] == pytest.approx((0.8 * w1 + 0.2 * w0) / (w1 + w0))
    assert p["n_metric_seasons"][0] == 2  # the 2022 row (the target season) is invisible
    only_first = coaches.priors(rows, 2021)
    assert only_first["prior_pct"][0] == pytest.approx(0.2)
    assert only_first["spread"][0] is None  # one season: no spread
    assert coaches.priors(rows, 2020).is_empty()  # nothing before the first season


def test_prior_changing_a_future_row_does_not_change_it():
    base = [_prof("X", 2020, "AAA", 0.2, -0.1), _prof("X", 2021, "AAA", 0.8, 0.1)]
    a = coaches.priors(pl.DataFrame(base + [_prof("X", 2022, "AAA", 0.0, -0.5)]), 2022)
    b = coaches.priors(pl.DataFrame(base + [_prof("X", 2022, "AAA", 1.0, 0.5)]), 2022)
    assert a["prior_pct"].to_list() == b["prior_pct"].to_list()


def test_play_caller_who_changed_teams_carries_history():
    rows = pl.DataFrame(
        [
            _prof("X", 2020, "AAA", 0.9, 0.1),
            _prof("X", 2021, "BBB", 0.7, 0.05),
            _prof("Y", 2021, "AAA", 0.1, -0.1),
        ]
    )
    s = coaches.person_summary(rows, 2022).filter(pl.col("person") == "X")
    assert s["n_seasons"][0] == 2 and s["n_teams"][0] == 2
    assert s["teams"][0].to_list() == ["AAA", "BBB"]
    p = coaches.priors(rows, 2022).filter(pl.col("person") == "X")
    assert p["prior_pct"][0] == pytest.approx((0.7 * 1 + 0.9 * 0.7) / 1.7)


def test_new_coordinator_has_no_prior():
    rows = pl.DataFrame([_prof("X", 2020, "AAA", 0.9, 0.1)])
    assert coaches.priors(rows, 2022).filter(pl.col("person") == "Newbie").is_empty()
    assert (
        coaches._prior_block(
            coaches.priors(rows, 2022), coaches.person_summary(rows, 2022), "Newbie", "def"
        )
        is None
    )
    s = coaches.sentence("Newbie", "Defensive play-caller", None, 2026)
    assert "no participation history" in s


def test_consistency_label():
    assert coaches.consistency_label(0.05, 5) == "very consistent"
    assert coaches.consistency_label(0.16, 5) == "fairly consistent"
    assert coaches.consistency_label(0.30, 5) == "changes a lot"
    assert coaches.consistency_label(0.05, 2) is None  # too few seasons to say
    assert coaches.consistency_label(None, 9) is None


def test_consistent_vs_erratic_spread():
    ms = ["man_rate", "two_high_rate", "blitz_rate"]
    steady = [_prof("S", y, "AAA", 0.8 + 0.01 * y % 2, 0.1, metric=m) for y in range(2018, 2023)
              for m in ms]  # fmt: skip
    wild = [_prof("W", y, "AAA", 0.9 if y % 2 else 0.1, 0.1, metric=m) for y in range(2018, 2023)
            for m in ms]  # fmt: skip
    s = coaches.person_summary(pl.DataFrame(steady + wild), 2024).sort("person")
    by = dict(zip(s["person"], s["consistency"], strict=True))
    assert by == {"S": "very consistent", "W": "changes a lot"}


def test_sentence_reads_plainly():
    prior = {"n_seasons": 4, "consistency": "very consistent", "metrics": {
        "man_rate": {"pct": 0.8}, "two_high_rate": {"pct": 0.5}}}  # fmt: skip
    s = coaches.sentence("Jim Doe", "Defensive coordinator", prior, 2026)
    assert "more man coverage than 80% of the league" in s
    assert "last 4 seasons" in s and "very consistent" in s
    prior["metrics"]["man_rate"]["pct"] = 0.1
    assert "less man coverage than 90%" in coaches.sentence("Jim Doe", "DC", prior, 2026)


def test_assignments_prefer_play_caller_and_map_franchise():
    a = coaches.assignments()
    assert set(a["side"]) == {"off", "def"}
    assert set(a["source"]) == {"play_caller", "coordinator"}
    assert not set(a["team"]) & {"OAK", "SD", "STL"}  # franchise codes
    assert a.select("season", "team", "side").unique().height == a.height


@requires_data
def test_real_profiles_and_site_json():
    paths = get_paths()
    coaches.build_profiles(paths)
    rows = pl.read_parquet(paths.marts / "coach_profiles.parquet")
    spags = rows.filter((pl.col("person") == "Steve Spagnuolo") & (pl.col("side") == "def"))
    assert spags["season"].n_unique() >= 4
    assert spags["pct"].is_between(0, 1).all()
    site = json.loads((paths.site / "coaches.json").read_text())
    cur = site["current_season"]
    assert len(site["teams"]) == 32
    team = next(iter(site["teams"].values()))
    assert {"head_coach", "off", "def"} <= set(team)
    # priors never include the current season
    for t in site["teams"].values():
        for side in ("off", "def"):
            b = t[side]
            if b and b["prior"]:
                assert b["prior"]["last_season"] < cur
    assert any(
        b[s] and not b[s]["has_history"] and "no participation history" in b[s]["sentence"]
        for b in site["teams"].values()
        for s in ("off", "def")
    )
