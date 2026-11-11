"""Paths to an upset (ADR 0028, M25.4): the upset_conditions model, the bucket table, the sentences."""

import re
from dataclasses import asdict

import numpy as np
import polars as pl
import pytest

from nfl import catalog
from nfl import paths as P
from nfl.config import Paths, get_paths
from nfl.sql import runner

from .conftest import requires_data
from .synth import PLAY, SCHEMA_PLAYS, write_games, write_table

EXTRA = {"yards_gained": 5.0, "special_teams_play": 0.0}
SCHEMA = {
    **SCHEMA_PLAYS,
    "season": pl.Int64,
    "yards_gained": pl.Float64,
    "special_teams_play": pl.Float64,
}


def pl_(**kw) -> dict:
    return PLAY | EXTRA | kw


def write_plays(paths: Paths, plays: list[dict]) -> None:
    write_table(paths, "plays", plays, SCHEMA)


def game(gid, week, home, away, result, spread=3.0, season=2022):
    return {"game_id": gid, "season": season, "week": week, "home_team": home, "away_team": away,
            "result": result, "spread_line": spread}  # fmt: skip


def planted_plays(gid="g1", season=2022):
    """A (home, favored by 3) loses to B by 4. From B's view every condition holds; from A's none."""
    k = {"season": season, "game_id": gid}
    a = {"posteam": "A", "defteam": "B"}
    b = {"posteam": "B", "defteam": "A"}
    return [
        pl_(**k, **a, play_id=1, epa=-0.5, interception=1.0),  # A giveaway (early down)
        pl_(**k, **a, play_id=2, epa=-1.0, sack=1.0, yards_gained=-7.0),  # A sacked
        pl_(**k, **a, play_id=3, epa=-1.0, sack=1.0, yards_gained=-6.0),  # A sacked again
        pl_(**k, **b, play_id=4, epa=1.0, yards_gained=25.0),  # B explosive pass, early down
        pl_(**k, **b, play_id=5, epa=0.5, down=3.0),  # not early down
        pl_(**k, **b, play_id=6, epa=1.5, special_teams_play=1.0, **{"pass": 0.0}, down=4.0),
        pl_(**k, **a, play_id=7, epa=-2.0, special_teams_play=1.0, **{"pass": 0.0}, down=4.0),
        pl_(**k, **a, play_id=8, epa=9.0, wp=0.99),  # garbage time: not counted early down
    ]  # fmt: skip


def build(tmp_path, plays, games):
    paths = Paths(tmp_path)
    write_plays(paths, plays)
    write_games(paths, games)
    runner.build(paths, "upset_conditions")
    return paths, pl.read_parquet(runner.output_path(paths, "upset_conditions"))


def test_planted_game_grades_each_condition_from_both_views(tmp_path):
    _, df = build(tmp_path, planted_plays(), [game("g1", 3, "A", "B", -4)])
    assert df.height == 2
    b = df.filter(pl.col("team") == "B").row(0, named=True)
    a = df.filter(pl.col("team") == "A").row(0, named=True)
    assert (b["role"], b["size_bucket"], b["spread"], b["won"], b["margin"]) == (
        "dog",
        "3-6.5",
        -3.0,
        True,
        4,
    )
    assert (a["role"], a["spread"], a["won"]) == ("fav", 3.0, False)
    assert b["turnover_margin"] == 1 and a["turnover_margin"] == -1
    assert b["sack_margin"] == 2 and a["sack_margin"] == -2
    assert (b["explosives"], b["explosives_opp"]) == (1, 0)
    assert b["early_down_epa"] == 1.0 and b["early_down_epa_opp"] == pytest.approx(
        -2.5 / 3
    )  # wp 0.99 play out
    assert b["st_epa_net"] == pytest.approx(3.5) and a["st_epa_net"] == pytest.approx(-3.5)
    for c in P.CONDITIONS:
        assert b[c.column] is True, c.id
        assert a[c.column] is False, c.id


def test_conditions_are_strict_and_ties_are_not_wins(tmp_path):
    k = {"season": 2022, "game_id": "g1"}
    plays = [  # one giveaway each, one sack each, equal explosives: no condition holds for either side
        pl_(**k, posteam="A", defteam="B", play_id=1, epa=0.1, interception=1.0, sack=1.0),
        pl_(**k, posteam="B", defteam="A", play_id=2, epa=0.1, fumble_lost=1.0, sack=1.0),
    ]
    _, df = build(tmp_path, plays, [game("g1", 1, "A", "B", 0, spread=-1.0)])
    for r in df.iter_rows(named=True):
        assert not any(r[c.column] for c in P.CONDITIONS)
        assert r["won"] is False and r["margin"] == 0  # a tie is not a win
    assert df.filter(pl.col("team") == "A")["role"][0] == "dog"  # home team at spread -1


