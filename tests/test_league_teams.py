"""teams.json builder: next-game values, record cut, ranks, exclusions (ADR 0019, M14.2)."""

import json
from datetime import datetime, timedelta

import polars as pl

from nfl.features.groups import GROUPS, validate_registry
from nfl.league.divisions import DIVISIONS
from nfl.league.teams import team_latest, teams_file

CODES = sorted(DIVISIONS)  # 32
NOW = datetime(2026, 10, 20)
BUILD = datetime(2026, 10, 19)  # known_as_of of the future rows
K = {1: datetime(2026, 9, 10), 2: datetime(2026, 9, 17), 3: datetime(2026, 10, 25), 4: datetime(2026, 11, 1)}  # fmt: skip


def _pairs(codes):
    return [(codes[i], codes[i + 1]) for i in range(0, len(codes), 2)]


def make(
    codes=CODES, weeks=(1, 2, 3, 4), played=(1, 2), features=("strength.epa_off",), value=None
):
    """Weeks 1-2 played, 3-4 future. value(feature, week, team) -> float."""
    value = value or (lambda f, w, t: float(codes.index(t)) + (100 * w if w >= 3 else 0.0))
    games, feats = [], []
    for w in weeks:
        for i, (h, a) in enumerate(_pairs(codes if w % 2 else codes[::-1])):
            gid = f"2026_{w:02d}_{a}_{h}"
            res = (h, a) if w in played else (None, None)
            games.append({"game_id": gid, "season": 2026, "week": w, "kickoff_utc": K[w],
                          "home_team": h, "away_team": a,
                          "home_score": 24 if res[0] else None, "away_score": 17 if res[1] else None})  # fmt: skip
            known = K[w] - timedelta(hours=2) if w in played else BUILD
            for side, t in (("home", h), ("away", a)):
                for f in features:
                    feats.append({"game_id": gid, "feature": f, "side": side,
                                  "value": value(f, w, t), "known_as_of": known})  # fmt: skip
    return pl.DataFrame(feats), pl.DataFrame(games)


def test_next_game_value_not_last_kickoff():
    feats, games = make()
    lat = team_latest(feats, games, NOW).filter(pl.col("team") == "KC")
    assert lat["value"].to_list() == [CODES.index("KC") + 300.0]  # week 3, not week 4
    assert lat["game_id"][0].startswith("2026_03")


def test_rows_not_known_yet_are_ignored():
    feats, games = make()
    lat = team_latest(feats, games, datetime(2026, 10, 18))  # before the future rows were stamped
    assert lat.filter(pl.col("team") == "KC")["value"].to_list() == [CODES.index("KC")]  # week 2


def test_no_future_game_falls_back_to_last_row():
    feats, games = make(weeks=(1, 2), played=(1, 2))
    lat = team_latest(feats, games, NOW).filter(pl.col("team") == "KC")
    assert lat["value"].to_list() == [float(CODES.index("KC"))]
    assert lat["game_id"][0].startswith("2026_02")


def test_non_finite_values_dropped():
    feats, games = make(value=lambda f, w, t: float("nan") if w >= 3 else 1.0)
    lat = team_latest(feats, games, NOW)
    assert lat["value"].to_list() == [1.0] * 32  # falls back to week 2


def test_shape_json_and_ranks():
    feats, games = make(features=("strength.epa_off", "strength.epa_def", "strength.luck"))
    obj = teams_file(feats, games, NOW, 3)
    json.dumps(obj, allow_nan=False)
    assert obj["season"] == 2026 and obj["week"] == 3 and obj["as_of"] == "2026-10-19T00:00:00Z"
    assert len(obj["teams"]) == 32
    for f in obj["features"]:
        assert all(f[k] not in (None, "") for k in ("label", "short", "unit", "group"))
        assert (
            "better" in f and f["n"] == 32 and f["lo"] <= f["q1"] <= f["med"] <= f["q3"] <= f["hi"]
        )
    for t in obj["teams"].values():
        assert t["conference"] in ("AFC", "NFC") and t["division"].startswith(t["conference"])
    by = {f["id"]: f for f in obj["features"]}
    assert [f["id"] for f in obj["features"]] == ["strength.luck", "strength.epa_off", "strength.epa_def"]  # registry order  # fmt: skip
    assert by["strength.epa_off"]["better"] == "higher"
    assert by["strength.epa_def"]["better"] == "lower"
    assert by["strength.luck"]["better"] is None
    teams = obj["teams"]
    order = sorted(teams, key=lambda c: teams[c]["values"]["strength.epa_off"])
    pcts = [teams[c]["pct"]["strength.epa_off"] for c in order]
    assert pcts == sorted(pcts) and pcts[0] == 0 and pcts[-1] == 100
    assert teams[order[-1]]["rank"]["strength.epa_off"] == 1  # higher is better
    assert teams[order[0]]["rank"]["strength.epa_def"] == 1  # lower is better
    assert teams[order[-1]]["rank"]["strength.luck"] == 1  # neutral: highest value is 1


