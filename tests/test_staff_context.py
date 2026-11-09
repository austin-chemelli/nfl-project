import polars as pl

from nfl import staff_context as ctx

from .conftest import requires_data


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


def test_career_merges_seasons_and_keeps_only_confirmed_calling():
    s = pl.DataFrame(
        [
            {"season": 2020, "team": "AAA", "role": "OFF_PC", "person": "Ann", "evidence": "news"},
            {"season": 2021, "team": "AAA", "role": "OFF_PC", "person": "Ann", "evidence": "news"},
            {
                "season": 2022,
                "team": "AAA",
                "role": "OFF_PC",
                "person": "Ann",
                "evidence": "inferred",
            },
            {
                "season": 2023,
                "team": "BBB",
                "role": "OFF_PC",
                "person": "Ann",
                "evidence": "roundup",
            },
            {"season": 2024, "team": "BBB", "role": "DEF_PC", "person": "Ann", "evidence": "news"},
        ]
    )
    assert ctx.career(s, "Ann", "off") == [
        {"team": "AAA", "from": 2020, "to": 2021},
        {"team": "BBB", "from": 2023, "to": 2023},
    ]


def test_replaced_names_a_confirmed_caller_only():
    first = {**spell("Evero", "inferred", role="DEF_PC"), "start_week": 1}
    wash = {**spell("Wash", role="DEF_PC"), "start_week": 9}
    assert ctx.replaced([first, wash], wash) is None
    assert ctx.replaced([{**first, "evidence": "news"}, wash], wash) == "Evero"
    title = {**spell("Evero", "wiki", role="DC"), "start_week": 1}
    assert ctx.replaced([title, {**wash, "role": "DC"}], {**wash, "role": "DC"}) == "Evero"


def test_rank_is_one_for_the_most_and_ties_share():
    df = pl.DataFrame({
        "season": [2030] * 3, "team": ["A", "B", "C"], "side": ["off"] * 3, "metric": ["m"] * 3,
        "n": [200] * 3, "rate": [0.2, 0.5, 0.5], "pct": [0.1, 0.6, 0.6],
    })  # fmt: skip
    out = dict(zip(*ctx._ranked(df).select("team", "rank").to_dict().values(), strict=True))
    assert out == {"B": 1, "C": 1, "A": 3}


def spells_frame(*rows):
    cols = ("season", "team", "role", "person", "evidence")
    return pl.DataFrame([dict(zip(cols, r, strict=True)) for r in rows])


def test_a_same_caller_claim_needs_last_season_confirmed():
    rows = [unit(2030, "AAA", "Ann"), unit(2031, "AAA", "Ann")]
    weak = spells_frame(
        (2030, "AAA", "OFF_PC", "Ann", "inferred"), (2031, "AAA", "OFF_PC", "Ann", "news")
    )
    good = spells_frame(
        (2030, "AAA", "OFF_PC", "Ann", "news"), (2031, "AAA", "OFF_PC", "Ann", "news")
    )
    for spells, want in ((weak, None), (good, "same_caller")):
        sit = ctx.Situations(pl.DataFrame(rows), {}, spells)
        label = sit.label(2031, "AAA", "off", "Ann")
        assert label == "same_caller"  # the blend still knows
        assert sit.public(2031, "AAA", "off", "Ann", label) == want


def test_called_before_needs_a_confirmed_past():
    rows = [unit(2030, "AAA", "Bob"), unit(2030, "BBB", "Ann"), unit(2031, "AAA", "Ann")]
    weak = spells_frame(
        (2030, "BBB", "OFF_PC", "Ann", "inferred"), (2031, "AAA", "OFF_PC", "Ann", "news")
    )
    sit = ctx.Situations(pl.DataFrame(rows), {}, weak)
    assert sit.label(2031, "AAA", "off", "Ann") == "moved_team"
    assert sit.public(2031, "AAA", "off", "Ann", "moved_team") is None


