"""Market feature builder: pure helpers on toy frames, plus one real-data consistency check."""

from datetime import datetime

import polars as pl
import pytest

from nfl.config import Paths, get_paths
from nfl.features import market, store
from nfl.models.market import norm_cdf
from tests.conftest import requires_data

BUILD = datetime(2025, 9, 10, 12, 0)


def games(rows):
    return pl.DataFrame(
        rows,
        schema={
            "game_id": pl.Utf8,
            "season": pl.Int64,
            "week": pl.Int64,
            "home_team": pl.Utf8,
            "away_team": pl.Utf8,
            "kickoff_utc": pl.Datetime("us"),
            "spread_line": pl.Float64,
            "total_line": pl.Float64,
            "home_moneyline": pl.Float64,
            "away_moneyline": pl.Float64,
        },
        orient="row",
    )


K = datetime(2025, 9, 7, 17, 0)


def wide(df):
    return {r["feature"]: r["value"] for r in df.iter_rows(named=True)}


def test_american_to_implied():
    assert market.american_to_implied(-100) == pytest.approx(0.5)
    assert market.american_to_implied(100) == pytest.approx(0.5)
    assert market.american_to_implied(-150) == pytest.approx(0.6)
    assert market.american_to_implied(130) == pytest.approx(100 / 230)


def test_vigfree_sums_to_one_and_favorite_over_half():
    ph = market.vigfree_home(-150, 130)
    pa = market.vigfree_home(130, -150)
    assert ph + pa == pytest.approx(1.0)
    assert ph > 0.5 > pa


def test_vigfree_missing_or_zero():
    assert market.vigfree_home(None, -110) is None
    assert market.vigfree_home(-110, None) is None
    assert market.vigfree_home(0, -110) is None


def test_fallback_and_null(tmp_path):
    g = games(
        [
            ("A", 2025, 1, "H", "V", K, 3.0, 44.0, None, None),
            ("B", 2025, 1, "H", "V", K, None, None, None, None),
            ("C", 2025, 1, "H", "V", K, 3.0, 44.0, -150.0, 130.0),
        ]
    )
    rows = market.build(Paths(tmp_path), g, BUILD)
    p = {
        r["game_id"]: r["value"]
        for r in rows.filter(pl.col("feature") == "market.p_home_vigfree").iter_rows(named=True)
    }
    assert p["A"] == pytest.approx(norm_cdf(3.0 / 13.5))
    assert p["B"] is None
    assert p["C"] == pytest.approx(market.vigfree_home(-150, 130))
    assert set(rows["side"]) == {"game"}
    assert "market.line_move_pts" not in set(rows["feature"])
    store.validate(rows)
    cov = market.coverage(g)
    assert (cov["moneyline"], cov["spread_fallback"], cov["none"]) == (1, 1, 1)
    assert cov["fallback_by_season"] == {2025: 1}


def test_home_favored_sign_and_passthrough(tmp_path):
    g = games([("A", 2025, 1, "H", "V", K, 7.0, 47.5, None, None)])
    w = wide(market.build(Paths(tmp_path), g, BUILD))
    assert w["market.p_home_vigfree"] > 0.5
    assert w["market.spread_line"] == 7.0
    assert w["market.total_line"] == 47.5


@requires_data
def test_moneyline_vs_spread_agree_on_real_games():
    g = store.games_frame(get_paths()).filter(pl.col("season").is_between(2022, 2025))
    d = g.filter(
        pl.col("home_moneyline").is_not_null()
        & pl.col("away_moneyline").is_not_null()
        & pl.col("spread_line").is_not_null()
    )
    p_ml = [market.vigfree_home(h, a) for h, a in zip(d["home_moneyline"], d["away_moneyline"])]
    p_sp = [norm_cdf(s / 13.5) for s in d["spread_line"]]
    df = pl.DataFrame({"a": p_ml, "b": p_sp}).drop_nulls()
    assert df.height > 500
    assert df.select(pl.corr("a", "b")).item() > 0.95
    assert df.select((pl.col("a") - pl.col("b")).abs().mean()).item() < 0.03
