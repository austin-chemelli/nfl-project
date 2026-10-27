"""Approach config loading and validation."""

import pytest
import yaml

from nfl.approaches import schema


def test_all_configs_load_and_ids_match_files():
    approaches = schema.load_all()
    assert {"traditionalist", "analyst", "sharp", "student"} <= set(approaches)
    for a in approaches.values():
        assert a.features
        assert a.emphasis or a.id == "student"


def test_emphasis_families_get_the_most_weight():
    for a in schema.load_all().values():
        if not a.emphasis:
            continue
        fw = a.family_weight()
        top = sorted(fw, key=fw.get, reverse=True)[: len(a.emphasis)]
        assert set(a.emphasis) == set(top), (a.id, fw)


def test_unknown_feature_fails_loudly():
    a = schema.load_all()["analyst"]
    with pytest.raises(ValueError, match="not in the store"):
        schema.check_features(a, known={"strength.epa_off"})


def test_bad_names_and_families_rejected(tmp_path):
    base = yaml.safe_load((schema.CONFIG_DIR / "analyst.yaml").read_text())
    bad = dict(base, weights={"epa_off": {"w": 1.0, "why": "no family"}})
    with pytest.raises(ValueError):
        schema.Approach.model_validate(bad)
    bad = dict(base, emphasis=["vibes"])
    with pytest.raises(ValueError):
        schema.Approach.model_validate(bad)
    p = tmp_path / "wrong_name.yaml"
    p.write_text(yaml.safe_dump(base))
    with pytest.raises(ValueError, match="must match"):
        schema.load_approach(p)