def test_ties_share_rank_and_average_pct():
    feats, games = make(value=lambda f, w, t: 1.0 if CODES.index(t) < 4 else 2.0)
    obj = teams_file(feats, games, NOW, 3)
    low, high = obj["teams"][CODES[0]], obj["teams"][CODES[-1]]
    assert low["rank"]["strength.epa_off"] == 29 and high["rank"]["strength.epa_off"] == 1
    assert low["pct"]["strength.epa_off"] == round(100 * 1.5 / 31, 1)


def test_record_counts_only_games_before_as_of():
    feats, games = make()
    # a week-2 result that kicked off after as_of (the build) is left out of the record
    late = games.with_columns(
        pl.when(pl.col("week") == 2)
        .then(datetime(2026, 10, 19, 12))
        .otherwise(pl.col("kickoff_utc"))
        .alias("kickoff_utc")
    )
    obj = teams_file(feats, late, datetime(2026, 10, 19, 18), 3)
    kc = obj["teams"]["KC"]
    assert kc["games_played"] == 1 and kc["wins"] + kc["losses"] + kc["ties"] == 1
    assert [g["pf"] is None for g in kc["games"]] == [False, True, True, True]
    full = teams_file(feats, games, NOW, 3)["teams"]["KC"]
    assert full["games_played"] == 2 and full["points_for"] + full["points_against"] == 2 * 41
    assert full["last_game_id"].startswith("2026_02") and full["next_game_id"].startswith("2026_03")
    assert len(full["games"]) == 4 and full["games"][2]["pf"] is None


def _without_team(feats, games, team):
    j = feats.join(games.select("game_id", "home_team", "away_team"), on="game_id")
    mine = (
        pl.when(pl.col("side") == "home").then(pl.col("home_team")).otherwise(pl.col("away_team"))
    )
    return j.filter(mine != team).select(feats.columns)


def test_flags_and_per_game_groups_dropped():
    feats, games = make(features=("strength.epa_off", "environment.is_dome", "availability.starters_out", "narrative.hype", "environment.rest_days", "form.eliminated"))  # fmt: skip
    obj = teams_file(feats, games, NOW, 3)
    assert [f["id"] for f in obj["features"]] == ["strength.epa_off"]


def test_feature_needs_twenty_teams():
    feats, games = make(codes=CODES[:20])
    assert [f["id"] for f in teams_file(feats, games, NOW, 3)["features"]] == ["strength.epa_off"]
    thin = _without_team(feats, games, CODES[0])  # 19 teams
    assert (
        teams_file(thin, games, NOW, 3) is None
    )  # nothing to publish: the page shows its empty card


def test_context_only_group_has_no_direction():
    feats, games = make(features=("decisions.pass_rate_oe", "front.blitz_rate"))
    by = {f["id"]: f for f in teams_file(feats, games, NOW, 3)["features"]}
    assert (
        by["decisions.pass_rate_oe"]["better"] is None and by["front.blitz_rate"]["better"] is None
    )


def test_registry_shorts():
    validate_registry()
    published = {
        "strength.epa_off": "Offense EPA", "decisions.pass_rate_oe": "Pass rate vs expected",
        "strength.elo_pre": "Elo rating", "front.blitz_rate": "Blitz rate", "form.epa_trend": "EPA trend",
    }  # fmt: skip
    members = {m.feature: m for g in GROUPS.values() for m in g.members}
    for f, short in published.items():
        assert members[f].short == short
    assert all(len(m.short) <= 22 for m in members.values())


def test_bands_are_p10_to_p90_as_on_the_game_page():
    feats, games = make()
    f = teams_file(feats, games, NOW, 3)["features"][0]
    vals = [CODES.index(c) + 300.0 for c in CODES]
    import numpy as np

    assert f["lo"] == round(float(np.percentile(vals, 10)), 4)
    assert f["hi"] == round(float(np.percentile(vals, 90)), 4)


def test_as_of_ignores_rows_that_arent_published():
    """A narrative row stamped after the feature build must not pull the record's cut past the values."""
    feats, games = make()
    late = BUILD + timedelta(hours=6)
    extra = feats.head(1).with_columns(
        pl.lit("narrative.sentiment").alias("feature"), pl.lit(late).alias("known_as_of")
    )
    out = teams_file(pl.concat([feats, extra]), games, NOW, 3)
    assert out["as_of"] == BUILD.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_record_is_the_regular_season():
    feats, games = make()
    games = games.with_columns(
        pl.when(pl.col("week") == 2).then(pl.lit("WC")).otherwise(pl.lit("REG")).alias("game_type")
    )
    t = teams_file(feats, games, NOW, 3)["teams"]["KC"]
    assert t["games_played"] == 1  # week 1 counts, the playoff game doesn't
    assert sum(g["pf"] is not None for g in t["games"]) == 2  # but it stays in the list
