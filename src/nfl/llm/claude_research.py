"""Narrative research by headless Claude Code on Austin's Max login (ADR 0030, M6.8).

One `claude -p` session per game, in a scratch folder outside any checkout (so no CLAUDE.md, hooks,
skills or MCP connectors load), with only WebSearch, WebFetch and Read/Write/Edit inside that
folder (`--tools`, `--permission-mode dontAsk`, a generated settings file). The folder holds the
game, both coaches and both teams' weekly rosters (`context.json`) and a complete example record.
The model searches, follows leads and writes `record.json`; then code decides what may be stored:

    claude -p (stream-json transcript) -> record.json
    -> pages the model opened, from the transcript; code's own read of each cited page (date, text)
    -> nfl.llm.checks: opened URLs, page dates, roster, standings, line, numbers on the page
    -> GameNarrative validation (one repair turn in the same session on a schema error) -> ingest

The app never touches a credential: `claude` is an external program on its own login, every
API-key variable is removed from its environment, and `require_subscription_login` refuses to run
unless `claude auth status` reports a claude.ai login (no API key, no paid API, ADR 0030).
Records are `producer: claude_max`, `prompt_version: claude_v2` (schema v3, ADR 0032: the starting
QB reporting names, starters ruled out and a fired coach, each cited and roster-checked). One row per game session goes to
`marts/llm_calls.parquet` (job `research_claude`); the folder (prompt, transcript, raw and checked
record, drops) is kept under raw/narrative_claude/.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from string import Template
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from nfl.config import Paths, now_utc, snapshot_ts
from nfl.llm import checks
from nfl.llm.client import append_call
from nfl.llm.fetch import Fetcher
from nfl.llm.narrative import (
    MAX_SOURCE_AGE_DAYS,
    STATUS_PASSES,
    GameNarrative,
    _check_against_schedule,
    example,
    ingest,
)
from nfl.llm.research import Game, full_names

PROMPT = Path(__file__).parent / "prompts" / "claude_research_v2.md"
PROMPT_VERSION = "claude_v2"
STATUS_PROMPT = Path(__file__).parent / "prompts" / "claude_status_v1.md"
STATUS_VERSION = "claude_status_v1"
STATUS_FIELDS = ("qb_status", "qb_named_starter", "injury_impact", "starters_ruled_out", "key_absences")  # fmt: skip
PRODUCER = "claude_max"
JOB = "research_claude"
MODEL = os.environ.get("NARRATIVE_CLAUDE_MODEL", "sonnet")
PARALLEL = 3  # games at once; a 13-game pass is about 15 minutes
TIMEOUT_S = 30 * 60
WINDOW_DAYS = 9
TOOLS = "WebSearch,WebFetch,Read,Write,Edit"
# Never let a run bill the API or use a token other than the login (ADR 0030).
CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
)  # fmt: skip
ROSTER_STATUSES = ("ACT", "INA", "RES", "DEV")
ET = ZoneInfo("America/New_York")


class LoginError(RuntimeError):
    pass


def claude_bin() -> str:
    return os.environ.get("NARRATIVE_CLAUDE_BIN", "claude")


def clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in CREDENTIAL_VARS}


def require_subscription_login(run=subprocess.run) -> str:
    """'<plan>' when Claude Code is logged in to claude.ai; LoginError otherwise (logged out, an
    API key or another method, not installed)."""
    try:
        p = run([claude_bin(), "auth", "status", "--json"], capture_output=True, text=True,
                timeout=60, env=clean_env())  # fmt: skip
        d = json.loads(p.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        raise LoginError(f"claude auth status failed ({type(e).__name__}): is Claude Code installed?") from e  # fmt: skip
    if not d.get("loggedIn"):
        raise LoginError("Claude is not logged in on this machine: run `claude`, then /login with the Max account")  # fmt: skip
    if d.get("authMethod") != "claude.ai":
        raise LoginError(f"Claude is signed in with {d.get('authMethod')!r}, not the claude.ai Max login")  # fmt: skip
    return str(d.get("subscriptionType") or "?")


# ------------------------------------------------------------------------------- the folder


def _roster_lines(paths: Paths, season: int, week: int, team: str) -> tuple[int | None, list[str]]:
    root = paths.curated / "rosters_weekly" / f"season={season}"
    if not root.exists():
        return None, []
    r = pl.read_parquet(root).filter(pl.col("week") <= week)
    if r.is_empty():
        return None, []
    wk = int(r["week"].max())
    r = r.filter((pl.col("week") == wk) & (pl.col("team") == team) & pl.col("status").is_in(ROSTER_STATUSES))  # fmt: skip
    rows = r.sort("position", "full_name").select("full_name", "position", "status").iter_rows()
    return wk, [f"{n} ({p}, {s})" for n, p, s in rows]


def prepare(paths: Paths, row: dict, folder: Path, model: str, now: datetime, *, base: GameNarrative | None = None) -> str:  # fmt: skip
    """Write the folder's inputs and return the prompt (the status prompt when `base`, the game's
    earlier record, is given: its status fields go to `previous.json`)."""
    g = Game.from_slate(row)
    names = full_names()
    folder.mkdir(parents=True, exist_ok=True)

    def team(t: str, side: str) -> dict:
        wk, lines = _roster_lines(paths, g.season, g.week, t)
        src = row.get(f"{side}_qb_source") or "schedule"
        return {"abbr": t, "name": names.get(t, t), "head_coach": row.get(f"{side}_coach"),
                "projected_qb": row.get(f"{side}_qb_name"),
                "projected_qb_from": f"{'the depth chart' if src == 'depth chart' else 'the schedule'}'s first QB as of {now:%Y-%m-%d}: a projection to confirm, not a fact",
                "roster_week": wk, "roster": lines}  # fmt: skip

    kick = g.kickoff_utc.replace(tzinfo=UTC)
    home, away = team(g.home, "home"), team(g.away, "away")
    ctx = {"game_id": g.game_id, "season": g.season, "week": g.week, "kickoff_utc": kick.isoformat(),
           "stadium": g.stadium, "roof": g.roof, "home": home, "away": away}  # fmt: skip
    (folder / "context.json").write_text(json.dumps(ctx, indent=1))
    if base is None:
        (folder / "example.json").write_text(json.dumps(example(), indent=1))
    else:
        prev = {side: {"team": getattr(base, side).team, **{f: getattr(getattr(base, side), f) for f in STATUS_FIELDS}} for side in ("home", "away")}  # fmt: skip
        (folder / "previous.json").write_text(json.dumps(prev, indent=1))
    p = str(folder.resolve())
    settings = {"permissions": {
        "allow": ["WebSearch", "WebFetch", f"Read(/{p}/**)", f"Write(/{p}/**)", f"Edit(/{p}/**)"],
        "deny": ["Bash", "Agent", "NotebookEdit", "Read(~/.claude/**)", "Read(~/.ssh/**)",
                 "Read(~/.config/**)", "Read(~/dev/**)", "Read(**/.env)"],
    }}  # fmt: skip
    (folder / "settings.json").write_text(json.dumps(settings, indent=1))
    n = now.replace(tzinfo=UTC, microsecond=0)
    return Template((STATUS_PROMPT if base else PROMPT).read_text()).substitute(
        away_name=names.get(g.away, g.away), away=g.away, home_name=names.get(g.home, g.home),
        home=g.home, season=g.season, week=g.week, kickoff_utc=kick.strftime("%Y-%m-%d %H:%M"),
        kickoff_et=kick.astimezone(ET).strftime("%a %b %-d %-I:%M %p"),
        venue=f"{g.stadium} ({g.roof or 'roof unknown'})", today=n.date().isoformat(),
        now=n.isoformat(), roster_week=home["roster_week"] or "unknown",
        window_start=(n.date() - timedelta(days=WINDOW_DAYS)).isoformat(),
        model_label=f"claude-code/{model}", prompt_version=STATUS_VERSION if base else PROMPT_VERSION,
    )  # fmt: skip


def call(folder: Path, prompt: str, model: str, *, resume: str | None = None, run=subprocess.run) -> dict:  # fmt: skip
    """One `claude -p` session (or a resumed turn); returns its result event plus `_transcript`."""
    cmd = [claude_bin(), "-p", prompt, "--model", model, "--setting-sources", "",
           "--strict-mcp-config", "--tools", TOOLS, "--permission-mode", "dontAsk",
           "--settings", str(folder / "settings.json"), "--output-format", "stream-json", "--verbose"]  # fmt: skip
    if resume:
        cmd += ["--resume", resume]
    tr = folder / f"transcript{len(list(folder.glob('transcript*.jsonl'))) or ''}.jsonl"
    t0 = time.monotonic()
    with tr.open("w") as f:
        try:
            p = run(cmd, cwd=folder, env=clean_env(), stdout=f, stderr=subprocess.STDOUT,
                    timeout=TIMEOUT_S, stdin=subprocess.DEVNULL)  # fmt: skip
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = 124
    res = next((e for e in reversed(_events(tr)) if e.get("type") == "result"), {})
    return {**res, "_rc": rc, "_seconds": time.monotonic() - t0, "_transcript": tr.name}


def _events(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def provenance(folder: Path) -> tuple[set[str], list[str]]:
    """(normalized URLs opened with WebFetch, search queries in order) from every transcript."""
    opened, queries = set(), []
    for tr in sorted(folder.glob("transcript*.jsonl")):
        for ev in _events(tr):
            msg = ev.get("message")
            content = msg.get("content") if isinstance(msg, dict) else None
            for c in content if isinstance(content, list) else []:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                inp = c.get("input") or {}
                if c.get("name") == "WebFetch" and inp.get("url"):
                    opened.add(checks.norm_url(inp["url"]))
                elif c.get("name") == "WebSearch" and inp.get("query"):
                    queries.append(inp["query"])
    return opened, queries


# ----------------------------------------------------------------------------- one game


@dataclass
class ClaudeRun:
    game_id: str
    ok: bool = False
    stored: Path | None = None
    error: str | None = None
    seconds: float = 0.0
    turns: int = 0
    searches: int = 0
    pages: int = 0
    dropped: Counter = field(default_factory=Counter)
    flags: Counter = field(default_factory=Counter)  # checks that count but don't drop
    usage: dict = field(default_factory=dict)
    api_equiv_usd: float | None = None
    folder: Path | None = None


def runs_dir(paths: Paths, season: int, week: int) -> Path:
    return paths.root / "raw" / "narrative_claude" / f"season={season}" / f"week={week:02d}"


def check_record(paths: Paths, raw: dict, folder: Path, fetcher: Fetcher, now: datetime, *, version: str = PROMPT_VERSION) -> tuple[dict, Counter, list]:  # fmt: skip
    """Run the checks on the model's record (a dict); returns (record, drops, log). Raises when
    what is left doesn't validate."""
    from nfl.features.store import games_frame

    raw = json.loads(json.dumps(raw))
    raw["producer"], raw["prompt_version"] = PRODUCER, version
    raw["reported_finished_at"] = raw.get("known_as_of")
    raw["known_as_of"] = now.replace(tzinfo=None, microsecond=0).isoformat()
    _check_against_schedule(paths, raw)
    opened, queries = provenance(folder)
    raw["searches"] = queries or raw.get(
        "searches"
    )  # what the transcript shows, not the model's word
    urls = sorted({str(c["source_url"]) for c in raw.get("claims", [])}
                  | {str(n["source_url"]) for s in ("home", "away") for n in raw[s].get("notes", []) if n.get("source_url")}
                  | {str(u) for s in ("home", "away") for x in raw[s].get("scheme_trends", []) for u in x["sources"]}
                  | {str(u) for m in raw.get("matchup_notes", []) for u in m["sources"]})  # fmt: skip
    pages = {u: fetcher.get(u) for u in urls if checks.norm_url(u) in opened}
    games = games_frame(paths)
    kick = datetime.fromisoformat(raw["kickoff_utc"])
    played = games.filter((pl.col("season") == raw["season"]) & pl.col("result").is_not_null()
                          & (pl.col("game_type") == "REG"))  # fmt: skip
    gp = max((played.filter((pl.col("home_team") == t) | (pl.col("away_team") == t)).height
              for t in (raw["home_team"], raw["away_team"])), default=0)  # fmt: skip
    names = full_names()
    ctx = checks.Context(
        home=raw["home_team"], away=raw["away_team"],
        roster=checks.roster_index(paths, raw["season"], raw["week"]),
        records=checks.season_records(games, raw["season"], (raw["home_team"], raw["away_team"]), kick),
        games_played=gp, opened=opened, pages=pages,
        known_as_of=now.date(), window_days=WINDOW_DAYS + 1,
        extra_text=" ".join([raw["home_team"], raw["away_team"], names.get(raw["home_team"], ""),
                             names.get(raw["away_team"], ""), f"week {raw['week']}", str(raw["season"])]),
    )  # fmt: skip
    rec, drops, log = checks.apply(raw, ctx)
    GameNarrative.model_validate(rec)
    return rec, drops, log


