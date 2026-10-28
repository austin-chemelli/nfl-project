"""Plain-language helpers behind the tracker page."""

from nfl.ui import tracker_helpers as h


def test_ll_vs_market_words():
    s = h.ll_vs_market(0.630, 0.610)
    assert "0.630" in s and "worse than the market" in s and "noise" in s
    assert "about the same" in h.ll_vs_market(0.612, 0.610)


def test_fold_and_verdict():
    rows = [
        {"mean_p": 0.25, "hit_rate": 0.35, "n": 300},  # a 75% call that won 65%
        {"mean_p": 0.75, "hit_rate": 0.65, "n": 300},
    ]
    f = h.fold_reliability(rows)
    assert len(f) == 1 and f[0]["n"] == 600 and abs(f[0]["hit_rate"] - 0.65) < 1e-9
    assert "overconfident" in h.calibration_verdict(rows, "X")
    ok = [{"mean_p": 0.7, "hit_rate": 0.7, "n": 500}]
    assert "well calibrated" in h.calibration_verdict(ok, "X")


def test_divergence_sentence():
    r = {"bucket": "10+", "n": 1158, "lean_win_rate": 0.40, "market_expected_rate": 0.42}
    s = h.divergence_sentence(r, "the Traditionalist")
    assert "1,158 games" in s and "10+ points" in s and "won 40%" in s and "expected 42%" in s


def test_headline_and_scale():
    a = {"name": "The Traditionalist", "history_shifted_points": 8.7,
         "persona_share": {"form": 15, "q": 5}, "history_share": {"form": 6, "q": 5}}  # fmt: skip
    s = h.persona_history_headline(a, {"form": "Form"})
    assert "9 of the Traditionalist's 100" in s and "Form, 15 vs 6" in s
    assert "14% more confident" in h.calibration_scale_sentence(0.88)
