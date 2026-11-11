"""`nfl status --json` (hub Contract B): recorded gcloud output mapped to items, no network."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from nfl import status

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "status"
NOW = datetime(2026, 11, 11, 17, 30, tzinfo=UTC)
P, R = "nfl-project-prod", "us-central1"
STATES = {"ok", "failed", "running"}


def load(name: str):
    return json.loads((FIX / name).read_text())


def check_contract(items: list[dict]) -> None:
    """The field rules of Contract B."""
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids))
    for it in items:
        assert it["id"] and it["label"]
        assert set(it) <= {
            "id",
            "label",
            "group",
            "schedule",
            "tz",
            "last",
            "links",
            "value",
            "limit",
            "unit",
        }
        if "last" in it:
            assert it["last"]["state"] in STATES
            datetime.fromisoformat(it["last"]["at"])
        if "schedule" in it:
            crons = it["schedule"] if isinstance(it["schedule"], list) else [it["schedule"]]
            assert all(len(c.split()) == 5 for c in crons) and it["tz"] == "America/New_York"
        for link in it.get("links", []):
            assert link["label"] and link["url"].startswith("https://")


def test_jobs_tf_is_the_job_list():
    jobs = status.parse_jobs_tf((ROOT / "infra" / "jobs.tf").read_text())
    assert set(jobs) == {
        "weekly-refresh", "lock-thu", "lock-sat", "odds-snapshot", "daily", "retro", "site", "narrative-check",
    }  # fmt: skip
    assert jobs["site"] == []
    assert jobs["narrative-check"] == ["30 8 * * 4", "30 11 * * 6"]
    assert len(jobs["odds-snapshot"]) == 6


def test_several_crons_become_a_list_one_stays_a_string():
    many = status.cloud_item("daily", ["5 20 * * 3", "5 20 * * 5"], [], None, NOW, P, R)
    one = status.cloud_item("retro", ["0 7 * * *"], [], None, NOW, P, R)
    none = status.cloud_item("site", [], [], None, NOW, P, R)
    assert many["schedule"] == ["5 20 * * 3", "5 20 * * 5"] and many["tz"] == "America/New_York"
    assert one["schedule"] == "0 7 * * *"
    assert "schedule" not in none and "tz" not in none
    assert "last" not in many  # never ran: the hub decides whether that is "missed"
    check_contract([many, one, none])


def test_failed_execution_is_the_latest():
    item = status.cloud_item(
        "narrative-check",
        ["30 8 * * 4", "30 11 * * 6"],
        load("executions_nfl-narrative-check.json"),
        None,
        NOW,
        P,
        R,
    )
    last = item["last"]
    assert last["state"] == "failed"
    assert last["detail"] == "exit code 1 after 1m 46s"
    assert last["at"] == "2026-11-07T11:30:01-05:00"
    assert "nfl-narrative-check-z66h9" in last["url"]
    assert [lk["label"] for lk in item["links"]] == ["Executions", "Logs", "Last run's logs"]
    check_contract([item])


def test_ok_execution_and_order_independence():
    execs = load("executions_nfl-odds-snapshot.json")
    item = status.cloud_item(
        "odds-snapshot", ["5 20 * * 1"], list(reversed(execs)), None, NOW, P, R
    )
    assert item["last"]["state"] == "ok"
    assert item["last"]["at"] == "2026-11-09T20:05:08-05:00"
    assert item["last"]["detail"].startswith("took 5m")


def test_running_and_cancelled_executions():
    base = {"metadata": {"name": "nfl-site-x", "creationTimestamp": "2026-11-11T17:20:00.123456Z"}}
    running = status.execution_last(
        {**base, "status": {"startTime": "2026-11-11T17:21:00Z"}}, NOW, P, R
    )
    assert running["state"] == "running" and running["detail"] == "running for 9m 00s"
    cancelled = status.execution_last(
        {**base, "status": {"startTime": "2026-11-11T17:21:00Z", "completionTime": "2026-11-11T17:22:00Z", "cancelledCount": 1}},
        NOW, P, R,
    )  # fmt: skip
    assert cancelled["state"] == "failed" and cancelled["detail"] == "cancelled after 1m 00s"


def test_desktop_passes_from_the_log():
    wed, sat = status.desktop_items(load("desktop_log.json"), NOW, P)
    assert (wed["id"], wed["schedule"]) == ("desktop-narrative-wed", "0 18 * * 3")
    assert (sat["id"], sat["schedule"]) == ("desktop-narrative-sat", "0 7 * * 6")
    # Wed 11-04: a failed git pull, a failed run, then a rerun that finished: the last run counts
    assert wed["last"]["state"] == "ok"
    assert wed["last"]["at"] == "2026-11-04T22:26:41-05:00"
    assert wed["last"]["detail"] == "2026 week 9, took 3h 05m"
    # Sat 11-07: started twice, the second run finished
    assert sat["last"]["state"] == "ok" and sat["last"]["detail"] == "2026 week 9, took 3h 28m"
    check_contract([wed, sat])


def test_desktop_failed_running_and_died():
    def entry(ts, sev, text):
        return {"timestamp": ts, "severity": sev, "textPayload": text}

    failed = [
        entry("2026-11-11T23:00:00Z", "INFO", "desktop narrative pass started: 2026 week 10"),
        entry(
            "2026-11-12T01:00:00Z",
            "ERROR",
            "desktop narrative pass failed: upload marts/x (log: ...)",
        ),
    ]
    later = datetime(2026, 11, 12, 2, tzinfo=UTC)
    wed = status.desktop_items(failed, later, P)[0]["last"]
    assert wed["state"] == "failed" and wed["detail"].startswith("upload marts/x")
    running = status.desktop_items(failed[:1], later, P)[0]["last"]
    assert running["state"] == "running" and running["detail"] == "2026 week 10, running for 3h 00m"
    died = status.desktop_items(failed[:1], datetime(2026, 11, 12, 12, tzinfo=UTC), P)[0]["last"]
    assert died["state"] == "failed" and "no finish" in died["detail"]
    no_start = status.desktop_items(
        [entry("2026-11-11T23:00:00Z", "ERROR", "desktop narrative pass failed: git fetch")],
        later,
        P,
    )
    assert no_start[0]["last"]["state"] == "failed"
    assert "last" not in status.desktop_items([], later, P)[1]


def test_site_freshness_threshold():
    fresh = status.site_item(
        {"generated_at": "2026-11-11T12:03:00Z", "current_week": 10}, None, NOW
    )
    assert fresh["last"]["state"] == "ok" and fresh["last"]["detail"] == "week 10, 5h 27m old"
    stale = status.site_item({"generated_at": "2026-11-10T12:03:00Z"}, None, NOW)
    assert stale["last"]["state"] == "failed" and "stale after 26h" in stale["last"]["detail"]
    broken = status.site_item(None, "URLError: timed out", NOW)
    assert broken["last"]["state"] == "failed"


def test_odds_meter():
    item = status.odds_item(
        {
            "fetched_at": "2026-11-10T15:01:51.059484+00:00",
            "requests_used": 54,
            "requests_remaining": 446,
        }
    )
    assert (item["value"], item["limit"], item["unit"]) == (54, 500, "credits")
    assert (
        status.odds_item(
            {
                "fetched_at": "2026-11-10T15:01:51Z",
                "requests_used": None,
                "requests_remaining": None,
            }
        )
        is None
    )


def _fake(responses: dict[str, tuple[int, str, str]]):
    calls = []

    def run(args):
        calls.append(args)
        key = " ".join(args[:4]) if args[0] == "gcloud" else args[0]
        for prefix, resp in responses.items():
            if key.startswith(prefix) or " ".join(args).startswith(prefix):
                return resp
        return 0, "[]", ""

    return run, calls


LS = "gs://b/raw/odds_api/live/snapshot_ts=20261109T011119Z/\ngs://b/raw/odds_api/live/snapshot_ts=20261110T150151Z/\n"


def test_collect_end_to_end_with_recorded_output():
    narr = json.dumps(load("executions_nfl-narrative-check.json"))
    manifest = {
        "fetched_at": "2026-11-10T15:01:51Z",
        "requests_used": 54,
        "requests_remaining": 446,
    }
    commit = [{"commit": {"committer": {"date": "2026-11-07T17:07:00Z"}, "message": "lock: 2026 W09 sat\n\nx"},
               "html_url": "https://github.com/austin-chemelli/nfl-project/commit/abc"}]  # fmt: skip
    run, _ = _fake({
        "gcloud auth": (0, "token\n", ""),
        "gcloud run jobs executions list --job=nfl-narrative-check": (0, narr, ""),
        "gcloud run jobs executions list --job=nfl-retro": (1, "", "ERROR: (gcloud.run) permission denied\n"),
        "gcloud logging read": (0, json.dumps(load("desktop_log.json")), ""),
        "gcloud storage ls": (0, LS, ""),
        "gcloud storage cat": (0, json.dumps(manifest), ""),
        "gh": (0, json.dumps(commit), ""),
    })  # fmt: skip
    meta = json.dumps({"generated_at": "2026-11-11T12:03:00Z", "current_week": 10}).encode()
    items = status.collect(ROOT, now=NOW, run=run, fetch=lambda url: meta, have_gcloud=True)
    check_contract(items)
    by_id = {it["id"]: it for it in items}
    assert by_id["nfl-narrative-check"]["last"]["state"] == "failed"
    assert (
        by_id["nfl-retro"]["last"]["detail"]
        == "could not read executions: ERROR: (gcloud.run) permission denied"
    )
    assert "last" not in by_id["nfl-daily"]
    assert by_id["desktop-narrative-sat"]["last"]["state"] == "ok"
    assert by_id["site-data"]["last"]["state"] == "ok"
    assert by_id["lock-commit"]["last"]["detail"] == "lock: 2026 W09 sat"
    assert by_id["odds-api-credits"]["value"] == 54
    assert [it["group"] for it in items][:8] == ["Cloud jobs"] * 8
    json.dumps({"items": items})  # serializable
    assert "Cloud jobs" in status.render_text(items)


def test_collect_without_gcloud_reports_failed_groups_and_never_raises():
    run, calls = _fake({"gh": (1, "", "gh: not logged in\n")})
    items = status.collect(ROOT, now=NOW, run=run, fetch=lambda url: b"{}", have_gcloud=False)
    check_contract(items)
    by_group = {}
    for it in items:
        by_group.setdefault(it["group"], []).append(it)
    for group in ("Cloud jobs", "Desktop", "Usage"):
        (it,) = by_group[group]
        assert it["last"]["state"] == "failed" and "not installed" in it["last"]["detail"]
    assert not any(c[0] == "gcloud" for c in calls)
    assert {it["id"]: it["last"]["state"] for it in by_group["Site"]} == {
        "site-data": "failed",
        "lock-commit": "failed",
    }


def test_collect_gcloud_logged_out():
    run, _ = _fake(
        {
            "gcloud auth": (
                1,
                "",
                "ERROR: (gcloud.auth.print-access-token) Reauthentication required.\n",
            )
        }
    )
    items = status.collect(ROOT, now=NOW, run=run, fetch=lambda url: b"{}", have_gcloud=True)
    cloud = [it for it in items if it["group"] == "Cloud jobs"]
    assert len(cloud) == 1 and "not logged in" in cloud[0]["last"]["detail"]
    assert "Reauthentication required" in cloud[0]["last"]["detail"]