def check_status(paths: Paths, status: dict, base: GameNarrative, folder: Path, fetcher: Fetcher, now: datetime) -> tuple[dict, Counter, list]:  # fmt: skip
    """The late-status record: `status` (the model's status.json) checked like a full record's
    status fields and claims, merged onto a copy of `base` (the game's latest record). The checks
    run on a shaped record that holds only the status fields and their claims, so nothing of the
    base is re-judged against pages this run never opened. Kept from the base: everything but its
    injury and qb claims (the status supersedes them) and claims too old for the window. New:
    `known_as_of`, `producer`, `prompt_version` claude_status_v1, `pass_kind: status`, `qb_name`
    (the named starter, when there is one). Raises when the result doesn't validate."""
    keep = base.model_dump(mode="json")
    shaped = json.loads(json.dumps(keep))
    for side in ("home", "away"):
        t = shaped[side]
        t.update({"notes": [], "scheme_trends": [], "summary": "Status-only update of the earlier record."})  # fmt: skip
        t.update({f: v for f, v in (status.get(side) or {}).items() if f in STATUS_FIELDS})
    shaped["matchup_notes"], shaped["consensus_narrative"] = [], "Status-only update of the earlier record."  # fmt: skip
    shaped["claims"], shaped["searches"] = status.get("claims", []), status.get("searches") or ["status"]  # fmt: skip
    checked, drops, log = check_record(paths, shaped, folder, fetcher, now, version=STATUS_VERSION)
    cutoff = datetime.fromisoformat(checked["known_as_of"]).date()
    kept = [c for c in keep["claims"] if c["category"] not in ("injury", "qb")
            and (not c.get("published_at") or (cutoff - date.fromisoformat(c["published_at"][:10])).days <= MAX_SOURCE_AGE_DAYS)]  # fmt: skip
    out = {**keep, "schema_version": "3", "producer": PRODUCER, "prompt_version": STATUS_VERSION,
           "pass_kind": "status", "model": checked["model"], "known_as_of": checked["known_as_of"],
           "reported_finished_at": checked.get("reported_finished_at"),
           "claims": [*kept, *checked["claims"]], "searches": [*keep["searches"], *checked["searches"]]}  # fmt: skip
    for side in ("home", "away"):
        for f in STATUS_FIELDS:
            out[side][f] = checked[side][f]
        if out[side]["qb_named_starter"]:
            out[side]["qb_name"] = out[side]["qb_named_starter"]
    GameNarrative.model_validate(out)
    return out, drops, log


