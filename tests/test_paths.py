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

EXTRA = {
    "yards_gained": 5.0, "special_teams_play": 0.0, "yardline_100": 50.0, "third_down_converted": 0.0,
    "third_down_failed": 0.0, "touchdown": 0.0, "td_team": None, "drive": 1.0,
}  # fmt: skip
SCHEMA = {
    **SCHEMA_PLAYS,
    "season": pl.Int64,
    "yards_gained": pl.Float64,
    "special_teams_play": pl.Float64,
    "yardline_100": pl.Float64,
    "third_down_converted": pl.Float64,
    "third_down_failed": pl.Float64,
    "touchdown": pl.Float64,
    "td_team": pl.String,
    "drive": pl.Float64,
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
    for c in P.CORE:
        assert b[c.column] is True, c.id
        assert a[c.column] is False, c.id


def test_the_six_newer_conditions_from_both_views(tmp_path):
    """B passes better, breaks a 10-yard run, converts its third down, runs more successfully, hits a
    deep pass and scores on its red-zone trip; A does none of it."""
    k = {"season": 2022, "game_id": "g1"}
    a = {"posteam": "A", "defteam": "B"}
    b = {"posteam": "B", "defteam": "A"}
    run = {"pass": 0.0, "rush": 1.0}
    plays = [
        pl_(**k, **b, play_id=1, epa=0.5, yards_gained=25.0),  # deep pass
        pl_(
            **k, **b, play_id=2, epa=0.3, yards_gained=12.0, success=1.0, **run
        ),  # big, successful run
        pl_(**k, **b, play_id=3, down=3.0, third_down_converted=1.0),
        pl_(**k, **b, play_id=4, yardline_100=10.0, touchdown=1.0, td_team="B", drive=1.0),
        pl_(**k, **a, play_id=5, epa=-0.5, yards_gained=4.0),
        pl_(**k, **a, play_id=6, epa=-0.2, yards_gained=3.0, success=0.0, **run),
        pl_(**k, **a, play_id=7, down=3.0, third_down_failed=1.0),
        pl_(**k, **a, play_id=8, yardline_100=15.0, drive=2.0),
    ]
    _, df = build(tmp_path, plays, [game("g1", 3, "A", "B", -4)])
    b_, a_ = (df.filter(pl.col("team") == t).row(0, named=True) for t in ("B", "A"))
    new = [c for c in P.CONDITIONS if c not in P.CORE]
    assert len(new) == 6
    for c in new:
        assert b_[c.column] is True, c.id
        assert a_[c.column] is False, c.id
    assert (b_["third_down_rate"], a_["third_down_rate"]) == (1.0, 0.0)
    assert (b_["rz_td_rate"], a_["rz_td_rate"]) == (1.0, 0.0)
    assert (b_["big_runs"], b_["deep_passes"]) == (1, 1)


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
    # the five plus the passing game (B's deep pass); outcomes list tier-1 conditions only
    assert o.met == [c.id for c in P.CORE] + ["pass_game"]
    assert [c.id for c in o.conditions] == [c.id for c in P.CONDITIONS if c.tier == 1]
    assert o.sentence.startswith("B won the turnover battle, won early downs")
    assert o.sentence.endswith("; it won.")
    assert P.paths_outcome("nope", df) is None


def test_a_dog_that_met_nothing_and_lost(tmp_path):
    _, df = outcome_and_paths(tmp_path)
    o = P.paths_outcome("g0", df)  # C is the home dog? B home, spread -1: B dog, lost by 10
    assert o.dog == "B" and not o.dog_won
    assert (
        o.met == ["turnovers", "early_down", "pass_game"]
        and o.sentence
        == "B won the turnover battle, won early downs and out-passed the other side; it lost."
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
    assert r is not None
    assert "probab" not in r.sentence and "chance" not in r.sentence
    have = numbers_in(r.to_dict())
    for n in re.findall(r"\d+(?:\.\d+)?", r.sentence):
        assert n in have, (n, r.sentence)
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
    assert "Too early" in P.upset_paths(g, 1, df).sentence


def ranks_frame(n=20, weeks=6, season=2022, seed=3):
    """Twenty teams with a fixed strength per condition stat, so the ranks are known."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(n)]
    strength = {t: {c.id: rng.normal() for c in P.CONDITIONS} for t in teams}
    rows = []
    for w in range(1, weeks + 1):
        order = rng.permutation(teams)
        for h, a in zip(order[::2], order[1::2], strict=True):
            for team, opp in ((h, a), (a, h)):
                row = {
                    "season": season,
                    "week": w,
                    "game_id": f"{w}_{h}",
                    "team": team,
                    "opponent": opp,
                }
                for c in P.CONDITIONS:
                    row[c.stat] = strength[team][c.id] + 0.1 * rng.normal()
                    row[c.stat_opp] = strength[opp][c.id] + 0.1 * rng.normal()
                rows.append(row)
    return pl.DataFrame(rows), strength


def test_team_ranks_are_point_in_time_and_best_is_first():
    df, _ = ranks_frame()
    base = P.team_ranks(df, 2022, 5)
    assert P.team_ranks(df, 2022, 3) == {}  # before MIN_RANK_WEEK
    # the as-of week and later change nothing
    later = df.filter(pl.col("week") >= 5).with_columns(
        [pl.lit(99.0).alias(c.stat) for c in P.CONDITIONS]
    )
    assert P.team_ranks(pl.concat([df.filter(pl.col("week") < 5), later]), 2022, 5) == base
    # an earlier week does
    moved = df.with_columns(
        pl.when(pl.col("week") == 4).then(99.0).otherwise(pl.col("explosives")).alias("explosives")
    )
    assert P.team_ranks(moved, 2022, 5) != base
    # rank 1 = best: most explosives, fewest giveaways; a defense is best when it allowed least
    exp = {t: r["explosives"] for t, r in base.items()}
    top = min(exp, key=lambda t: exp[t].off_rank)
    assert exp[top].off_value == max(r.off_value for r in exp.values())
    gv = {t: r["turnovers"] for t, r in base.items()}
    assert gv[min(gv, key=lambda t: gv[t].off_rank)].off_value == min(
        r.off_value for r in gv.values()
    )
    assert gv[min(gv, key=lambda t: gv[t].def_rank)].def_value == max(
        r.def_value for r in gv.values()
    )


def _paths_with(dog_ranks: dict, fav_ranks: dict, n=32):
    p = P.UpsetPaths("g", 2026, 9, 9, "DOG", "FAV", 3.0, "3-6.5", 0.37, 37)
    p.conditions = [
        P.ConditionPath(c.id, c.label, "", 0.6, 60, 100, 0.3, 30, 0.37, 37, 0, 0, 0, 0,
                        c.plausibility, c.measured_r, "")
        for c in P.CONDITIONS
    ]  # fmt: skip

    def rows(rk):
        return {
            c.id: P.RankRow(c.id, c.label, c.off_noun, c.def_noun, 0.0, rk.get(c.id, (16, 16))[0], 0.0,
                            rk.get(c.id, (16, 16))[1], n, 8)
            for c in P.CONDITIONS
        }  # fmt: skip

    return p, {"DOG": rows(dog_ranks), "FAV": rows(fav_ranks)}


def test_levers_prefer_tier_one_cap_at_four_and_keep_one_per_family():
    # (off_rank, def_rank). The dog's offense is strong on everything; the favorite's defense is weak.
    strong = {c.id: (2, 16) for c in P.CONDITIONS}
    weak = {c.id: (16, 30) for c in P.CONDITIONS}
    p, ranks = _paths_with(strong, weak)
    levers, chips = P.levers_and_chips(p, ranks)
    assert len(levers) == P.MAX_LEVERS
    assert all(lv.tier == 1 for lv in levers)  # tier 2 only after every tier-1 lever
    fams = [P.BY_ID[lv.id].family for lv in levers if P.BY_ID[lv.id].family]
    assert len(fams) == len(set(fams))
    assert {lv.side for lv in levers} <= {"offense", "net"}
    # a tier-2 lever shows when the tier-1 conditions aren't mismatches
    only_rz = {"red_zone": (3, 16)}
    p, ranks = _paths_with(only_rz, {"red_zone": (16, 25)})
    levers, chips = P.levers_and_chips(p, ranks)
    assert [lv.id for lv in levers] == ["red_zone"]
    assert {c.kind for c in chips} == {"even"} and all(P.BY_ID[c.id].tier == 1 for c in chips)


def test_a_lever_needs_a_strong_dog_unit_and_a_gap():
    # gap 14 but the dog's unit is 18th: not a lever, a 'weak' chip
    p, ranks = _paths_with({"turnovers": (16, 18)}, {"turnovers": (32, 16)})
    levers, chips = P.levers_and_chips(p, ranks)
    assert levers == [] and next(c for c in chips if c.id == "turnovers").kind == "weak"
    # the favorite's unit is far better: a 'favorite' chip
    p, ranks = _paths_with({"sacks": (25, 25)}, {"sacks": (5, 5)})
    _, chips = P.levers_and_chips(p, ranks)
    assert next(c for c in chips if c.id == "sacks").kind == "favorite"


def test_lever_headlines_and_sentence_use_only_record_ranks():
    p, ranks = _paths_with(
        {"turnovers": (16, 1), "pass_game": (2, 16)}, {"turnovers": (28, 16), "pass_game": (16, 17)}
    )
    p.levers, p.chips = P.levers_and_chips(p, ranks)
    p.sentence = P._paths_sentence(p)
    assert [lv.id for lv in p.levers] == ["turnovers", "pass_game"]
    assert p.levers[0].headline == "DOG's takeaways (1st) against FAV's ball security (28th)"
    have = numbers_in(p.to_dict())
    for n in re.findall(r"\d+", p.sentence):
        assert n in have, (n, p.sentence)


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
