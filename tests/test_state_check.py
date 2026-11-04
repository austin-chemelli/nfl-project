"""scripts/state_check.py: the parsers behind the hub checks (docs/state-maintenance.md)."""

import datetime as dt
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "state_check", Path(__file__).resolve().parents[1] / "scripts" / "state_check.py"
)
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

TF = """
  schedules = {
    weekly-refresh = { "tue-10" = "0 10 * * 2" }
    narrative-check = { "thu-0830" = "30 8 * * 4", "sat-1130" = "30 11 * * 6" }
    odds-snapshot = {
      "thu-2005" = "5 20 * * 4"
      "sun-0920" = "20 9 * * 0"
    }
  }
  schedule_pairs = merge([
"""

HUB = """
### Schedule (ET)

| When | What | Where | Cron | Writes | Check |
|---|---|---|---|---|---|
| Tue 10:00 | `nfl-weekly-refresh`: everything | cloud | `0 10 * * 2` | marts | list |
| Wed 18:00 | desktop pass | desktop | `wed 18:00` | records | log |
| Thu 08:30 | `nfl-narrative-check` | cloud | `30 8 * * 4` | nothing | list |
| Sat 11:30 | `nfl-narrative-check` | cloud | `30 11 * * 6` | nothing | list |
| Thu 20:05 | `nfl-odds-snapshot` | cloud | `5 20 * * 4` | lines | list |
| Sun 09:20 | `nfl-odds-snapshot` | cloud | `20 9 * * 0` | lines | list |
| On demand | `nfl-site` | cloud | none | site | list |

## Workstreams

| Track | Branch | Worktree | Goal | Status (date) | PR |
|---|---|---|---|---|---|
| ui | `ui-next` | `~/dev/nfl-project-ui` | next round | idle (2026-11-04) | |
| old | `a`, `b` | x | y | merged (2026-11-01) | #1 |

## Milestones
"""


def test_cloud_schedule_parses_one_line_and_multi_line_blocks():
    assert sc.expected_cloud_schedule(TF) == {
        ("weekly-refresh", "0 10 * * 2"),
        ("narrative-check", "30 8 * * 4"),
        ("narrative-check", "30 11 * * 6"),
        ("odds-snapshot", "5 20 * * 4"),
        ("odds-snapshot", "20 9 * * 0"),
    }


def test_desktop_schedule_from_passes():
    py = "PASSES = ((2, time(18, 0)), (5, time(7, 0)))\n"
    assert sc.expected_desktop_schedule(py) == {("wed", "18:00"), ("sat", "07:00")}


def test_hub_schedule_matches_the_sources():
    cloud, desktop = sc.hub_schedule(HUB)
    assert cloud == sc.expected_cloud_schedule(TF)
    assert desktop == {("wed", "18:00")}


def test_workstream_rows_collect_every_branch():
    rows = sc.workstream_rows(HUB)
    assert [r["track"] for r in rows] == ["ui", "old"]
    assert rows[1]["branches"] == ["a", "b"] and rows[1]["pr"] == "#1"


def test_bottom_line_age():
    today = dt.date(2026, 11, 10)
    assert sc.check_bottom_line("## Bottom line (as of 2026-11-04)\n", today) == []
    assert sc.check_bottom_line("## Bottom line (as of 2026-10-20)\n", today)[0][0] == "WARN"
    assert sc.check_bottom_line("## Bottom line\n", today)[0][0] == "ERROR"


def test_links_resolve_in_the_real_hub():
    assert sc.check_links(sc.STATE.read_text()) == []