def research_game(paths: Paths, row: dict, *, model: str = MODEL, store: bool = True, now: datetime | None = None, run=subprocess.run, fetcher: Fetcher | None = None, base: GameNarrative | None = None) -> ClaudeRun:  # fmt: skip
    """One game's session and what code stores of it. With `base` (the game's latest record) it is
    the late-status pass: a short status-only session merged onto a copy of `base`."""
    g = Game.from_slate(row)
    now = now or now_utc()
    out = ClaudeRun(g.game_id)
    keep = runs_dir(paths, g.season, g.week) / f"{g.game_id}_{'status_' if base else ''}{snapshot_ts(now)}"  # fmt: skip
    fname = "status.json" if base else "record.json"
    work = Path(tempfile.mkdtemp(prefix=f"nfl-narrative-{g.game_id}-"))
    out.folder = keep
    t0 = time.monotonic()
    try:
        prompt = prepare(paths, row, work, model, now, base=base)
        (work / "prompt.txt").write_text(prompt)
        res = call(work, prompt, model, run=run)
        rec_path = work / fname
        record, err = None, None
        for attempt in range(2):
            try:
                if not rec_path.exists():
                    raise ValueError(f"no {fname} was written")
                fetch = fetcher or Fetcher(paths, use_cache=False, max_chars=200_000)
                raw = json.loads(rec_path.read_text())
                record, drops, log = (check_status(paths, raw, base, work, fetch, now_utc()) if base else check_record(paths, raw, work, fetch, now_utc()))  # fmt: skip
                err = None
                break
            except Exception as e:  # noqa: BLE001  (schema or JSON errors: one repair turn)
                err = f"{type(e).__name__}: {str(e)[:500]}"
                if attempt or not res.get("session_id"):
                    break
                res2 = call(work, f"Code could not use {fname}: {err}\nFix {fname} (only what the error names), then reply with one line.", model, resume=res["session_id"], run=run)  # fmt: skip
                res = {**res2, "_seconds": res.get("_seconds", 0) + res2.get("_seconds", 0),
                       "num_turns": (res.get("num_turns") or 0) + (res2.get("num_turns") or 0)}  # fmt: skip
        out.turns = res.get("num_turns") or 0
        out.api_equiv_usd = res.get("total_cost_usd")  # cumulative for a resumed session
        out.usage = res.get("usage") or {}
        opened, queries = provenance(work)
        out.pages, out.searches = len(opened), len(queries)
        if res.get("_rc") not in (0, None) and record is None:
            raise RuntimeError(f"claude -p exited {res.get('_rc')}: {str(res.get('result') or err or '')[:300]}")  # fmt: skip
        if record is None:
            raise RuntimeError(err or "no record")
        out.dropped = Counter({k: v for k, v in drops.items() if not k.startswith("flag ")})
        out.flags = Counter({k: v for k, v in drops.items() if k.startswith("flag ")})
        (work / "record.checked.json").write_text(json.dumps(record, indent=1, default=str))
        (work / "drops.json").write_text(json.dumps([list(x) for x in log], indent=1, default=str))
        if store:
            out.stored = ingest(paths, work / "record.checked.json", now=now_utc())
        out.ok = True
    except Exception as e:  # noqa: BLE001  (one game's failure never stops the pass)
        out.error = f"{type(e).__name__}: {str(e)[:400]}"
    finally:
        out.seconds = time.monotonic() - t0
        keep.parent.mkdir(parents=True, exist_ok=True)
        for f in ("context.json", "settings.json", "example.json"):
            (work / f).unlink(missing_ok=True)
        shutil.copytree(work, keep, dirs_exist_ok=True)
        shutil.rmtree(work, ignore_errors=True)
        _log(paths, model, g.game_id, out, status=base is not None)
    return out


