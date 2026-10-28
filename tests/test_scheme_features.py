"""Scheme-prior features: point-in-time construction and the store contract."""

from datetime import UTC, datetime

import polars as pl
import pytest

from nfl import coaches
from nfl.config import get_paths
from nfl.features import scheme, store

from .conftest import requires_data


def _games():
    def g(gid, season, week, home, away, day):
        return {"game_id": gid, "season": season, "week": week, "home_team": home,
                "away_team": away, "kickoff_utc": datetime(season, 9, day, 17, tzinfo=UTC)}  # fmt: skip

    return pl.DataFrame(
        [
            g("g16", 2016, 1, "AAA", "BBB", 10),
            g("g17", 2017, 1, "AAA", "BBB", 10),
            g("g18", 2018, 1, "BBB", "AAA", 10),
        ]
    )


def _assign():
    rows = []
    for season in (2016, 2017, 2018):
        rows += [
            (season, "AAA", "off", "OffA", "play_caller"),
            (season, "BBB", "off", "OffB" if season < 2018 else "OffNew", "coordinator"),
            (season, "AAA", "def", "DefA", "coordinator"),
            (season, "BBB", "def", "DefB", "coordinator"),
        ]
    return pl.DataFrame(rows, schema=["season", "team", "side", "person", "source"], orient="row")


def _rows():
    def r(person, side, season, team, metric, pct, dev):
        return {"person": person, "side": side, "season": season, "team": team,
                "metric": metric, "pct": pct, "dev": dev}  # fmt: skip

    return pl.DataFrame(
        [
            r("OffA", "off", 2016, "AAA", "pers_11_share", 0.6, 0.05),
            r("OffA", "off", 2017, "AAA", "pers_11_share", 0.9, 0.99),  # leak canary
            r("DefA", "def", 2016, "AAA", "man_rate", 0.7, 0.2),
            r("OffB", "off", 2016, "BBB", "pers_11_share", 0.4, -0.05),
        ]
    )


def test_prior_reads_only_earlier_seasons():
    out = scheme.compute(_games(), _rows(), _assign())
    v = {(r["game_id"], r["team"], r["feature"]): r["value"] for r in out.to_dicts()}
    # 2017 game uses only 2016: the 0.99 canary (2017 season) must not appear
    assert v[("g17", "AAA", "scheme.off_11_rate_prior")] == pytest.approx(0.05)
    assert v[("g17", "AAA", "scheme.def_man_rate_prior")] == pytest.approx(0.2)
    # 2018 sees both 2016 and 2017 (weights 0.7 and 1)
    want = (0.05 * 0.7 + 0.99 * 1.0) / 1.7
    assert v[("g18", "AAA", "scheme.off_11_rate_prior")] == pytest.approx(want)


def test_new_coordinator_and_missing_metric_are_null():
    out = scheme.compute(_games(), _rows(), _assign())
    v = {(r["game_id"], r["team"], r["feature"]): r["value"] for r in out.to_dicts()}
    assert v[("g18", "BBB", "scheme.off_11_rate_prior")] is None  # OffNew has no history
    assert v[("g17", "AAA", "scheme.off_heavy_rate_prior")] is None  # no such metric rows
    assert "g16" not in set(out["game_id"])  # needs a prior season: 2017+


def test_store_contract():
    ts = datetime(2026, 10, 27, tzinfo=UTC)
    vals = scheme.compute(_games(), _rows(), _assign())
    rows = store.from_team_values(
        vals, _games(), source=scheme.SOURCE, version=scheme.VERSION, build_ts=ts
    )
    store.validate(rows)
    assert set(rows["feature"]) == set(scheme.FEATURES)
    assert set(rows["side"]) == {"home", "away"}
    k = rows.join(_games().select("game_id", "kickoff_utc"), on="game_id")
    assert (k["known_as_of"].dt.replace_time_zone("UTC") < k["kickoff_utc"]).all()
    assert all(f.startswith("scheme.") for f in rows["feature"])


@requires_data
def test_real_features_non_null_share_and_contract():
    paths = get_paths()
    games = store.games_frame(paths)
    rows = scheme.build(paths, games, datetime(2026, 10, 27, tzinfo=UTC))
    store.validate(rows)
    assert set(rows["feature"]) == set(scheme.FEATURES)
    assert rows["season"].min() == 2017
    late = rows.filter(pl.col("season") >= 2019)
    share = late.group_by("feature").agg(pl.col("value").is_not_null().mean().alias("s"))
    assert (share["s"] > 0.5).all(), share
    # a long-tenured DC has >= 4 profile seasons
    prof = coaches.profile_rows(paths)
    d = prof.filter((pl.col("person") == "Steve Spagnuolo") & (pl.col("side") == "def"))
    assert d["season"].n_unique() >= 4
