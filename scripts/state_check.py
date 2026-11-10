#!/usr/bin/env python3
"""Mechanical checks on docs/state.md, the project hub (docs/state-maintenance.md).

Runs at every session start (scripts/hooks/session-start.sh), before `gh pr create` / `git push`
(scripts/hooks/pr-guard.sh) and in CI. Prints one line per finding:

  ERROR  something inside the hub is wrong (a broken link, the schedule table disagrees with
         infra/jobs.tf, the docs map's verified date differs from the doc's own status line).
         Deterministic; the chat fixes it.
  WARN   the environment disagrees with the hub (a worktree or an open PR without a workstream
         row, a doc changed after its verified date, a stale bottom line). Informational.

`--strict` exits 1 when there is at least one ERROR. Needs only the standard library and git;
`gh` is optional (the PR check is skipped without it).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs" / "state.md"
JOBS_TF = ROOT / "infra" / "jobs.tf"
NARRATIVE_PY = ROOT / "src" / "nfl" / "llm" / "narrative.py"
TRACKS = ROOT / ".notes" / "hub" / "tracks"  # the live layer (~/dev/hub); replaced .notes/board.md
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
BOTTOM_LINE_MAX_AGE = 7
VERIFIED_MAX_AGE = 30

Finding = tuple[str, str]  # ("ERROR" | "WARN", message)


# --- parsing helpers -------------------------------------------------------------------------


def section(text: str, heading: str) -> str:
    """The body of the first markdown section whose heading line starts with `heading`
    (hashes included, e.g. "### Schedule"), up to the next heading of the same or a higher level."""
    m = re.search(rf"^{re.escape(heading)}.*?$", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end() :]
    level = len(heading) - len(heading.lstrip("#"))
    nxt = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def table_rows(body: str) -> list[list[str]]:
    """Cells of every data row of the first table in `body` (header and separator dropped)."""
    rows = []
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return [r for r in rows[1:] if r and not set("".join(r)) <= set("-: ")]


def codes(cell: str) -> list[str]:
    return re.findall(r"`([^`]+)`", cell)


def git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], check=False, cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    return out.stdout.strip() if out.returncode == 0 else ""


# --- checks ------------------------------------------------------------------------------------


def check_links(text: str) -> list[Finding]:
    found = []
    for label, target in re.findall(r"\[([^\]]*)\]\(([^)\s]+)\)", text):
        if re.match(r"^(https?:|mailto:|#)", target):
            continue
        path = (STATE.parent / target.split("#")[0]).resolve()
        if not path.exists():
            found.append(("ERROR", f"link [{label}]({target}) in docs/state.md does not resolve"))
    return found


def expected_cloud_schedule(tf: str) -> set[tuple[str, str]]:
    block = tf.split("schedules = {", 1)[1].split("schedule_pairs", 1)[0]
    pairs, job = set(), None
    for line in block.splitlines():
        m = re.match(r"\s*([\w-]+)\s*=\s*\{", line)
        if m:
            job = m.group(1)
        if job:
            for cron in re.findall(r'"[\w-]+"\s*=\s*"([^"]+)"', line):
                pairs.add((job, cron))
    return pairs


def expected_desktop_schedule(py: str) -> set[tuple[str, str]]:
    return {
        (WEEKDAYS[int(wd)], f"{int(h):02d}:{int(mi):02d}")
        for wd, h, mi in re.findall(r"\((\d), time\((\d+), (\d+)\)\)", py)
    }


def hub_schedule(text: str) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    cloud, desktop = set(), set()
    for row in table_rows(section(text, "### Schedule")):
        if len(row) < 4:
            continue
        what, where, cron = row[1], row[2], row[3]
        crons = codes(cron)
        if where == "cloud":
            jobs = [c for c in codes(what) if c.startswith("nfl-")]
            if jobs:
                job = jobs[0].removeprefix("nfl-")
                cloud.update((job, c) for c in crons)
        elif where == "desktop":
            for c in crons:
                day, _, hhmm = c.partition(" ")
                desktop.add((day, hhmm))
    return cloud, desktop


def check_schedule(text: str) -> list[Finding]:
    found = []
    cloud, desktop = hub_schedule(text)
    if JOBS_TF.exists():
        want = expected_cloud_schedule(JOBS_TF.read_text())
        for job, cron in sorted(want - cloud):
            found.append(("ERROR", f"schedule table lacks infra/jobs.tf entry nfl-{job} `{cron}`"))
        for job, cron in sorted(cloud - want):
            found.append(("ERROR", f"schedule table has nfl-{job} `{cron}`, not in infra/jobs.tf"))
    if NARRATIVE_PY.exists():
        want = expected_desktop_schedule(NARRATIVE_PY.read_text())
        for day, hhmm in sorted(want - desktop):
            found.append(("ERROR", f"schedule table lacks desktop pass `{day} {hhmm}` (PASSES)"))
        for day, hhmm in sorted(desktop - want):
            found.append(
                ("ERROR", f"schedule table has desktop pass `{day} {hhmm}`, not in PASSES")
            )
    return found


def workstream_rows(text: str) -> list[dict[str, str]]:
    rows = []
    for row in table_rows(section(text, "## Workstreams")):
        if len(row) >= 5:
            rows.append(
                {
                    "track": row[0],
                    "branches": codes(row[1]),
                    "status": row[4].lower(),
                    "pr": row[5] if len(row) > 5 else "",
                }
            )
    return rows


def board_branches() -> set[str] | None:
    """Branches named by the hub's track files (`branch:` in each file's frontmatter)."""
    if not TRACKS.is_dir():
        return None
    out: set[str] = set()
    for f in TRACKS.glob("*.md"):
        m = re.search(
            r"^branch:\s*[\"'`]?([^\s\"'`]+)", f.read_text(errors="replace"), re.MULTILINE
        )
        if m:
            out.add(m.group(1))
    return out


def worktree_branches() -> dict[str, str]:
    """branch -> worktree path, from `git worktree list`, the primary checkout's main excluded."""
    out, path = {}, ""
    for line in git("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            branch = line.rsplit("/", 1)[-1]
            if branch != "main":
                out[branch] = path
    return out


def open_prs() -> dict[str, int] | None:
    try:
        out = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--json", "number,headRefName"],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    if out.returncode != 0:
        return None
    return {p["headRefName"]: p["number"] for p in json.loads(out.stdout or "[]")}


def check_workstreams(text: str) -> list[Finding]:
    found = []
    rows = workstream_rows(text)
    if not rows:
        return [("ERROR", "docs/state.md has no Workstreams table")]
    listed = {b for r in rows for b in r["branches"]}
    for branch, path in worktree_branches().items():
        if branch not in listed:
            found.append(
                ("WARN", f"worktree {path} ({branch}) has no workstream row in docs/state.md")
            )
    board = board_branches()
    if board is None:
        found.append(
            (
                "WARN",
                ".notes/hub/tracks/ is missing (one file per active track; see docs/state-maintenance.md)",
            )
        )
    else:
        for branch, path in worktree_branches().items():
            if branch not in board:
                found.append(
                    ("WARN", f"worktree {path} ({branch}) has no track file in .notes/hub/tracks/")
                )
    prs = open_prs()
    if prs is not None:
        for branch, number in prs.items():
            if branch not in listed:
                found.append(
                    ("WARN", f"open PR #{number} ({branch}) has no workstream row in docs/state.md")
                )
    return found


def doc_status_date(path: Path) -> dt.date | None:
    """The date in a doc's own `Status: ..., verified YYYY-MM-DD` line (first lines), if any."""
    try:
        head = "\n".join(path.read_text().splitlines()[:6])
    except OSError:
        return None
    m = re.search(r"^Status:.*?verified (\d{4}-\d{2}-\d{2})", head, re.MULTILINE)
    return dt.date.fromisoformat(m.group(1)) if m else None


def check_docs_map(text: str, today: dt.date) -> list[Finding]:
    found = []
    for row in table_rows(section(text, "## Docs map")):
        if len(row) < 3:
            continue
        m = re.search(r"\]\(([^)]+)\)", row[0])
        d = re.search(r"\d{4}-\d{2}-\d{2}", row[2])
        if not m or not d:
            continue
        target, verified = m.group(1), dt.date.fromisoformat(d.group(0))
        path = STATE.parent / target
        if (today - verified).days > VERIFIED_MAX_AGE:
            found.append(
                ("WARN", f"{target}: verified {verified}, more than {VERIFIED_MAX_AGE} days ago")
            )
        if path.is_dir():
            continue
        own = doc_status_date(path)
        if own and own != verified:
            found.append(
                ("ERROR", f"{target}: docs map says verified {verified}, its status line {own}")
            )
        rel = str(path.relative_to(ROOT))
        if git("status", "--porcelain", "--", rel):
            last = today
        else:
            stamp = git("log", "-1", "--format=%as", "--", rel)
            last = dt.date.fromisoformat(stamp) if stamp else verified
        if last > verified:
            found.append(
                (
                    "WARN",
                    f"{target} changed {last}, after its verified date {verified}: re-verify it",
                )
            )
    return found


def check_bottom_line(text: str, today: dt.date) -> list[Finding]:
    m = re.search(r"^## Bottom line \(as of (\d{4}-\d{2}-\d{2})\)", text, re.MULTILINE)
    if not m:
        return [("ERROR", "docs/state.md lacks '## Bottom line (as of YYYY-MM-DD)'")]
    age = (today - dt.date.fromisoformat(m.group(1))).days
    if age > BOTTOM_LINE_MAX_AGE:
        return [("WARN", f"bottom line is {age} days old; rewrite it with today's date")]
    return []


def run(today: dt.date | None = None) -> list[Finding]:
    today = today or dt.date.today()
    if not STATE.exists():
        return [("ERROR", "docs/state.md is missing")]
    text = STATE.read_text()
    found: list[Finding] = []
    for check in (check_links, check_schedule, check_workstreams):
        found += check(text)
    found += check_docs_map(text, today)
    found += check_bottom_line(text, today)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true", help="exit 1 on any ERROR")
    args = ap.parse_args()
    findings = run()
    for level, msg in findings:
        print(f"{level}: {msg}")
    errors = sum(1 for level, _ in findings if level == "ERROR")
    if not findings:
        print("state_check: docs/state.md is consistent")
    return 1 if args.strict and errors else 0


if __name__ == "__main__":
    sys.exit(main())