def test_old_codes_are_mapped_to_play_codes(tmp_path):
    k = {"season": 2010, "game_id": "g1"}
    plays = [
        pl_(**k, posteam="LAC", defteam="LV", play_id=1),
        pl_(**k, posteam="LV", defteam="LAC", play_id=2),
    ]
    _, df = build(tmp_path, plays, [game("g1", 1, "SD", "OAK", 3, season=2010)])
    assert sorted(df["team"]) == ["LAC", "LV"]


def outcome_and_paths(tmp_path):
    games = [game("g1", 3, "A", "B", -4), game("g0", 1, "B", "C", -10, spread=-1.0)]
    plays = planted_plays() + [
        pl_(season=2022, game_id="g0", posteam="B", defteam="C", play_id=1, epa=0.4),
        pl_(
            season=2022,
            game_id="g0",
            posteam="C",
            defteam="B",
            play_id=2,
            epa=0.1,
            interception=1.0,
        ),
    ]
    return build(tmp_path, plays, games)


def test_paths_outcome_for_the_planted_dog(tmp_path):
    _, df = outcome_and_paths(tmp_path)
    o = P.paths_outcome("g1", df)
    assert o.dog == "B" and o.favorite == "A" and o.dog_won and not o.tied
    assert o.met == [c.id for c in P.CONDITIONS]
    assert o.sentence.startswith("B won the turnover battle, won early downs")
    assert o.sentence.endswith("; it won.")
    assert P.paths_outcome("nope", df) is None


def test_a_dog_that_met_nothing_and_lost(tmp_path):
    _, df = outcome_and_paths(tmp_path)
    o = P.paths_outcome("g0", df)  # C is the home dog? B home, spread -1: B dog, lost by 10
    assert o.dog == "B" and not o.dog_won
    assert (
        o.met == ["turnovers", "early_down"]
        and o.sentence == "B won the turnover battle and won early downs; it lost."
    )


def test_pickem_and_missing_line_return_none(tmp_path):
    _, df = outcome_and_paths(tmp_path)
    g = {"season": 2022, "week": 5, "home_team": "A", "away_team": "B", "spread_line": 0.0}
    assert P.upset_paths(g, 5, df) is None
    assert P.upset_paths(g | {"spread_line": None}, 5, df) is None
    pk = build(tmp_path / "pk", planted_plays(), [game("g1", 3, "A", "B", -4, spread=0.0)])[1]
    assert P.paths_outcome("g1", pk) is None and pk["role"].unique().to_list() == ["pick"]


def synth_frame(seed=1, seasons=range(2015, 2022), weeks=12):
    rng = np.random.default_rng(seed)
    rows = []
    for s in [*seasons, 2022]:
        for w in range(1, weeks + 1):
            for h, a in (("A", "B"), ("C", "D")):
                spread = float(rng.choice([1.5, 3.0, 4.5, 6.0, 8.0, 12.0]))
                flags = {c.column: rng.random() < 0.3 for c in P.CONDITIONS}
                win = rng.random() < 0.4
                for team, opp, sp in ((h, a, spread), (a, h, -spread)):
                    dog = sp < 0
                    rows.append({
                        "season": s, "week": w, "game_id": f"{s}_{w}_{team}", "team": team, "opponent": opp,
                        "spread": sp, "role": "dog" if dog else "fav", "size_bucket": P.bucket_of(sp),
                        "won": bool(win) == dog, **(flags if dog else {k: not v for k, v in flags.items()}),
                    })  # fmt: skip
    return pl.DataFrame(rows)


