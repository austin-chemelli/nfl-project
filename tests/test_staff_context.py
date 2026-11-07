import polars as pl

from nfl import staff_context as ctx


def unit(season, team, person, side="off", source="play_caller", changed=False):
    return {"season": season, "team": team, "side": side, "person": person, "source": source,
            "changed_midseason": changed}  # fmt: skip


def label(rows, qbs=None):
    out = ctx.unit_situations(pl.DataFrame(rows), qbs or {})
    return {(r["season"], r["team"]): r["situation"] for r in out.to_dicts()}


def test_same_caller_and_new_quarterback():
    rows = [unit(2030, "AAA", "Ann"), unit(2031, "AAA", "Ann"), unit(2032, "AAA", "Ann")]
    qbs = {(2030, "AAA"): "q1", (2031, "AAA"): "q1", (2032, "AAA"): "q2"}
    got = label(rows, qbs)
    assert got[(2031, "AAA")] == "same_caller"
    assert got[(2032, "AAA")] == "same_caller_new_qb"


def test_a_caller_with_a_past_elsewhere_has_moved():
    rows = [unit(2030, "AAA", "Ann"), unit(2030, "BBB", "Bob"), unit(2031, "BBB", "Ann")]
    assert label(rows)[(2031, "BBB")] == "moved_team"


def test_a_first_time_caller_is_never_moved():
    rows = [unit(2030, "AAA", "Ann"), unit(2031, "AAA", "Cal")]
    assert label(rows)[(2031, "AAA")] == "outside_first_time"


def test_coordinator_seasons_do_not_count_as_calling():
    rows = [unit(2030, "AAA", "Cal", source="coordinator"), unit(2030, "BBB", "Bob"),
            unit(2031, "BBB", "Cal")]  # fmt: skip
    assert label(rows)[(2031, "BBB")] == "outside_first_time"


def test_a_midseason_change_is_marked_unsettled():
    rows = [unit(2030, "AAA", "Ann", changed=True), unit(2031, "AAA", "Ann")]
    out = ctx.unit_situations(pl.DataFrame(rows), {})
    assert out["unsettled"].to_list() == [True]


def test_prior_reads_only_earlier_seasons_and_weights_recent_ones():
    assign = pl.DataFrame([unit(2030, "AAA", "Ann"), unit(2031, "AAA", "Ann"),
                           unit(2032, "AAA", "Ann")])  # fmt: skip
    rates = pl.DataFrame({
        "season": [2030, 2031, 2032], "team": ["AAA"] * 3, "side": ["off"] * 3,
        "metric": ["m"] * 3, "n": [200] * 3, "rate": [0.1] * 3, "pct": [0.0, 1.0, 0.5],
    })  # fmt: skip
    p = ctx.caller_prior(assign, rates, decay=0.5).filter(pl.col("season") == 2032)
    assert p["prior"].item() == (1.0 * 1 + 0.0 * 0.5) / 1.5
    assert p["prior_seasons"].item() == 2


CELL = {"weight": 0.75, "miss": 18.0, "league_miss": 25.0, "cases": 50}


def test_expected_blends_with_the_measured_weight():
    e = ctx.expected(0.8, 0.4, CELL)
    assert e["pct"] == 0.7
    assert e["miss"] == 0.18
    assert e["strength"] == "fair"


def test_expected_without_a_past_of_his_own_is_the_team_and_weak():
    e = ctx.expected(None, 0.4, CELL)
    assert e["pct"] == 0.4
    assert e["weight_on_caller"] == 0.0
    assert e["strength"] == "weak"


def test_expected_is_weak_when_it_barely_beats_the_league_middle():
    assert ctx.expected(0.8, 0.4, {**CELL, "miss": 23.0})["strength"] == "weak"


def test_expected_with_nothing_is_nothing():
    assert ctx.expected(None, None, CELL) is None


def test_blend_falls_back_from_metric_to_situation():
    blend = {"live": {"off": {"moved_team": {"*": CELL, "m": {**CELL, "weight": 0.1}}}}}
    assert ctx.blend_cell(blend, "live", "off", "moved_team", "m")["weight"] == 0.1
    assert ctx.blend_cell(blend, "live", "off", "moved_team", "x")["weight"] == 0.75
    assert ctx.blend_cell(blend, "live", "off", "same_caller", "x") is None


def test_other_starter_weeks_are_measured_from_week_one():
    g = pl.DataFrame({
        "week": [1, 2, 3, 4], "home_team": ["AAA", "BBB", "AAA", "AAA"],
        "away_team": ["BBB", "AAA", "CCC", "CCC"], "home_score": [10, 20, 30, None],
        "home_qb_name": ["Starter", "X", "Backup", None], "away_qb_name": ["Y", "Starter", "Z", None],
    })  # fmt: skip
    assert ctx.other_starter_weeks(g, "AAA") == [{"week": 3, "qb": "Backup"}]


def spell(person, evidence="news", role="OFF_PC"):
    return {"person": person, "evidence": evidence, "source_url": "https://x", "role": role,
            "start_week": 1, "end_week": None, "note": "working note"}  # fmt: skip


def test_an_unconfirmed_caller_shows_as_the_coordinator():
    c = ctx._caller(spell("Head Coach", "inferred"), "The OC", "Head Coach", None)
    assert c["name"] == "The OC" and c["confirmed"] is False and c["is_head_coach"] is False
    assert c["source_url"] is None
    c = ctx._caller(spell("Head Coach"), "The OC", "Head Coach", None)
    assert c["name"] == "Head Coach" and c["confirmed"] is True and c["is_head_coach"] is True


def test_an_unconfirmed_caller_with_no_coordinator_prints_no_name():
    assert ctx._caller(spell("Guess", "inferred"), None, "HC", None) is None


def test_public_staff_drops_unconfirmed_callers_and_working_notes():
    rows = [spell("Guess", "wiki"), spell("Named"), spell("Titled", "wiki", role="OC")]
    out = ctx._public(rows)
    assert [r["name"] for r in out] == ["Named", "Titled"]
    assert all("note" not in r for r in out)


STAFF = pl.DataFrame(
    [{"season": 2030, "team": "AAA", "role": "HC", "person": "Hal"}],
    schema={"season": pl.Int64, "team": pl.Utf8, "role": pl.Utf8, "person": pl.Utf8},
)


def test_a_caller_already_on_the_staff_took_over_rather_than_moved():
    rows = [unit(2029, "BBB", "Hal"), unit(2030, "AAA", "Ann"), unit(2031, "AAA", "Hal")]
    out = ctx.unit_situations(pl.DataFrame(rows), {}, STAFF)
    got = {(r["season"], r["team"]): r["situation"] for r in out.to_dicts()}
    assert got[(2031, "AAA")] == "took_over"


def test_a_first_timer_from_the_staff_is_promoted():
    rows = [unit(2030, "AAA", "Ann"), unit(2031, "AAA", "Hal")]
    out = ctx.unit_situations(pl.DataFrame(rows), {}, STAFF)
    assert out.filter(pl.col("season") == 2031)["situation"].item() == "promoted_first_time"