def _log(paths: Paths, model: str, game_id: str, r: ClaudeRun, *, status: bool = False) -> None:
    u = r.usage
    append_call(paths, {
        "run_id": r.folder.name if r.folder else game_id, "job": f"{JOB}_status" if status else JOB,
        "model": model, "prompt_version": STATUS_VERSION if status else PROMPT_VERSION, "game_id": game_id, "attempt": 1, "ok": r.ok,
        "error": r.error, "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
        "cache_read_tokens": u.get("cache_read_input_tokens"),
        "cache_write_tokens": u.get("cache_creation_input_tokens"), "energy_wh": None,
        "latency_ms": int(r.seconds * 1000), "ts": now_utc(), "turns": r.turns,
        "searches": r.searches, "pages": r.pages, "dropped": sum(r.dropped.values()),
        "api_equiv_usd": r.api_equiv_usd,
    })  # fmt: skip


# ----------------------------------------------------------------------------- the pass


def run_week(paths: Paths, season: int, week: int, game_ids: list[str] | None = None, *, model: str = MODEL, parallel: int = PARALLEL, store: bool = True, run=subprocess.run, login=require_subscription_login) -> list[ClaudeRun]:  # fmt: skip
    """Research the week's games. Without `game_ids` this is a pass: games under way and games
    already stored since the pass began are skipped, so rerunning a failed pass resumes it."""
    from nfl.llm.narrative import last_pass, slate, stored_since

    plan = login()
    print(f"claude login ok (plan {plan}); model {model}", flush=True)
    rows = slate(paths, season, week).to_dicts()
    if game_ids:
        unknown = set(game_ids) - {r["game_id"] for r in rows}
        if unknown:
            raise ValueError(f"not in {season} week {week}: {sorted(unknown)}")
        rows = [r for r in rows if r["game_id"] in game_ids]
    else:
        now = now_utc().replace(tzinfo=None)
        done = stored_since(paths, season, week, last_pass(now)) if store else set()
        rows = [r for r in rows if r["kickoff_utc"] > now and r["game_id"] not in done]
        if done:
            print(f"resuming: {len(done)} games already stored in this pass", flush=True)

    def one(r: dict) -> ClaudeRun:
        x = research_game(paths, r, model=model, store=store, run=run)
        print(f"{x.game_id}: {'stored' if x.stored else 'ok' if x.ok else x.error} "
              f"({x.seconds / 60:.1f} min, {x.pages} pages, {sum(x.dropped.values())} dropped)", flush=True)  # fmt: skip
        return x

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        return list(ex.map(one, rows))


