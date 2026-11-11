"""Did each scheduled job run? `nfl status --json` for the project hub's Status tab (Contract B in
~/dev/t3code/.notes/hub/plans/hub-v2.md). Read-only: it lists, reads and fetches, never writes.

Sources, queried concurrently (a run takes a few seconds; the hub runs it every 10 minutes):
  Cloud jobs  the latest Cloud Run execution of every job in infra/jobs.tf, with its crons
  Desktop     the Wed and Sat narrative passes, from the nfl-desktop-narrative log (PASSES)
  Site        meta.json's generated_at on the public bucket, and the last lock commit on main
  Usage       Odds API credits from the newest snapshot manifest in the data bucket (no API call)

The job list, crons, project and region come from infra/ (the source scripts/state_check.py also
checks docs/state.md against), so a new job or cron shows up here without a second copy.
Failures never raise: a source that can't be read becomes an item with state "failed", and the
command exits 0 (the hub treats a non-zero exit as a broken feed).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
TZ = "America/New_York"
SITE_META_URL = "https://storage.googleapis.com/nfl-project-prod-site/site/meta.json"
SITE_URL = "https://nfl-project-prod.web.app"
# nfl-retro rebuilds the site JSON every day at 07:00 ET (scripts/cloud-job.sh), and the refresh,
# daily, odds, lock and site jobs do too, so meta.json is never more than a day old when the jobs
# run. 26 hours = a day plus the retro's 30-minute timeout and slack for a slow start.
SITE_STALE_AFTER = timedelta(hours=26)
# A desktop pass takes ~13 minutes a game, so 3 to 4 hours for a full week. A start with no
# "done" or ERROR after it is still running for this long, then counts as a pass that died.
DESKTOP_RUNNING_FOR = timedelta(hours=8)
DESKTOP_LOG = "nfl-desktop-narrative"
LOOKBACK_DAYS = 21
CMD_TIMEOUT = 30  # seconds per external command; they run in parallel, well inside the hub's 60

LABELS = {
    "weekly-refresh": "Tuesday refresh",
    "narrative-check": "Narrative check before each lock",
    "lock-thu": "Lock Thursday games",
    "lock-sat": "Lock Saturday to Monday games",
    "odds-snapshot": "Odds snapshot",
    "daily": "Daily pass (Wed, Fri, Sat)",
    "retro": "Retros and recaps",
    "site": "Site rebuild (on demand)",
}
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

Run = Callable[[list[str]], tuple[int, str, str]]
Fetch = Callable[[str], bytes]


# ------------------------------------------------------------------ infra (the one trusted list)


def _block(text: str, opener: str) -> str:
    """The `{ ... }` body that follows `opener` (brace-matched)."""
    start = text.index(opener) + len(opener)
    depth, i = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[start : i - 1]


def parse_jobs_tf(text: str) -> dict[str, list[str]]:
    """{job: [cron, ...]} for every Cloud Run job in infra/jobs.tf, in file order ([] = on demand)."""
    jobs = re.findall(r"^\s*([\w-]+)\s*=\s*\{", _block(text, "jobs = {"), re.MULTILINE)
    out: dict[str, list[str]] = {j: [] for j in jobs}
    job = None
    for line in _block(text, "schedules = {").splitlines():
        m = re.match(r"\s*([\w-]+)\s*=\s*\{", line)
        if m:
            job = m.group(1)
        if job:
            out.setdefault(job, []).extend(re.findall(r'"[\w-]+"\s*=\s*"([^"]+)"', line))
    return out


def parse_tfvars(text: str) -> dict[str, str]:
    return dict(re.findall(r'^\s*(\w+)\s*=\s*"([^"]*)"', text, re.MULTILINE))


# ------------------------------------------------------------------ formatting helpers


def _ts(s: str) -> datetime:
    """RFC 3339 (any precision, Z or offset) to an aware datetime."""
    s = s.replace("Z", "+00:00")
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(\.\d+)?(.*)", s)
    if m and m.group(2):  # fromisoformat takes at most 6 fractional digits
        s = m.group(1) + m.group(2)[:7] + m.group(3)
    return datetime.fromisoformat(s)


def _iso(t: datetime) -> str:
    return t.astimezone(ET).isoformat(timespec="seconds")


def _dur(d: timedelta) -> str:
    s = int(d.total_seconds())
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}h {m:02d}m" if h else f"{m}m {sec:02d}s" if m else f"{sec}s"


def _schedule(crons: list[str]) -> dict:
    if not crons:
        return {}
    return {"schedule": crons[0] if len(crons) == 1 else crons, "tz": TZ}


def _failed(id_: str, label: str, group: str, detail: str, now: datetime) -> dict:
    return {
        "id": id_,
        "label": label,
        "group": group,
        "last": {"at": _iso(now), "state": "failed", "detail": detail[:300]},
    }


def _logs_url(project: str, query: str) -> str:
    return f"https://console.cloud.google.com/logs/query;query={quote(query, safe='')}?project={project}"


# ------------------------------------------------------------------ cloud jobs


def execution_last(ex: dict, now: datetime, project: str, region: str) -> dict:
    """One Cloud Run execution (gcloud's v1 JSON) as Contract B's `last`."""
    st = ex.get("status", {})
    name = ex["metadata"]["name"]
    created = _ts(ex["metadata"]["creationTimestamp"])
    started = _ts(st["startTime"]) if st.get("startTime") else created
    url = (
        "https://console.cloud.google.com/run/jobs/executions/details/"
        f"{region}/{name}/tasks?project={project}"
    )
    if not st.get("completionTime"):
        return {
            "at": _iso(created),
            "state": "running",
            "detail": f"running for {_dur(now - started)}",
            "url": url,
        }
    took = _dur(_ts(st["completionTime"]) - started)
    if st.get("succeededCount"):
        return {"at": _iso(created), "state": "ok", "detail": f"took {took}", "url": url}
    if st.get("cancelledCount"):
        return {
            "at": _iso(created),
            "state": "failed",
            "detail": f"cancelled after {took}",
            "url": url,
        }
    msg = next(
        (c.get("message", "") for c in st.get("conditions", []) if c.get("type") == "Completed"), ""
    )
    code = re.search(r"exit code:? (\d+)", msg)
    why = f"exit code {code.group(1)}" if code else (msg[:120] or "failed")
    return {"at": _iso(created), "state": "failed", "detail": f"{why} after {took}", "url": url}


def cloud_item(
    job: str,
    crons: list[str],
    executions: list[dict] | None,
    error: str | None,
    now: datetime,
    project: str,
    region: str,
) -> dict:
    name = f"nfl-{job}"
    log_query = f'resource.type="cloud_run_job"\nresource.labels.job_name="{name}"'
    item: dict = {
        "id": name,
        "label": LABELS.get(job, name),
        "group": "Cloud jobs",
        **_schedule(crons),
        "links": [
            {
                "label": "Executions",
                "url": f"https://console.cloud.google.com/run/jobs/details/{region}/{name}/executions?project={project}",
            },
            {"label": "Logs", "url": _logs_url(project, log_query)},
        ],
    }
    if error is not None:
        item["last"] = {
            "at": _iso(now),
            "state": "failed",
            "detail": f"could not read executions: {error}"[:300],
        }
    elif executions:
        latest = max(executions, key=lambda e: _ts(e["metadata"]["creationTimestamp"]))
        item["last"] = execution_last(latest, now, project, region)
        if latest.get("status", {}).get("logUri"):
            item["links"].append({"label": "Last run's logs", "url": latest["status"]["logUri"]})
    return item  # no executions on record: no `last`, so the hub can call a passed schedule missed


# ------------------------------------------------------------------ desktop passes


def _pass_cron(weekday: int, hhmm) -> str:
    return f"{hhmm.minute} {hhmm.hour} * * {(weekday + 1) % 7}"  # Python Mon=0 -> cron Sun=0


def desktop_items(entries: list[dict], now: datetime, project: str, passes=None) -> list[dict]:
    """One item per scheduled desktop pass, from nfl-desktop-narrative log entries (any order).

    An entry belongs to the most recent scheduled pass at or before it (a hand rerun on Monday
    counts toward Saturday's). Within the latest pass that has entries, the run is the last
    "started" line and what follows it: "done" = ok, an ERROR = failed, nothing yet = running
    (failed after DESKTOP_RUNNING_FOR). An ERROR with no start (a failed git fetch) = failed.
    """
    from nfl.llm.narrative import PASSES, last_pass

    passes = passes or PASSES
    by_pass: dict[int, dict[datetime, list[tuple[datetime, str, str]]]] = {
        wd: {} for wd, _ in passes
    }
    for e in entries:
        text = e.get("textPayload") or json.dumps(e.get("jsonPayload", ""))
        if "narrative pass" not in text and e.get("severity") != "ERROR":
            continue  # setup tests, warnings about local edits
        t = _ts(e["timestamp"])
        start = last_pass(t.astimezone(UTC).replace(tzinfo=None)).replace(tzinfo=UTC)
        wd = start.astimezone(ET).weekday()
        if wd in by_pass:
            by_pass[wd].setdefault(start, []).append((t, e.get("severity", "DEFAULT"), text))

    items = []
    for wd, hhmm in passes:
        day = WEEKDAY[wd]
        item: dict = {
            "id": f"desktop-narrative-{day.lower()}",
            "label": f"Desktop narrative pass, {day} {hhmm:%H:%M}",
            "group": "Desktop",
            "schedule": _pass_cron(wd, hhmm),
            "tz": TZ,
            "links": [
                {
                    "label": "Logs",
                    "url": _logs_url(project, f'logName="projects/{project}/logs/{DESKTOP_LOG}"'),
                }
            ],
        }
        if by_pass[wd]:
            item["last"] = _desktop_last(sorted(by_pass[wd][max(by_pass[wd])]), now)
        items.append(item)
    return items


def _desktop_last(events: list[tuple[datetime, str, str]], now: datetime) -> dict:
    starts = [i for i, (_, _, text) in enumerate(events) if "pass started" in text]
    run = events[starts[-1] :] if starts else events
    t0, _, first = run[0]
    week = re.search(r"(\d{4}) week (\d+)", first)
    what = f"{week.group(1)} week {week.group(2)}" if week else ""
    errors = [
        (t, text) for t, sev, text in run if sev in ("ERROR", "CRITICAL", "ALERT", "EMERGENCY")
    ]
    if errors:
        _, text = errors[-1]
        return {
            "at": _iso(t0),
            "state": "failed",
            "detail": text.removeprefix("desktop narrative pass failed: ")[:300],
        }
    done = [t for t, _, text in run if "pass done" in text]
    if done:
        return {
            "at": _iso(t0),
            "state": "ok",
            "detail": f"{what}, took {_dur(done[-1] - t0)}".lstrip(", "),
        }
    if starts and now - t0 < DESKTOP_RUNNING_FOR:
        return {
            "at": _iso(t0),
            "state": "running",
            "detail": f"{what}, running for {_dur(now - t0)}".lstrip(", "),
        }
    return {
        "at": _iso(t0),
        "state": "failed",
        "detail": f"{what}: started, but no finish was logged".lstrip(": "),
    }


# The check runs half an hour before each lock (infra/jobs.tf): a pass that finishes later than
# this after the check missed the lock, which the resolved detail says.
CHECK_BEFORE_LOCK = timedelta(minutes=30)


def resolve_narrative_check(item: dict, entries: list[dict]) -> dict:
    """A failed nfl-narrative-check counts as resolved (state ok, the failure kept in the detail)
    when a desktop pass in the same pass window logged "pass done" after the check ran. The pass
    script logs "done" only when every upcoming game was stored, which is what the check tests.
    Without this, a failure handled by a rerun stays red until the next scheduled check."""
    from nfl.llm.narrative import last_pass

    last = item.get("last") or {}
    if last.get("state") != "failed" or "detail" not in last:
        return item
    if last["detail"].startswith("could not read") or last["detail"].startswith("cancelled"):
        return item
    checked = _ts(last["at"])

    def window(t: datetime) -> datetime:
        return last_pass(t.astimezone(UTC).replace(tzinfo=None))

    done = sorted(
        t
        for e in entries
        if "narrative pass done" in (e.get("textPayload") or "")
        and (t := _ts(e["timestamp"])) > checked
        and window(t) == window(checked)
    )
    if not done:
        return item
    fin = done[0].astimezone(ET)
    late = " (after the lock)" if done[0] > checked + CHECK_BEFORE_LOCK else ""
    detail = (
        f"resolved: failed {checked.astimezone(ET):%a %H:%M} ({last['detail']}), then the "
        f"desktop pass stored every game, done {fin:%a %H:%M}{late}"
    )
    return {**item, "last": {**last, "state": "ok", "detail": detail[:300]}}


# ------------------------------------------------------------------ site, lock commit, credits


def site_item(meta: dict | None, error: str | None, now: datetime) -> dict:
    item: dict = {
        "id": "site-data",
        "label": "Site data freshness",
        "group": "Site",
        "links": [{"label": "Site", "url": SITE_URL}, {"label": "meta.json", "url": SITE_META_URL}],
    }
    if error is not None or not meta or "generated_at" not in meta:
        item["last"] = {
            "at": _iso(now),
            "state": "failed",
            "detail": f"could not read meta.json: {error or 'no generated_at'}"[:300],
        }
        return item
    gen = _ts(meta["generated_at"])
    age = now - gen
    stale = age > SITE_STALE_AFTER
    week = f"week {meta['current_week']}, " if meta.get("current_week") else ""
    item["last"] = {
        "at": _iso(gen),
        "state": "failed" if stale else "ok",
        "detail": f"{week}{_dur(age)} old"
        + (f" (stale after {_dur(SITE_STALE_AFTER)})" if stale else ""),
        "url": SITE_META_URL,
    }
    return item


def lock_item(commit: dict | None, error: str | None, now: datetime, repo: str) -> dict:
    item: dict = {
        "id": "lock-commit",
        "label": "Last lock artifact on main",
        "group": "Site",
        "links": [
            {
                "label": "History",
                "url": f"https://github.com/{repo}/commits/main/public/predictions",
            }
        ],
    }
    if error is not None or not commit:
        item["last"] = {
            "at": _iso(now),
            "state": "failed",
            "detail": f"could not read the commit: {error or 'none found'}"[:300],
        }
        return item
    c = commit["commit"]
    item["last"] = {
        "at": _iso(_ts(c["committer"]["date"])),
        "state": "ok",
        "detail": c["message"].splitlines()[0][:120],
        "url": commit["html_url"],
    }
    return item


def odds_item(manifest: dict) -> dict | None:
    used, left = manifest.get("requests_used"), manifest.get("requests_remaining")
    if used is None or left is None:
        return None
    return {
        "id": "odds-api-credits",
        "label": "Odds API credits used this month",
        "group": "Usage",
        "value": used,
        "limit": used + left,
        "unit": "credits",
        "last": {
            "at": _iso(_ts(manifest["fetched_at"])),
            "state": "ok",
            "detail": f"{left} left after the last snapshot",
        },
        "links": [{"label": "Account", "url": "https://the-odds-api.com/account/"}],
    }


# ------------------------------------------------------------------ I/O and the whole report


def _run(args: list[str]) -> tuple[int, str, str]:
    try:
        p = subprocess.run(args, check=False, capture_output=True, text=True, timeout=CMD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {CMD_TIMEOUT}s"
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout, p.stderr


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=CMD_TIMEOUT) as r:
        return r.read()


def _err(rc: int, err: str) -> str:
    lines = [ln for ln in err.strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else f"exit {rc}")[:200]


def _gcloud_problem(run: Run, have_gcloud: bool) -> str | None:
    if not have_gcloud:
        return "gcloud is not installed on this machine"
    rc, out, err = run(["gcloud", "auth", "print-access-token", "--quiet"])
    if rc != 0 or not out.strip():
        return f"gcloud is not logged in ({_err(rc, err)}); run `gcloud auth login`"
    return None


def collect(
    root: Path,
    now: datetime | None = None,
    run: Run = _run,
    fetch: Fetch = _fetch,
    have_gcloud: bool | None = None,
) -> list[dict]:
    now = now or datetime.now(UTC)
    jobs = parse_jobs_tf((root / "infra" / "jobs.tf").read_text())
    tfvars = parse_tfvars((root / "infra" / "prod.auto.tfvars").read_text())
    project, region = (
        tfvars.get("project_id", "nfl-project-prod"),
        tfvars.get("region", "us-central1"),
    )
    repo = tomllib.loads((root / "hub.toml").read_text()).get(
        "github", "austin-chemelli/nfl-project"
    )
    have_gcloud = shutil.which("gcloud") is not None if have_gcloud is None else have_gcloud

    def executions(job: str):
        rc, out, err = run([
            "gcloud", "run", "jobs", "executions", "list", f"--job=nfl-{job}", f"--region={region}",
            f"--project={project}", "--limit=5", "--format=json",
        ])  # fmt: skip
        if rc != 0:
            raise RuntimeError(_err(rc, err))
        return json.loads(out or "[]")

    def desktop_log():
        rc, out, err = run([
            "gcloud", "logging", "read", f'logName="projects/{project}/logs/{DESKTOP_LOG}"',
            f"--project={project}", f"--freshness={LOOKBACK_DAYS}d", "--limit=200", "--format=json",
        ])  # fmt: skip
        if rc != 0:
            raise RuntimeError(_err(rc, err))
        return json.loads(out or "[]")

    def odds_manifest():
        base = f"gs://{project}-data/raw/odds_api"
        rc, out, err = run(["gcloud", "storage", "ls", f"--project={project}", f"{base}/*/"])
        if rc != 0:
            raise RuntimeError(_err(rc, err))
        snaps = [ln.rstrip("/") for ln in out.split() if "snapshot_ts=" in ln]
        if not snaps:
            return None
        newest = max(snaps, key=lambda s: s.rsplit("snapshot_ts=", 1)[1])
        rc, out, err = run(
            ["gcloud", "storage", "cat", f"--project={project}", f"{newest}/manifest.json"]
        )
        if rc != 0:
            raise RuntimeError(_err(rc, err))
        return json.loads(out)

    def site_meta():
        return json.loads(fetch(SITE_META_URL))

    def lock_commit():
        rc, out, err = run(
            ["gh", "api", f"repos/{repo}/commits?sha=main&path=public/predictions&per_page=1"]
        )
        if rc != 0:
            raise RuntimeError(_err(rc, err))
        commits = json.loads(out)
        return commits[0] if commits else None

    def safe(f, *a):
        try:
            return f(*a), None
        except RuntimeError as e:  # a command's own error line
            return None, str(e)
        except Exception as e:  # noqa: BLE001 - any failure becomes a failed item, never a crash
            return None, f"{type(e).__name__}: {e}"[:200]

    with ThreadPoolExecutor(max_workers=len(jobs) + 6) as pool:
        meta_f = pool.submit(safe, site_meta)
        commit_f = pool.submit(safe, lock_commit)
        problem = _gcloud_problem(run, have_gcloud)
        if problem is None:
            exec_f = {j: pool.submit(safe, executions, j) for j in jobs}
            desk_f = pool.submit(safe, desktop_log)
            odds_f = pool.submit(safe, odds_manifest)

        items: list[dict] = []
        if problem is None:
            for job, crons in jobs.items():
                res, err = exec_f[job].result()
                items.append(cloud_item(job, crons, res, err, now, project, region))
            entries, err = desk_f.result()
            if not err:
                items = [
                    resolve_narrative_check(it, entries)
                    if it["id"] == "nfl-narrative-check"
                    else it
                    for it in items
                ]
            if err:
                items.append(
                    _failed(
                        "desktop-narrative",
                        "Desktop narrative passes",
                        "Desktop",
                        f"could not read the desktop log: {err}",
                        now,
                    )
                )
            else:
                items.extend(desktop_items(entries, now, project))
        else:
            items.append(_failed("cloud-jobs", "Cloud Run jobs", "Cloud jobs", problem, now))
            items.append(
                _failed("desktop-narrative", "Desktop narrative passes", "Desktop", problem, now)
            )

        meta, err = meta_f.result()
        items.append(site_item(meta, err, now))
        commit, err = commit_f.result()
        items.append(lock_item(commit, err, now, repo))

        if problem is None:
            manifest, err = odds_f.result()
            if err:
                items.append(
                    _failed(
                        "odds-api-credits",
                        "Odds API credits used this month",
                        "Usage",
                        f"could not read the last odds manifest: {err}",
                        now,
                    )
                )
            elif manifest and (item := odds_item(manifest)):
                items.append(item)
        else:
            items.append(
                _failed(
                    "odds-api-credits", "Odds API credits used this month", "Usage", problem, now
                )
            )
    return items


def render_text(items: list[dict]) -> str:
    rows = [("GROUP", "ITEM", "STATE", "LAST (ET)", "DETAIL")]
    for it in items:
        last = it.get("last") or {}
        at = _ts(last["at"]).astimezone(ET).strftime("%a %m-%d %H:%M") if last.get("at") else "-"
        detail = last.get("detail", "")
        if "value" in it:
            detail = f"{it['value']}/{it.get('limit', '?')} {it.get('unit', '')}; {detail}".rstrip(
                "; "
            )
        rows.append((it.get("group", ""), it["label"], last.get("state", "never"), at, detail))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    return "\n".join(
        "  ".join(c.ljust(w) for c, w in zip(r[:4], widths, strict=True)) + "  " + r[4]
        for r in rows
    )
