"""M9.5: week recap from planted game retros."""

import json
from pathlib import Path

import pytest

from nfl.config import Paths
from nfl.retro.game import pure_luck, retro_path
from nfl.retro.schema import RetroGame, WeekRecap
from nfl.retro.week import build_recap, recap_path, write_recap

FIX = Path(__file__).parent / "fixtures" / "retro" / "game_2026_08_CAR_GB.json"
SKILL = {"interceptions", "third_down", "fourth_down", "penalties"}


def planted(gid, margin=-3, student_ll=1.0, luck=None, week=8):
    d = json.loads(FIX.read_text())
    d["game_id"], d["week"] = gid, week
    d["result"] = {"home_score": 20, "away_score": 20 - margin, "margin": margin}
    for t in d["teams"].values():
        for f in t["luck"]:
            f["partly_skill"] = f["factor"] in SKILL
    for p in d["predictions"]:
        if p["model_id"] == "student":
            p["log_loss"] = student_ll
    for side, vals in (luck or {}).items():
        for f in d["teams"][side]["luck"]:
            f["swing_pts"] = vals.get(f["factor"], 0.0)
    return d


def write(paths, *games):
    for d in games:
        p = retro_path(paths, 2026, d["game_id"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(RetroGame.model_validate(d).model_dump(mode="json")))


def test_models_ordering_and_best(tmp_path):
    paths = Paths(tmp_path)
    a = planted("g_a", student_ll=0.1)
    b = planted("g_b", margin=4, student_ll=0.2)
    write(paths, a, b)
    rec = build_recap(paths, 2026, 8)
    WeekRecap.model_validate(rec.model_dump(mode="json"))
    assert rec.games == ["g_a", "g_b"]
    ranked = [m for m in rec.models if m.rank > 0]
    assert ranked[0].model_id == "student" == rec.best_model
    assert [m.rank for m in ranked] == list(range(1, len(ranked) + 1))
    assert [m.log_loss for m in ranked] == sorted(m.log_loss for m in ranked)
    refs = [m for m in rec.models if m.rank == 0]
    assert {m.kind for m in refs} <= {"reference", "global"} and refs
    mk = next(m for m in rec.models if m.model_id == "market_baseline")
    assert mk.vs_market == 0.0 and mk.n == 2
    ens = next(m for m in rec.models if m.model_id == "student")
    assert ens.vs_market == pytest.approx(0.15 - 1.0169, abs=1e-3)
    assert "2 games" in rec.note


def test_upsets_and_misread(tmp_path):
    paths = Paths(tmp_path)
    write(
        paths,
        planted("up", margin=-3, student_ll=1.5),  # market had the home team 64%: away won
        planted("fav", margin=4, student_ll=0.3),  # the favorite won: not an upset
        planted("tie", margin=0, student_ll=0.9),
    )
    rec = build_recap(paths, 2026, 8)
    assert [u.game_id for u in rec.upsets] == ["up"]
    assert rec.upsets[0].value == pytest.approx(0.362, abs=1e-3)
    assert "36%" in rec.upsets[0].sentence
    assert [m.game_id for m in rec.misread] == ["up", "tie", "fav"]
    assert "ended 20-20" in rec.misread[1].sentence


def test_pure_luck_ranking(tmp_path):
    paths = Paths(tmp_path)
    # home: huge partly-skill swing, small pure luck; away: the reverse sign and size
    big = planted("g1", luck={"home": {"third_down": 20.0, "fumbles": 1.0},
                              "away": {"fumbles": -5.0, "kicking": -2.0}})  # fmt: skip
    small = planted("g2", luck={"home": {"fumbles": 3.0}, "away": {"interceptions": -15.0}})
    write(paths, big, small)
    rec = build_recap(paths, 2026, 8)
    assert [(t.game_id, t.luck_net) for t in rec.luckiest] == [("g2", 3.0), ("g1", 1.0)]
    assert [(t.game_id, t.luck_net) for t in rec.unluckiest] == [("g1", -7.0)]
    assert (
        "fumble" in rec.unluckiest[0].sentence.lower()
        or "kick" in rec.unluckiest[0].sentence.lower()
    )
    t = RetroGame.model_validate(big).teams["home"]
    assert pure_luck(t) == 1.0


def test_write_recap(tmp_path):
    paths = Paths(tmp_path)
    assert write_recap(paths, 2026, 8) is None
    write(paths, planted("g1"), planted("g9", week=9))
    rec = write_recap(paths, 2026, 8)
    assert rec.games == ["g1"]
    assert recap_path(paths, 2026, 8).exists()
    WeekRecap.model_validate_json(recap_path(paths, 2026, 8).read_text())


def test_ranked_models_compared_on_shared_games(tmp_path):
    paths = Paths(tmp_path)
    a = planted("g_a", student_ll=0.1)
    b = planted("g_b", margin=4, student_ll=5.0)
    b["predictions"] = [p for p in b["predictions"] if p["model_id"] != "sharp"]
    write(paths, a, b)
    rec = build_recap(paths, 2026, 8)
    by = {m.model_id: m for m in rec.models}
    assert by["sharp"].n == 1 and by["student"].n == 2  # n and right stay on their own games
    assert by["student"].log_loss == pytest.approx(0.1)  # but the mean is over g_a, the shared one
    assert by["sharp"].log_loss == pytest.approx(
        next(p["log_loss"] for p in a["predictions"] if p["model_id"] == "sharp"), abs=1e-3
    )


def calls(d, **by_model):
    """Set each model's pick outcome and log loss: model_id=(right, log_loss)."""
    for p in d["predictions"]:
        if p["model_id"] in by_model:
            p["right"], p["log_loss"] = by_model[p["model_id"]]
    return d


def test_bold_calls_right_and_wrong(tmp_path):
    paths = Paths(tmp_path)
    a = calls(planted("g_a"), sharp=(True, 0.1), analyst=(True, 0.3), student=(False, 1.4),
              traditionalist=(False, 0.9))  # fmt: skip
    write(paths, a)
    rec = build_recap(paths, 2026, 8)
    WeekRecap.model_validate(rec.model_dump(mode="json"))
    b, c = rec.best_call, rec.costliest_call
    assert (b.model_id, b.game_id, b.log_loss, b.earned) == ("sharp", "g_a", 0.1, 0.593)
    assert b.sentence.startswith("The Sharp gave ") and "and they won: 0.59 better" in b.sentence
    assert (c.model_id, c.log_loss, c.earned) == ("student", 1.4, -0.707)
    assert c.sentence.endswith("and they lost: 0.71 worse than a coin flip.")
    assert f"{round(100 * c.p_pick)}%" in c.sentence and (c.away, c.home) == ("CAR", "GB")


def test_bold_calls_none_when_all_one_side(tmp_path):
    paths = Paths(tmp_path)
    allwrong = {m: (False, 1.0) for m in ("traditionalist", "sharp", "analyst", "student")}
    write(paths, calls(planted("g_a"), **allwrong))
    rec = build_recap(paths, 2026, 8)
    assert rec.best_call is None and rec.costliest_call is not None
    allright = {m: (True, 0.4) for m in allwrong}
    write(paths, calls(planted("g_a"), **allright))
    rec = build_recap(paths, 2026, 8)
    assert rec.costliest_call is None and rec.best_call is not None


def test_bold_calls_ignore_ties_and_references(tmp_path):
    paths = Paths(tmp_path)
    d = calls(planted("g_a"), sharp=(True, 0.5), analyst=(False, 0.8), student=(None, 0.01),
              traditionalist=(None, 3.0), market_baseline=(True, 0.001), elo_v0=(False, 9.0))  # fmt: skip
    for p in d["predictions"]:
        if p["model_id"] == "global":
            p["right"], p["log_loss"] = False, 9.0
    write(paths, d)
    rec = build_recap(paths, 2026, 8)
    assert rec.best_call.model_id == "sharp"
    assert rec.costliest_call.model_id == "analyst"


def test_bold_calls_tie_breaks(tmp_path):
    paths = Paths(tmp_path)
    same = {m: (True, 0.2) for m in ("traditionalist", "sharp", "analyst", "student")}
    sameb = {m: (False, 1.1) for m in same}
    a = calls(planted("g_b"), **same)
    b = calls(planted("g_a"), **same)
    write(paths, a, b)
    rec = build_recap(paths, 2026, 8)
    assert (rec.best_call.game_id, rec.best_call.model_id) == ("g_a", "analyst")  # game, then model
    write(paths, calls(planted("g_b"), **sameb), calls(planted("g_a"), **sameb))
    rec = build_recap(paths, 2026, 8)
    assert (rec.costliest_call.game_id, rec.costliest_call.model_id) == ("g_a", "analyst")
