"""The retro contract (M9.2): the hand-written examples validate, and they're the same files the
web app's tests parse (so pydantic and zod agree on one shape)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nfl.retro.schema import Expectations, RetroGame, WeekRecap

FIX = Path(__file__).parent / "fixtures" / "retro"
WEB = Path(__file__).parents[1] / "web" / "src" / "test" / "fixtures" / "site"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def test_examples_validate():
    RetroGame.model_validate(_load("game_2026_08_CAR_GB.json"))
    WeekRecap.model_validate(_load("recap_2026_08.json"))
    Expectations.model_validate(_load("expectations.json"))


def test_web_fixtures_match():
    assert json.loads((WEB / "retro" / "2026_08_CAR_GB.json").read_text()) == _load("game_2026_08_CAR_GB.json")  # fmt: skip
    assert json.loads((WEB / "recap_2026_08.json").read_text()) == _load("recap_2026_08.json")


def test_example_is_consistent():
    r = RetroGame.model_validate(_load("game_2026_08_CAR_GB.json"))
    for t in r.teams.values():
        assert t.luck_net == pytest.approx(sum(x.swing_pts for x in t.luck), abs=0.06)
    best = [p for p in r.predictions if p.best]
    assert len(best) == 1 and best[0].model_id == r.best_model
    assert best[0].kind in ("approach", "ensemble")
    for a in r.attribution:
        vals = [g.value for g in a.groups]
        assert vals == sorted(vals, reverse=True)


def test_unknown_fields_rejected():
    rec = _load("game_2026_08_CAR_GB.json")
    rec["teams"]["home"]["luck"][0]["swing"] = 1.0
    with pytest.raises(ValidationError):
        RetroGame.model_validate(rec)


def test_recap_bold_calls_optional():
    rec = _load("recap_2026_08.json")
    assert WeekRecap.model_validate(rec).best_call is not None
    for k in ("best_call", "costliest_call"):
        del rec[k]
    r = WeekRecap.model_validate(rec)
    assert r.best_call is None and r.costliest_call is None
