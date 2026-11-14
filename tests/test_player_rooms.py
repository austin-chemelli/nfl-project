"""Position-room grades (M24.7 round 3, PR B): league ranks from the weeks a room was near full
strength, the skill rooms from their starters' own plays, and the estimate now."""

import polars as pl

from nfl.players import rooms as R


def _sums(teams: dict[str, list[tuple[int, float]]]) -> pl.DataFrame:
    """Weekly sums where every team's stats are one number per week: `x` per unit of every
    denominator, so a team-week with x = 1.0 has every rate at 1.0."""
    cols = {n for n, d in R.RATIO.values()} | {d for _, d in R.RATIO.values()}
    rows = []
    for team, weeks in teams.items():
        for week, x in weeks:
            r = {"team": team, "week": week}
            for n, d in R.RATIO.values():
                r[d] = 10.0
                r[n] = 10.0 * x
            rows.append(r)
    return pl.DataFrame(rows).select("team", "week", *sorted(cols))


def test_the_line_is_graded_on_its_healthy_weeks_and_ranked_league_wide():
    # AAA's line allowed the most in its healthy weeks (1-3) and nothing in week 4, when it was hurt
    sums = _sums({
        "AAA": [(1, 3.0), (2, 3.0), (3, 3.0), (4, -9.0)],
        "BBB": [(1, 1.0), (2, 1.0), (3, 1.0), (4, 1.0)],
        "CCC": [(1, 0.0), (2, 0.0), (3, 0.0), (4, 0.0)],
    })  # fmt: skip
    counted = R.healthy_weeks(
        {"AAA": [{"week": w, "rooms": {"OL": 1.0 if w < 4 else 0.4}} for w in (1, 2, 3, 4)]}
    )
    st = R.stats(sums, counted)
    assert st["AAA"]["OL"]["games"] == 3 and st["AAA"]["OL"]["ol_sack"] == 3.0
    assert st["BBB"]["OL"]["games"] == 4  # no health rows: every week counts
    g = R.grades(st)
    # sacks allowed: lower is better, so the line allowing the most ranks last on that stat
    sack = {t: next(x["rank"] for x in g[t]["OL"]["stats"] if x["key"] == "ol_sack") for t in g}
    assert [sack[t] for t in ("AAA", "BBB", "CCC")] == [3, 2, 1]
    assert g["CCC"]["OL"]["basis"] == "team"


def test_too_few_healthy_weeks_fall_back_to_every_week():
    sums = _sums(
        {"AAA": [(1, 1.0), (2, 2.0), (3, 3.0), (4, 4.0)], "BBB": [(w, 0.0) for w in (1, 2, 3, 4)]}
    )
    counted = R.healthy_weeks(
        {"AAA": [{"week": 1, "rooms": {"OL": 0.9}}, {"week": 2, "rooms": {"OL": 0.5}}]}
    )
    assert R.stats(sums, counted)["AAA"]["OL"]["games"] == 4


def test_a_strong_room_missing_its_players_falls_further_than_a_weak_one():
    rooms = {t: {"WR": {"z": z, "rank": r, "label": R.label(r)}} for t, z, r in
             [("LA", 1.5, 1), ("MID", 0.0, 2), ("BAD", -1.2, 3), ("X", -0.5, 3)]}  # fmt: skip
    out = R.with_now(
        rooms, {"LA": [{"grp": "WR", "health": 0.3}], "BAD": [{"grp": "WR", "health": 0.3}]}
    )
    la, bad = out["LA"][0], out["BAD"][0]
    assert la["rank"] == 1 and la["now_rank"] > 2  # from the top to below the middle
    assert la["z"] - la["z_now"] > bad["z"] - bad["z_now"]  # an elite room has further to fall
    assert out["MID"][0]["now_rank"] == out["MID"][0]["rank"] or out["MID"][0]["health"] is None