def latest_full_records(paths: Paths, season: int, week: int) -> dict[str, GameNarrative]:
    """game_id -> the game's newest stored `claude_max` record of the week (a status record is the
    newest once one exists: it carries the full record's fields forward)."""
    from nfl.llm.narrative import load_records

    out: dict[str, GameNarrative] = {}
    for r in sorted(load_records(paths, (season, season)), key=lambda r: r.known_as_of):
        if r.week == week and r.producer == PRODUCER:
            out[r.game_id] = r
    return out


def run_status(paths: Paths, season: int, week: int, game_ids: list[str] | None = None, *, model: str = MODEL, parallel: int = PARALLEL, store: bool = True, run=subprocess.run, login=require_subscription_login) -> list[ClaudeRun]:  # fmt: skip
    """The late-status pass: for games of the week that already have a stored `claude_max` record
    and haven't kicked off, a short status-only session merged onto a copy of the latest record
    (`check_status`). Without `game_ids` it is a pass: games a status pass already stored since the
    last scheduled one (`STATUS_PASSES`) are skipped, so a rerun resumes it. A game with no record
    is skipped, never researched in full here."""
    from nfl.llm.narrative import last_pass, slate, stored_since

    plan = login()
    print(f"claude login ok (plan {plan}); model {model}; status only", flush=True)
    rows = slate(paths, season, week).to_dicts()
    have = latest_full_records(paths, season, week)
    now = now_utc().replace(tzinfo=None)
    if game_ids:
        unknown = set(game_ids) - {r["game_id"] for r in rows}
        if unknown:
            raise ValueError(f"not in {season} week {week}: {sorted(unknown)}")
        rows = [r for r in rows if r["game_id"] in game_ids]
    else:
        done = stored_since(paths, season, week, last_pass(now, STATUS_PASSES), "status") if store else set()  # fmt: skip
        rows = [r for r in rows if r["kickoff_utc"] > now and r["game_id"] not in done]
        if done:
            print(f"resuming: {len(done)} games already status-checked in this pass", flush=True)
    skipped = [r["game_id"] for r in rows if r["game_id"] not in have]
    rows = [r for r in rows if r["game_id"] in have]
    if skipped:
        print(f"no stored record, skipped: {', '.join(skipped)}", flush=True)

    def one(r: dict) -> ClaudeRun:
        x = research_game(paths, r, model=model, store=store, run=run, base=have[r["game_id"]])
        print(f"{x.game_id}: {'stored' if x.stored else 'ok' if x.ok else x.error} "
              f"({x.seconds / 60:.1f} min, {x.pages} pages, {sum(x.dropped.values())} dropped)", flush=True)  # fmt: skip
        return x

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        return list(ex.map(one, rows))


def summarize(runs: list[ClaudeRun]) -> dict[str, Any]:
    drops: Counter = Counter()
    for r in runs:
        drops.update(r.dropped)
    return {
        "games": len(runs), "ok": sum(r.ok for r in runs),
        "minutes": round(sum(r.seconds for r in runs) / 60, 1),
        "api_equiv_usd": round(sum(r.api_equiv_usd or 0 for r in runs), 2),
        "dropped": dict(drops.most_common()),
    }  # fmt: skip
