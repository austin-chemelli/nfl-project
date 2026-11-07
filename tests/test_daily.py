from nfl import daily


def test_plan_runs_the_snapshot_before_the_features_and_ends_with_the_site():
    steps = daily.plan()
    assert steps.index("odds snapshot") < steps.index("curate") < steps.index("features")
    assert steps[-1] == "site"
    assert "grade" not in steps and "ledger" not in steps  # the Tuesday refresh grades


def test_no_odds_skips_only_the_snapshot():
    assert daily.plan(odds=False) == [s for s in daily.plan() if s != "odds snapshot"]


def test_the_forecast_runs_after_curate_and_before_the_features():
    steps = daily.plan()
    assert steps.index("curate") < steps.index("forecast") < steps.index("features")


def test_an_optional_step_failing_never_stops_the_site(monkeypatch):
    from rich.console import Console

    ran = []

    def boom(*a):
        raise RuntimeError("config hash mismatch")

    steps = [
        daily.Step("forecast", boom, optional=True),
        daily.Step("site", lambda *a: ran.append("site")),
    ]
    monkeypatch.setattr(daily, "STEPS", steps)
    daily.run(None, Console(quiet=True), season=2026)
    assert ran == ["site"]
    assert {s.name for s in daily.STEPS if s.optional} <= {"forecast"}


def test_only_context_steps_are_optional():
    assert {s.name for s in daily.STEPS if s.optional} == {"forecast", "previews"}
