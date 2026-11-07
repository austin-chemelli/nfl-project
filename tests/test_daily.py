from nfl import daily


def test_plan_runs_the_snapshot_before_the_features_and_ends_with_the_site():
    steps = daily.plan()
    assert steps.index("odds snapshot") < steps.index("curate") < steps.index("features")
    assert steps[-1] == "site"
    assert "grade" not in steps and "ledger" not in steps  # the Tuesday refresh grades


def test_no_odds_skips_only_the_snapshot():
    assert daily.plan(odds=False) == [s for s in daily.plan() if s != "odds snapshot"]