def test_replaced_is_the_spell_right_before_and_never_the_same_person():
    a = {**spell("A"), "start_week": 1}
    b = {**spell("B", "inferred"), "start_week": 5}
    c = {**spell("C"), "start_week": 9}
    assert ctx.replaced([a, b, c], c) is None
    again = {**spell("A"), "start_week": 12}
    assert ctx.replaced([a, again], again) is None


def test_traits_need_every_season_on_one_side():
    row = {"metric": "m", "kind": "live", "prior": 0.9, "prior_min": 0.7, "prior_max": 0.99,
           "prior_seasons": 4, "prior_first": 2022, "prior_last": 2025}  # fmt: skip
    assert [t["metric"] for t in ctx.traits([row])] == ["m"]
    assert ctx.traits([{**row, "prior_min": 0.4}]) == []  # one season below the middle
    assert ctx.traits([{**row, "prior_seasons": 1}]) == []
    assert ctx.traits([{**row, "prior": 0.7}]) == []  # not far enough from the middle
    low = {**row, "metric": "low", "prior": 0.05, "prior_min": 0.01, "prior_max": 0.2}
    assert [t["metric"] for t in ctx.traits([row, low])] == ["low", "m"]
    mirror = {**row, "metric": "a", "prior": 0.1, "prior_min": 0.05, "prior_max": 0.3}
    for rows in ([row, mirror], [mirror, row]):  # equally far from the middle: by metric, any order
        assert [t["metric"] for t in ctx.traits(rows)] == ["a", "m"]


def test_lean_follows_the_study_and_drops_weak_cells():
    assert ctx.lean({"strength": "fair", "weight_on_caller": 0.8}) == "caller"
    assert ctx.lean({"strength": "fair", "weight_on_caller": 0.3}) == "team"
    assert ctx.lean({"strength": "fair", "weight_on_caller": 0.4}) == "both"  # about a tie
    assert ctx.lean({"strength": "fair", "weight_on_caller": 0.5}) == "both"
    assert ctx.lean({"strength": "weak", "weight_on_caller": 0.9}) is None
    assert ctx.lean(None) is None


def test_profiles_need_a_source_and_a_claim():
    """On the raw file: the loader drops a row without a source, so it can't catch one."""
    import csv
    from importlib import resources

    text = resources.files("nfl.data").joinpath("coach_profiles.csv").read_text()
    for r in csv.DictReader(text.splitlines()):
        urls = [u.strip() for u in r["sources"].split(" ; ") if u.strip()]
        assert urls and all(u.startswith("http") for u in urls), r["person"]
        assert r["tree"] or r["known_for"], r["person"]


def test_profiles_never_say_who_calls_plays():
    """That claim lives in the staff table, under its evidence rule (ADR 0021)."""
    import re

    calling = re.compile(
        r"play[- ]?call|\bcall(s|ed|ing)?\b[^.]{0,40}\b(plays?|offen[sc]e|defen[sc]e)\b",
        re.IGNORECASE,
    )
    for person, p in ctx.load_profiles().items():
        assert not calling.search(p["known_for"] or ""), person
        assert not calling.search(p["tree"] or ""), person


def test_profiles_carry_no_percentages():
    """Our data owns the numbers; a source's share is often measured another way."""
    for person, p in ctx.load_profiles().items():
        assert "%" not in (p["known_for"] or "") + (p["tree"] or ""), person


@requires_data
def test_the_page_draws_only_confirmed_calling_seasons():
    """Todd Wash's JAX 2016-2020 seasons are unconfirmed, so CAR's defense shows no past for him."""
    import polars as pl

    from nfl.config import get_paths
    from nfl.features import store

    paths = get_paths()
    games = store.games_frame(paths).filter(pl.col("season") == 2026)

    def label(m):
        return {"label": m, "help": "", "unit": "pct", "lo": "less", "hi": "more"}

    car = ctx.team_files(paths, 2026, 9, games, label)["CAR"]["units"]["def"]
    assert car["caller"]["name"] == "Todd Wash"
    assert all(m["caller_past"] is None for m in car["live"] + car["charted"])
    assert car["caller"]["traits"] == []