def test_labels_cover_every_rank():
    assert [R.label(r) for r in (1, 6, 7, 14, 15, 24, 25, 32)] == [
        "elite", "elite", "good", "good", "average", "average", "weak", "weak"
    ]  # fmt: skip


def test_skill_rooms_use_their_starters_plays_shrunk_toward_the_league():
    import duckdb

    con = duckdb.connect()
    rows = [  # (season, receiver, epa, success): a star with many targets, a rookie with 2 great ones
        *[(2026, "star", 0.6, 1) for _ in range(150)], *[(2025, "star", 0.6, 1) for _ in range(100)],
        (2026, "rookie", 3.0, 1), (2026, "rookie", 3.0, 1),
        *[(2026, "plain", 0.0, 0) for _ in range(150)],
    ]  # fmt: skip
    plays = pl.DataFrame(
        [{"season": s, "season_type": "REG", "special_teams_play": 0, "pass": 1, "rush": 0,
          "qb_dropback": 1, "receiver_player_id": r, "rusher_player_id": None,
          "passer_player_id": "qb", "epa": e, "qb_epa": e, "success": x} for s, r, e, x in rows]
    )  # fmt: skip
    con.register("plays", plays)
    starters = {"AAA": [{"gsis_id": "star", "grp": "WR"}], "BBB": [{"gsis_id": "rookie", "grp": "WR"}],
                "CCC": [{"gsis_id": "plain", "grp": "WR"}]}  # fmt: skip
    pr = R.player_rooms(con, 2026, starters)
    assert pr["AAA"]["WR"]["plays"] == 250
    # two great targets barely move the rookie off the league average; the star's 250 do
    assert pr["AAA"]["WR"]["wr_epa"] > pr["BBB"]["WR"]["wr_epa"] > pr["CCC"]["WR"]["wr_epa"]
    assert pr["BBB"]["WR"]["wr_epa"] < 0.5
    st = R.stats(_sums({t: [(w, 0.0) for w in (1, 2, 3)] for t in starters}), players=pr)
    g = R.grades(st)
    assert g["AAA"]["WR"]["rank"] == 1 and g["AAA"]["WR"]["basis"] == "players"


def test_a_pass_rusher_back_from_injury_counts_with_last_seasons_rush():
    import duckdb

    con = duckdb.connect()
    # the star missed this season (no 2026 rows) but had a big 2025; the other room is ordinary
    pfr = [("star", 2025, g, 50, 1.0, 0.5) for g in range(17)] + [
        (p, s, g, 50, 0.1, 0.0) for p in ("plain",) for s in (2025, 2026) for g in range(17)
    ]  # fmt: skip
    con.register(
        "players", pl.DataFrame({"gsis_id": ["g_star", "g_plain"], "pfr_id": ["star", "plain"]})
    )
    con.register("pfr_def", pl.DataFrame(
        [{"pfr_player_id": p, "season": s, "game_type": "REG", "pfr_game_id": f"{p}{s}{g}",
          "def_pressures": pr, "def_sacks": sk, "def_tackles_combined": 2, "def_missed_tackles": 0,
          "def_targets": 0, "def_completions_allowed": 0, "def_yards_allowed": 0} for p, s, g, _, pr, sk in pfr]
    ))  # fmt: skip
    con.register("snap_counts", pl.DataFrame(
        [{"pfr_player_id": p, "pfr_game_id": f"{p}{s}{g}", "defense_snaps": n} for p, s, g, n, _, _ in pfr]
    ))  # fmt: skip
    rooms = R.defense_rooms(con, 2026, {"LA": [{"gsis_id": "g_star", "grp": "EDGE"}],
                                         "XX": [{"gsis_id": "g_plain", "grp": "EDGE"}]})  # fmt: skip
    assert rooms["LA"]["EDGE"]["edge_pressure"] > rooms["XX"]["EDGE"]["edge_pressure"]
    assert rooms["LA"]["EDGE"]["plays"] == 850