def test_point_in_time_ignores_the_game_week_and_later(tmp_path):
    df = synth_frame()
    g = {"season": 2022, "week": 6, "home_team": "A", "away_team": "B", "spread_line": 3.0}
    base = P.upset_paths(g, 6, df).to_dict()
    # later and same-week games of this season, and later seasons, change nothing
    later = df.filter((pl.col("season") == 2022) & (pl.col("week") >= 6)).with_columns(
        [pl.lit(True).alias(c.column) for c in P.CONDITIONS] + [pl.lit(True).alias("won")]
    )
    after = df.filter(~((pl.col("season") == 2022) & (pl.col("week") >= 6)))
    f2 = pl.concat([after, later, later.with_columns(season=pl.lit(2023).cast(pl.Int64))])
    assert P.upset_paths(g, 6, f2).to_dict() == base
    assert [asdict(c) for c in P.bucket_table(df, 2022)] == [
        asdict(c) for c in P.bucket_table(f2, 2022)
    ]
    # control: an earlier week does move the dog's rates, and an earlier season moves the table
    f3 = df.with_columns(
        pl.when((pl.col("season") == 2022) & (pl.col("week") == 5))
        .then(True)
        .otherwise(pl.col("turnovers"))
        .alias("turnovers")
    )
    assert P.upset_paths(g, 6, f3).to_dict() != base
    assert P.upset_paths(g, 5, f3).to_dict() == P.upset_paths(g, 5, df).to_dict()
    f4 = df.with_columns(
        pl.when(pl.col("season") == 2015).then(True).otherwise(pl.col("won")).alias("won")
    )
    assert [asdict(c) for c in P.bucket_table(f4, 2022)] != [
        asdict(c) for c in P.bucket_table(df, 2022)
    ]


def numbers_in(obj) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= numbers_in(v)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, int):
        out.add(str(obj))
    elif isinstance(obj, float):
        out |= {str(obj), f"{obj:g}", str(round(obj)), str(round(100 * obj))}
    return out


@pytest.mark.parametrize("spread", [1.5, 3.0, -6.0, 8.0, 12.0])
@pytest.mark.parametrize("week", [1, 6, 12])
def test_no_sentence_number_that_is_not_in_the_record(spread, week):
    df = synth_frame()
    g = {"season": 2022, "week": week, "home_team": "A", "away_team": "B", "spread_line": spread}
    r = P.upset_paths(g, week, df)
    assert r is not None and len(r.top) == 3 and r.sentence.startswith(f"How {r.dog} wins: ")
    assert "probab" not in r.sentence and "chance" not in r.sentence
    have = numbers_in(r.to_dict())
    for n in re.findall(r"\d+(?:\.\d+)?", r.sentence):
        assert n in have, (n, r.sentence)
    # the pct in each clause is the record's own
    for cid in r.top:
        c = next(c for c in r.conditions if c.id == cid)
        assert f"won {c.win_rate_pct}%" in r.sentence
    assert [c.win_rate_if for c in r.conditions] == sorted(
        (c.win_rate_if for c in r.conditions), reverse=True
    )


def test_outcome_sentence_has_no_digits(tmp_path):
    _, df = outcome_and_paths(tmp_path)
    assert not re.search(r"\d", P.paths_outcome("g1", df).sentence)


def test_rates_count_the_dogs_production_and_the_favorites_allowance():
    df = synth_frame(weeks=4)
    g = {"season": 2022, "week": 4, "home_team": "A", "away_team": "B", "spread_line": 3.0}
    r = P.upset_paths(g, 4, df)
    t = next(c for c in r.conditions if c.id == "turnovers")
    b = df.filter((pl.col("season") == 2022) & (pl.col("week") < 4) & (pl.col("team") == "B"))
    a = df.filter((pl.col("season") == 2022) & (pl.col("week") < 4) & (pl.col("opponent") == "A"))
    assert (t.dog_games, t.dog_count) == (3, int(b["turnovers"].sum()))
    assert (t.fav_games, t.fav_count) == (3, int(a["turnovers"].sum()))
    assert (
        P.upset_paths(g, 1, df).conditions[0].dog_games == 0
    )  # nothing yet: the sentence still reads
    assert "no games yet" in P.upset_paths(g, 1, df).sentence


@requires_data
def test_bucket_table_reproduces_the_adr_numbers_on_real_data():
    paths = get_paths()
    con = catalog.connect(paths)
    df = con.sql((runner.MODELS_DIR / "upset_conditions.sql").read_text()).pl()
    cells = {(c.bucket, c.condition): c for c in P.bucket_table(df, 2026)}
    for bucket, base in (("0-2.5", 46), ("3-6.5", 37), ("7-9.5", 23), ("10+", 14)):
        assert abs(100 * cells[(bucket, "turnovers")].base_rate - base) <= 1, bucket
    for cond, want in (
        ("turnovers", 69),
        ("early_down", 67),
        ("explosives", 56),
        ("sacks", 63),
        ("special_teams", 44),
    ):
        assert abs(100 * cells[("3-6.5", cond)].win_rate_if - want) <= 1, cond
    # NOTE: 'happens' for turnovers is 35% here against the ADR's 29%; see the M25.4 hand-back.
