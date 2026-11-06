"""Standings measures and NFL tiebreakers (ADR 0019, M14.6).

Unit tests build tiny leagues from real team codes; the replay test reruns every 2002-2025
conference-season and compares qualifiers, byes and wild-card pairings with the actual postseason.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from nfl.league.divisions import DIVISIONS
from nfl.league.standings import GameResult, Results, canon
from nfl.league.tiebreak import (
    DIVISION_STEPS,
    WILDCARD_STEPS_2,
    WILDCARD_STEPS_N,
    break_division_tie,
    break_wildcard_tie,
    rank_division,
    seed_conference,
)
from tests.conftest import DATA

FIXTURE = Path(__file__).parent / "fixtures" / "league_results_2023_2024.csv"


def g(home: str, away: str, hs: int, as_: int) -> GameResult:
    return GameResult.from_scores(home, away, hs, as_)


def rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def div_winner(games, ts, trace=None):
    return break_division_tie(Results(games), ts, rng(), trace)


def wc_winner(games, ts, trace=None, divorder=None):
    r = Results(games)
    return break_wildcard_tie(r, ts, divorder or {}, rng(), trace)


def only_step(trace) -> str:
    assert len(trace) == 1, trace
    return trace[0][1]


# --- standings measures ----------------------------------------------------------------------


def test_record_with_ties_as_half_a_win():
    r = Results([g("KC", "DEN", 20, 10), g("DEN", "KC", 17, 17), g("LV", "KC", 3, 10)])
    assert r.record("KC") == (2, 0, 1)
    assert r.pct("KC") == pytest.approx(2.5 / 3)
    assert r.record("DEN") == (0, 1, 1) and r.pct("DEN") == 0.25
    assert r.games_played == {"KC": 3, "DEN": 2, "LV": 1}


def test_division_conference_and_common_records():
    r = Results([g("BUF", "MIA", 20, 10), g("BUF", "DAL", 20, 10), g("KC", "BUF", 3, 6)])
    assert r.division_record("BUF") == (1, 0, 0)
    assert r.conference_record("BUF") == (2, 0, 0)  # DAL is the other conference
    assert r.record_vs("BUF", {"DAL"}) == (1, 0, 0)
    r2 = Results([g("BUF", "KC", 1, 0), g("MIA", "KC", 0, 1), g("MIA", "DEN", 1, 0)])
    assert r2.common_opponents(["BUF", "MIA"]) == {"KC"}


def test_strength_of_victory_and_schedule():
    # BUF beat MIA (1-1 after losing to KC) and lost to DEN (1-0 and nothing else)
    r = Results([g("BUF", "MIA", 9, 3), g("MIA", "KC", 7, 3), g("DEN", "BUF", 5, 1)])
    assert r.sov("BUF") == pytest.approx(1 / 2)  # MIA 1-1
    assert r.sos("BUF") == pytest.approx((1 + 1) / (2 + 1))  # MIA 1-1 and DEN 1-0
    assert r.sov("KC") == 0.0  # beat nobody


def test_points_ranks_share_ties_and_split_by_conference():
    r = Results([g("BUF", "MIA", 30, 10), g("DAL", "NYG", 20, 10)])
    league, conf = r.points_ranks()
    assert league["BUF"] == 2 and league["DAL"] == 3  # BUF and DAL share first in points allowed
    assert conf["BUF"] == 2 and conf["MIA"] == 4 and conf["DAL"] == 2


def test_extended_adds_games_without_touching_the_base():
    base = Results([g("BUF", "MIA", 20, 10)], remaining=[("MIA", "BUF"), ("BUF", "NE")])
    ext = base.extended([GameResult("MIA", "BUF", 1.0)])
    assert base.record("MIA") == (0, 1, 0) and base.scored
    assert ext.record("MIA") == (1, 1, 0) and ext.record("BUF") == (1, 1, 0)
    assert not ext.scored  # a simulated game has no score
    assert (
        base.left == {"BUF": 2, "MIA": 1, "NE": 1} and ext.left["BUF"] == 1 and ext.left["MIA"] == 0
    )
    assert ext.division_record("BUF") == (1, 1, 0)
    # a scored extension keeps points off the base
    ext2 = base.extended([g("BUF", "NE", 7, 3)])
    assert ext2.scored and ext2.points("BUF") == (27, 13) and base.points("BUF") == (20, 10)


def test_canon_maps_historical_codes():
    assert [canon(x) for x in ("OAK", "SD", "STL", "KC")] == ["LV", "LAC", "LA", "KC"]
    assert g("OAK", "SD", 1, 0).home == "LV"


# --- division steps: one scenario each --------------------------------------------------------

SPLIT = [g("BUF", "MIA", 20, 10), g("MIA", "BUF", 20, 10)]  # level on h2h and points


def test_div_step_1_head_to_head():
    t = []
    assert div_winner([g("MIA", "BUF", 10, 20)], ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "h2h"


def test_div_step_2_division_record():
    games = SPLIT + [g("BUF", "NYJ", 20, 10), g("NYJ", "MIA", 20, 10)]
    t = []
    assert div_winner(games, ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "division"


def test_div_step_3_common_games():
    games = SPLIT + [g("BUF", "KC", 20, 10), g("KC", "MIA", 20, 10)]
    t = []
    assert div_winner(games, ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "common"


def test_div_step_4_conference_record():
    games = SPLIT + [g("BUF", "DEN", 20, 10), g("MIA", "DAL", 20, 10)]
    t = []
    assert div_winner(games, ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "conference"


def test_div_step_5_strength_of_victory():
    games = SPLIT + [
        g("BUF", "DEN", 20, 10),
        g("MIA", "KC", 20, 10),
        g("DEN", "LV", 20, 10),  # DEN 1-1 and KC 0-1... DEN beats LV, KC loses to LV
        g("LV", "KC", 20, 10),
    ]
    t = []
    assert div_winner(games, ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "sov"


def test_div_step_6_strength_of_schedule():
    games = SPLIT + [
        g("BUF", "DEN", 20, 10),
        g("MIA", "DEN", 20, 10),  # both beat DEN: common is level, SOV level
        g("HOU", "BUF", 20, 10),  # BUF lost to strong HOU
        g("KC", "MIA", 20, 10),  # MIA lost to weak KC
        g("HOU", "LV", 20, 10),
        g("HOU", "TEN", 20, 10),
        g("LV", "KC", 20, 10),
        g("TEN", "KC", 20, 10),
    ]
    t = []
    assert div_winner(games, ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "sos"


def netall_base() -> list[GameResult]:
    """Level through SOS and through both points ranks; BUF has the better net points overall.

    Conference rank sums are 5 and 5 for BUF and MIA (80/75 against 40/37 on a four-club field).
    """
    return SPLIT + [g("BUF", "DEN", 50, 45), g("MIA", "KC", 10, 7)]


def test_div_step_7_conference_points_rank():
    games = SPLIT + [g("BUF", "DEN", 40, 0), g("MIA", "KC", 7, 0)]
    t = []
    assert div_winner(games, ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "conf_points"


def test_div_step_8_league_points_rank():
    games = netall_base() + [g("PHI", "WAS", 77, 0)]  # an NFC club that only moves league ranks
    r = Results(games)
    assert r.points_ranks()[1]["BUF"] == r.points_ranks()[1]["MIA"]
    t = []
    assert break_division_tie(r, ["BUF", "MIA"], rng(), t) == "BUF"
    assert only_step(t) == "league_points"


def test_div_step_9_net_points_in_common_games():
    games = SPLIT + [
        g("BUF", "KC", 30, 10),  # both beat KC, BUF by more
        g("MIA", "KC", 11, 10),
        g("DEN", "BUF", 30, 10),  # equal totals: BUF 70-70, MIA 70-70
        g("HOU", "MIA", 30, 29),
    ]
    t = []
    assert div_winner(games, ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "net_common"


def test_div_step_10_net_points_all_games():
    t = []
    assert div_winner(netall_base(), ["BUF", "MIA"], t) == "BUF"
    assert only_step(t) == "net_all"


def test_div_final_step_is_a_coin_and_only_then_uses_the_rng():
    r = Results(SPLIT)
    winners = set()
    for seed in range(20):
        gen = rng(seed)
        before = gen.bit_generator.state
        t = []
        winners.add(break_division_tie(r, ["BUF", "MIA"], gen, t))
        assert t[-1][1] == "coin" and gen.bit_generator.state != before
    assert winners == {"BUF", "MIA"}


def test_a_decided_tie_consumes_no_random_numbers():
    gen = rng()
    before = gen.bit_generator.state
    t = []
    break_division_tie(Results([g("MIA", "BUF", 10, 20)]), ["BUF", "MIA"], gen, t)
    assert gen.bit_generator.state == before and t[-1][1] == "h2h"


def test_points_steps_are_skipped_without_scores_then_coin():
    # level on every non-points step; points would pick BUF (see test_div_step_7)
    games = [
        GameResult(x.home, x.away, x.outcome)  # drop the scores
        for x in SPLIT + [g("BUF", "DEN", 40, 0), g("MIA", "KC", 7, 0)]
    ]
    r = Results(games)
    assert not r.scored
    t = []
    break_division_tie(r, ["BUF", "MIA"], rng(), t)
    assert t == [("division", "coin", 2)]


# --- wild-card steps ------------------------------------------------------------------------


def test_wc_step_1_head_to_head_when_played():
    t = []
    assert wc_winner([g("BAL", "BUF", 10, 20)], ["BAL", "BUF"], t) == "BUF"
    assert only_step(t) == "h2h"


def test_wc_step_1_not_played_falls_through():
    t = []
    wc_winner([g("BUF", "DEN", 20, 10), g("KC", "BAL", 20, 10)], ["BAL", "BUF"], t)
    assert only_step(t) == "conference"


def test_wc_step_2_conference_record():
    t = []
    assert wc_winner([g("BUF", "DEN", 20, 10), g("DEN", "BAL", 20, 10)], ["BAL", "BUF"], t) == "BUF"
    assert only_step(t) == "conference"


def common_games(bal_wins: int, n: int = 4) -> list[GameResult]:
    """BUF 3-1 and BAL `bal_wins`-(n - bal_wins) against n common opponents, level in conference."""
    opps = ["KC", "LV", "LAC", "HOU"][:n]
    out = []
    for i, o in enumerate(opps):
        out.append(g("BUF", o, 20, 10) if i < 3 else g(o, "BUF", 20, 10))
        out.append(g("BAL", o, 20, 10) if i < bal_wins else g(o, "BAL", 20, 10))
    return out


def test_wc_step_3_common_games_with_minimum_four():
    # conference: BUF 3-1 + loss to CLE = 3-2; BAL 2-2 + win over CIN = 3-2
    games = common_games(2) + [g("CLE", "BUF", 20, 10), g("BAL", "CIN", 20, 10)]
    t = []
    assert wc_winner(games, ["BAL", "BUF"], t) == "BUF"
    assert only_step(t) == "common4"


def test_wc_common_games_below_four_do_not_count():
    # same shape with three common games: BUF 3-0 and BAL 2-1 would split them if counted
    games = common_games(2, n=3) + [g("CLE", "BUF", 20, 10), g("BAL", "CIN", 20, 10)]
    t = []
    wc_winner(games, ["BAL", "BUF"], t)
    assert only_step(t) != "common4"


def test_wc_step_4_strength_of_victory():
    games = [
        g("BUF", "DEN", 20, 10),
        g("CLE", "BUF", 20, 10),
        g("BAL", "KC", 20, 10),
        g("CIN", "BAL", 20, 10),
        g("DEN", "LV", 20, 10),  # DEN 1-1, KC 0-2
        g("LV", "KC", 20, 10),
    ]
    t = []
    assert wc_winner(games, ["BAL", "BUF"], t) == "BUF"
    assert only_step(t) == "sov"


def test_wc_step_5_strength_of_schedule():
    games = [
        g("BUF", "DEN", 20, 10),
        g("BAL", "DEN", 20, 10),  # only one common game: below the four-game minimum
        g("CLE", "BUF", 20, 10),
        g("CIN", "BAL", 20, 10),
        g("CLE", "PIT", 20, 10),  # CLE 2-0 against CIN 1-0
    ]
    t = []
    assert wc_winner(games, ["BAL", "BUF"], t) == "BUF"
    assert only_step(t) == "sos"


def test_wc_step_6_conference_points_rank():
    games = SPLIT_BAL + [g("BUF", "DEN", 40, 0), g("BAL", "KC", 7, 0)]
    t = []
    assert wc_winner(games, ["BAL", "BUF"], t) == "BUF"
    assert only_step(t) == "conf_points"


SPLIT_BAL = [g("BUF", "BAL", 20, 10), g("BAL", "BUF", 20, 10)]


def test_wc_step_7_league_points_rank():
    games = [
        g("BUF", "BAL", 20, 10),
        g("BAL", "BUF", 20, 10),
        g("BUF", "DEN", 50, 45),
        g("BAL", "KC", 10, 7),
        g("PHI", "WAS", 77, 0),
    ]
    t = []
    assert wc_winner(games, ["BAL", "BUF"], t) == "BUF"
    assert only_step(t) == "league_points"


def test_wc_step_8_net_points_in_conference_games():
    games = SPLIT_BAL + [g("BUF", "DEN", 50, 45), g("BAL", "KC", 10, 7)]
    t = []
    assert wc_winner(games, ["BAL", "BUF"], t) == "BUF"
    assert only_step(t) == "net_conf"


def test_wc_step_9_net_points_all_games_and_step_tables():
    r = Results(SPLIT_BAL + [g("BUF", "DAL", 20, 0), g("BAL", "KC", 30, 29)])
    net_all = {n: f for n, f, _ in WILDCARD_STEPS_2}["net_all"]
    assert net_all(r, ["BAL", "BUF"]) == {"BAL": 1, "BUF": 20}
    net_conf = {n: f for n, f, _ in WILDCARD_STEPS_2}["net_conf"]
    assert net_conf(r, ["BAL", "BUF"]) == {"BAL": 1, "BUF": 0}


def test_step_order_matches_the_procedure():
    assert [s[0] for s in DIVISION_STEPS] == [
        "h2h",
        "division",
        "common",
        "conference",
        "sov",
        "sos",
        "conf_points",
        "league_points",
        "net_common",
        "net_all",
    ]
    assert [s[0] for s in WILDCARD_STEPS_2] == [
        "h2h",
        "conference",
        "common4",
        "sov",
        "sos",
        "conf_points",
        "league_points",
        "net_conf",
        "net_all",
    ]
    assert WILDCARD_STEPS_N[0][0] == "h2h_sweep" and WILDCARD_STEPS_N[1:] == WILDCARD_STEPS_2[1:]
    assert [s[2] for s in DIVISION_STEPS] == [False] * 6 + [True] * 4
    assert [s[2] for s in WILDCARD_STEPS_2] == [False] * 5 + [True] * 4


# --- rules -----------------------------------------------------------------------------------


def three_way_sweep_games() -> list[GameResult]:
    """BUF, BAL and KC (three divisions); BUF beat both others, BAL beat KC."""
    return [g("BUF", "BAL", 20, 10), g("BUF", "KC", 20, 10), g("BAL", "KC", 20, 10)]


def test_three_club_sweep_rule_needs_a_sweep():
    divorder = {d: [t] for t in ("BUF", "BAL", "KC") for d in [DIVISIONS[t][1]]}
    t = []
    r = Results(three_way_sweep_games())
    assert break_wildcard_tie(r, ["BAL", "BUF", "KC"], divorder, rng(), t) == "BUF"
    assert t[0][1] == "h2h_sweep"
    # nobody swept: a cycle sends it to the next step with all three still tied
    cyc = Results([g("BUF", "BAL", 20, 10), g("BAL", "KC", 20, 10), g("KC", "BUF", 20, 10)])
    t = []
    break_wildcard_tie(cyc, ["BAL", "BUF", "KC"], divorder, rng(), t)
    assert t[0][1] != "h2h_sweep"


def test_swept_club_is_eliminated_and_the_rest_restart_as_a_pair():
    # KC lost to both others; BUF-BAL split 1-1 so the restarted pair goes to its own step 1
    games = [
        g("BUF", "KC", 20, 10),
        g("BAL", "KC", 20, 10),
        g("BUF", "BAL", 20, 10),
        g("BAL", "BUF", 20, 10),
        g("BAL", "DEN", 20, 10),
    ]
    divorder = {DIVISIONS[x][1]: [x] for x in ("BUF", "BAL", "KC")}
    # No sweep by anyone: BUF is 2-1 vs the others, BAL 2-1, KC 0-2 -> swept, eliminated
    t = []
    r = Results(games)
    break_wildcard_tie(r, ["BAL", "BUF", "KC"], divorder, rng(), t)
    assert [x[2] for x in t] == [2]  # decided as a two-club tie after the elimination
    assert t[0][1] == "conference"  # pair: h2h split, so conference record decides (BAL beat DEN)


def test_division_first_reduction_for_three_club_wild_card_ties():
    # BUF and MIA share a division (BUF ahead); BAL is elsewhere. BUF would lose the 3-way
    # tiebreak to BAL, so reducing to the best club per division matters: MIA must drop out.
    games = [g("MIA", "BAL", 30, 10), g("BAL", "BUF", 20, 10), g("BUF", "MIA", 20, 10)]
    divorder = {
        "AFC East": ["BUF", "MIA", "NE", "NYJ"],
        "AFC North": ["BAL", "CIN", "CLE", "PIT"],
    }
    t = []
    r = Results(games)
    w = break_wildcard_tie(r, ["BAL", "BUF", "MIA"], divorder, rng(), t)
    assert w == "BAL"  # BUF vs BAL: head-to-head
    assert t == [("wildcard", "h2h", 2)]


def test_restart_after_elimination_in_a_division():
    # KC-less example: three clubs; MIA loses h2h overall and drops, BUF-NE restart at step 1
    games = [
        g("BUF", "MIA", 20, 10),
        g("NE", "MIA", 20, 10),
        g("MIA", "NYJ", 20, 10),
        g("BUF", "NE", 20, 10),
        g("NE", "BUF", 20, 10),
        g("BUF", "NYJ", 20, 10),
    ]
    t = []
    w = div_winner(games, ["BUF", "MIA", "NE"], t)
    # all three: BUF 3-1, NE 3-1 vs the others, MIA 0-2... actually MIA 0-2, BUF/NE restart
    assert w == "BUF"
    assert [x[2] for x in t] == [2]


def test_only_one_club_advances_per_step():
    # four clubs level on everything: the order is made by repeated single picks
    r = Results([])
    order = rank_division(r, "NFC East", rng(3))
    assert sorted(order) == ["DAL", "NYG", "PHI", "WAS"]
    # a different seed gives a different order, so every slot was drawn separately
    assert any(rank_division(r, "NFC East", rng(s)) != order for s in range(4, 12))


def test_rank_division_orders_by_record_then_tiebreak():
    games = [g("DAL", "NYG", 20, 10), g("NYG", "DAL", 10, 20), g("PHI", "WAS", 20, 10)]
    # DAL 2-0, PHI 1-0, then NYG 0-2 and WAS 0-1: WAS ahead of NYG on percentage
    assert rank_division(Results(games), "NFC East", rng()) == ["DAL", "PHI", "WAS", "NYG"]


def test_seed_conference_orders_winners_then_wild_cards():
    # AFC: win totals by team from a round robin of one-sided results
    ranked = [
        "BUF",
        "MIA",
        "NE",
        "NYJ",
        "BAL",
        "CIN",
        "CLE",
        "PIT",
        "HOU",
        "IND",
        "JAX",
        "TEN",
        "DEN",
        "KC",
        "LAC",
        "LV",
    ]
    games = []
    for i, a in enumerate(ranked):
        for b in ranked[i + 1 :]:
            games.append(g(a, b, 20, 10))  # earlier in the list always wins
    seeds = seed_conference(Results(games), "AFC", rng())
    # division winners BUF, BAL, HOU, DEN seeded by record (BUF 15-0, BAL 11-4, ...), then wild cards
    assert seeds == ["BUF", "BAL", "HOU", "DEN", "MIA", "NE", "NYJ"]
    assert seed_conference(Results(games), "AFC", rng(), n_seeds=6) == seeds[:6]


# --- replay: every conference-season ----------------------------------------------------------


def _load_fixture() -> pl.DataFrame:
    return pl.read_csv(FIXTURE)


def _load_real() -> pl.DataFrame:
    df = pl.read_parquet(
        str(DATA.curated_table("games")) + "/*/*.parquet", hive_partitioning=True
    ).filter(pl.col("season") >= 2002)
    return df.select(
        "season", "game_type", "week", "home_team", "away_team", "home_score", "away_score"
    )


def actual_seeds_check(df: pl.DataFrame, season: int, conf: str, seeds: list[str]) -> list[str]:
    """Compare engine seeds with the postseason. Returns the mismatches (empty = match).

    Qualifiers are the conference's clubs that played a postseason game; byes are qualifiers
    missing from the wild-card round; the wild-card games must pair seed 3 v 6 / 4 v 5 (6 clubs)
    or 2 v 7 / 3 v 6 / 4 v 5 (7 clubs) with the better seed at home.
    """
    post = df.filter((pl.col("season") == season) & (pl.col("game_type") != "REG"))
    teams = {canon(t) for t in post["home_team"]} | {canon(t) for t in post["away_team"]}
    qualified = {t for t in teams if DIVISIONS[t][0] == conf}
    wc = post.filter(pl.col("game_type") == "WC").with_columns(
        pl.col("home_team").map_elements(canon, return_dtype=pl.String),
        pl.col("away_team").map_elements(canon, return_dtype=pl.String),
    )
    wc = wc.filter(pl.col("home_team").is_in(list(qualified)))
    played = set(wc["home_team"]) | set(wc["away_team"])
    nby = 1 if season >= 2020 else 2
    n = len(seeds)
    want = {(seeds[i], seeds[n - 1 - (i - nby)]) for i in range(nby, nby + (n - nby) // 2)}
    got = set(zip(wc["home_team"], wc["away_team"], strict=True))
    bad = []
    if set(seeds) != qualified:
        bad.append(f"qualifiers {sorted(seeds)} vs {sorted(qualified)}")
    if qualified - played != set(seeds[:nby]):
        bad.append(f"byes {sorted(qualified - played)} vs {seeds[:nby]}")
    if want != got:
        bad.append(f"pairings {sorted(want)} vs {sorted(got)}")
    return bad


def replay(df: pl.DataFrame, seasons: list[int], with_scores: bool = True) -> tuple[int, list[str]]:
    """(conference-seasons checked, mismatches)."""
    checked, bad = 0, []
    for season in seasons:
        reg = df.filter((pl.col("season") == season) & (pl.col("game_type") == "REG"))
        games = [
            g(h, a, hs, as_)
            if with_scores
            else GameResult(canon(h), canon(a), 1.0 if hs > as_ else 0.0 if hs < as_ else 0.5)
            for h, a, hs, as_ in reg.select(
                "home_team", "away_team", "home_score", "away_score"
            ).iter_rows()
        ]
        r = Results(games)
        for conf in ("AFC", "NFC"):
            seeds = seed_conference(r, conf, rng(season), n_seeds=7 if season >= 2020 else 6)
            checked += 1
            bad += [f"{season} {conf}: {m}" for m in actual_seeds_check(df, season, conf, seeds)]
    return checked, bad


def test_replay_fixture_seasons():
    checked, bad = replay(_load_fixture(), [2023, 2024])
    assert checked == 4 and not bad, bad


def test_replay_fixture_seasons_without_scores_needs_no_points_steps():
    # no real tie from 2002 to 2025 went past strength of victory, so the cap changes nothing
    checked, bad = replay(_load_fixture(), [2023, 2024], with_scores=False)
    assert checked == 4 and not bad, bad


requires_games = pytest.mark.skipif(
    not DATA.curated_table("games").exists(), reason="needs curated games (run nfl run-all)"
)


@requires_games
@pytest.mark.parametrize("with_scores", [True, False], ids=["points", "capped"])
def test_replay_every_conference_season_2002_2025(with_scores):
    checked, bad = replay(_load_real(), list(range(2002, 2026)), with_scores=with_scores)
    assert checked == 48 and not bad, bad
