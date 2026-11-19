"""Narrative research on headless Claude Code (ADR 0030): the checks code runs on a record, the
transcript parsing, the login guard and one game end to end with a fake `claude`."""

import json
import subprocess
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from nfl.config import Paths
from nfl.llm import checks
from nfl.llm import claude_research as cr
from nfl.llm.client import read_calls
from nfl.llm.fetch import Page
from nfl.llm.narrative import example, load_records

KICK = datetime(2026, 11, 1, 18, 0)
NOW = datetime(2026, 10, 28, 20, 0, tzinfo=UTC)
URL_A = "https://www.example.com/a"
URL_B = "https://www.example.com/b"


def _games(tmp_path) -> Paths:
    """BUF and BAL both 2-1 before the Week 8 game (BAL went 1-0, 1-1, 2-1), plus the game."""
    rows = {
        "game_id": ["2026_01_BUF_MIA", "2026_02_NYJ_BUF", "2026_03_BUF_NE", "2026_01_BAL_CIN",
                    "2026_02_PIT_BAL", "2026_03_BAL_CLE", "2026_08_BAL_BUF"],
        "season": [2026] * 7, "week": [1, 2, 3, 1, 2, 3, 8], "game_type": ["REG"] * 7,
        "home_team": ["MIA", "BUF", "NE", "CIN", "BAL", "CLE", "BUF"],
        "away_team": ["BUF", "NYJ", "BUF", "BAL", "PIT", "BAL", "BAL"],
        "result": [-7, 3, 10, -3, -4, -6, None],
        "kickoff_utc": [datetime(2026, 9, d, 17) for d in (13, 20, 27)] * 2 + [KICK],
    }  # fmt: skip
    d = tmp_path / "curated" / "games" / "season=2026"
    d.mkdir(parents=True)
    pl.DataFrame(rows).with_columns(pl.lit("s").alias("raw_snapshot_ts")).write_parquet(d / "g.parquet")  # fmt: skip
    r = tmp_path / "curated" / "rosters_weekly" / "season=2026"
    r.mkdir(parents=True)
    roster = {
        "team": ["BUF", "BUF", "BAL", "BAL", "ARI", "NYG"],
        "full_name": ["Josh Allen", "Example Receiver", "Lamar Jackson", "Jacoby Brissett", "Old Teammate", "Daron Payne"],
        "football_name": ["Josh", "Example", "Lamar", "Jacoby", "Old", "Daron"],
        "last_name": ["Allen", "Receiver", "Jackson", "Brissett", "Teammate", "Payne"],
        "position": ["QB", "WR", "QB", "QB", "WR", "DT"], "status": ["ACT"] * 6, "week": [7] * 6,
    }  # fmt: skip
    pl.DataFrame(roster).write_parquet(r / "r.parquet")
    return Paths(tmp_path)


def _ctx(paths: Paths, **over) -> checks.Context:
    from nfl.features.store import games_frame

    kw = {
        "home": "BUF", "away": "BAL", "roster": checks.roster_index(paths, 2026, 8),
        "records": checks.season_records(games_frame(paths), 2026, ("BUF", "BAL"), KICK),
        "games_played": 3, "opened": {checks.norm_url(URL_A), checks.norm_url(URL_B)},
        "known_as_of": date(2026, 10, 28), "window_days": 10,
    }  # fmt: skip
    kw.update(over)
    return checks.Context(**kw)


def _record() -> dict:
    r = example()
    r["claims"] = [
        {"claim": "Jacoby Brissett will start for Baltimore after the trade.", "category": "qb",
         "team": "BAL", "source_url": URL_A, "published_at": "2026-10-27", "confidence": "high"},
    ]  # fmt: skip
    r["home"]["notes"][0]["source_url"] = URL_A
    r["home"]["scheme_trends"][0]["sources"] = [URL_A]
    r["matchup_notes"][0]["sources"] = [URL_A, URL_B]
    return r


# ---------------------------------------------------------------------------------- checks


def test_records_include_every_record_either_team_had(tmp_path):
    ctx = _ctx(_games(tmp_path))
    assert ctx.records == {"0-0", "1-0", "2-0", "1-1", "2-1", "1-0-0", "2-0-0", "1-1-0", "2-1-0"}
    assert (
        checks.bad_record("Buffalo is 2-1 after a 24-21 win.", ctx) is None
    )  # score: too many games
    assert checks.bad_record("Baltimore is 0-4 at home.", ctx) is None  # a split
    assert checks.bad_record("Baltimore is 2-1.", ctx) is None  # BUF's record: either team's passes
    assert checks.bad_record("Baltimore sits at 0-3.", ctx) == "0-3"


def test_a_traded_player_never_stays_on_his_old_team(tmp_path):
    ctx = _ctx(_games(tmp_path))
    r = _record()
    r["home"]["key_absences"] = ["Josh Allen (QB, out)", "Lamar Jackson (QB, out)"]
    r["away"]["key_absences"] = ["Daron Payne (DT, out)"]  # NYG's: the Week 10 WAS/NYG error
    r["away"]["summary"] = "Baltimore faces Josh Allen this week. Old Teammate was traded away."
    r["away"]["qb_name"] = "Josh Allen"
    out, drops, _ = checks.apply(r, ctx)
    assert out["home"]["key_absences"] == ["Josh Allen (QB, out)"]
    assert out["away"]["key_absences"] == []
    # the opponent's QB may be named in a summary; a third team's player may not
    assert out["away"]["summary"] == "Baltimore faces Josh Allen this week."
    assert out["away"]["qb_name"] is None and out["away"]["qb_status"] == 2
    assert drops["absence: team"] == 2 and drops["sentence: team"] == 1 and drops["qb: team"] == 1


def test_only_pages_opened_in_the_run_and_inside_the_window(tmp_path):
    paths = _games(tmp_path)
    r = _record()
    r["claims"].append({"claim": "An unopened page says something about Buffalo here.", "category": "form",
                        "team": "BUF", "source_url": "https://other.example.org/x", "published_at": "2026-10-27", "confidence": "high"})  # fmt: skip
    r["claims"].append({"claim": "A stale page says something about Buffalo here.", "category": "form",
                        "team": "BUF", "source_url": URL_B, "published_at": "2026-10-27", "confidence": "high"})  # fmt: skip
    stale = Page(URL_B, URL_B, "t", "text", date(2026, 10, 1), NOW, 200, True, None)
    out, drops, _ = checks.apply(r, _ctx(paths, pages={URL_B: stale}))
    assert [c["source_url"] for c in out["claims"]] == [URL_A]
    assert drops["claim: not opened"] == 1 and drops["claim: outside window"] == 1
    assert out["matchup_notes"][0]["sources"] == [URL_A] and out["matchup_notes"][0]["support"] == 1


def test_code_dates_win_and_the_line_stays_out_of_text(tmp_path):
    paths = _games(tmp_path)
    r = _record()
    r["home"]["notes"][0]["text"] = "Buffalo is favored by three at home this week."
    r["claims"].append({"claim": "The line opened at Buffalo -3.5 and moved to -2.5.", "category": "public",
                        "team": None, "source_url": URL_A, "published_at": "2026-10-20", "confidence": "high"})  # fmt: skip
    page = Page(URL_A, URL_A, "t", "Jacoby Brissett will start. The line opened at Buffalo -3.5 and moved to -2.5.", date(2026, 10, 26), NOW, 200, True, None)  # fmt: skip
    out, drops, _ = checks.apply(r, _ctx(paths, pages={URL_A: page}))
    assert out["home"]["notes"] == [] and drops["note: line"] == 1
    assert len(out["claims"]) == 2  # a public claim may state the line
    assert all(c["published_at"] == "2026-10-26" for c in out["claims"])


def test_text_not_on_its_page_is_flagged_not_dropped(tmp_path):
    paths = _games(tmp_path)
    r = _record()
    page = Page(URL_A, URL_A, "t", "Jacoby Brissett will start for Baltimore after the trade.", date(2026, 10, 26), NOW, 200, True, None)  # fmt: skip
    r["claims"][0]["claim"] = "Jacoby Brissett will start for Baltimore after a 41-yard day."
    out, drops, log = checks.apply(r, _ctx(paths, pages={URL_A: page}))
    assert len(out["claims"]) == 1 and drops["flag claim: not on page"] == 1
    assert log[0][0] == "flag claim"
    out, drops, _ = checks.apply(_record() | {"claims": r["claims"]}, _ctx(paths, pages={URL_A: page}, on_page_drops=True))  # fmt: skip
    assert out["claims"] == [] and drops["claim: not on page"] == 1


# --------------------------------------------------------------------- transcript and login


def _transcript(folder: Path, urls: list[str], queries: list[str], result: dict | None = None) -> None:  # fmt: skip
    ev = [{"type": "system", "subtype": "init"}]
    for q in queries:
        ev.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "WebSearch", "input": {"query": q}}]}})  # fmt: skip
    for u in urls:
        ev.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "WebFetch", "input": {"url": u, "prompt": "x"}}]}})  # fmt: skip
        ev.append({"type": "user", "message": {"content": [{"type": "tool_result", "content": "page text"}]}})  # fmt: skip
    ev.append({"type": "user", "message": "a plain string message"})
    ev.append({"type": "result", "subtype": "success", "session_id": "s1", "num_turns": 9,
               "total_cost_usd": 0.6, "usage": {"input_tokens": 10, "output_tokens": 900}, **(result or {})})  # fmt: skip
    with (folder / "transcript.jsonl").open("w") as f:
        f.write("not json\n")
        for e in ev:
            f.write(json.dumps(e) + "\n")


def test_provenance_reads_fetches_and_searches(tmp_path):
    _transcript(tmp_path, ["https://www.example.com/a/", URL_B], ["q1", "q2"])
    opened, queries = cr.provenance(tmp_path)
    assert opened == {"example.com/a", "example.com/b"} and queries == ["q1", "q2"]


@pytest.mark.parametrize(
    ("status", "msg"),
    [
        ({"loggedIn": False}, "not logged in"),
        ({"loggedIn": True, "authMethod": "api_key"}, "api_key"),
    ],
)
def test_login_must_be_the_claude_ai_subscription(status, msg):
    def run(cmd, **kw):
        assert "ANTHROPIC_API_KEY" not in kw["env"]
        return subprocess.CompletedProcess(cmd, 0, json.dumps(status), "")

    with pytest.raises(cr.LoginError, match=msg):
        cr.require_subscription_login(run)
    ok = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}
    assert cr.require_subscription_login(lambda c, **k: subprocess.CompletedProcess(c, 0, json.dumps(ok), "")) == "max"  # fmt: skip


def test_the_session_is_locked_down(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-pass")
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["env"], seen["cwd"] = cmd, kw["env"], kw["cwd"]
        _transcript(Path(kw["cwd"]), [], [])
        return subprocess.CompletedProcess(cmd, 0)

    (tmp_path / "settings.json").write_text("{}")
    cr.call(tmp_path, "prompt", "sonnet", run=run)
    cmd = seen["cmd"]
    assert "ANTHROPIC_API_KEY" not in seen["env"]
    assert cmd[cmd.index("--tools") + 1] == "WebSearch,WebFetch,Read,Write,Edit"
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert cmd[cmd.index("--setting-sources") + 1] == "" and "--strict-mcp-config" in cmd


# ------------------------------------------------------------------------ one game, faked


class _Pages:
    def get(self, url):
        return Page(url, url, "t", "Jacoby Brissett will start for Baltimore after the trade.", date(2026, 10, 27), NOW, 200, True, None)  # fmt: skip


def _row() -> dict:
    return {"game_id": "2026_08_BAL_BUF", "kickoff_utc": KICK, "home_team": "BUF", "away_team": "BAL",
            "roof": "outdoors", "stadium": "Highmark", "home_qb_name": "Josh Allen",
            "away_qb_name": "Jacoby Brissett", "home_coach": "H", "away_coach": "A"}  # fmt: skip


def test_one_game_end_to_end_with_a_repair_turn(tmp_path, monkeypatch):
    paths = _games(tmp_path)
    monkeypatch.setattr(cr, "now_utc", lambda: NOW)
    calls = []

    def fake_claude(cmd, **kw):
        folder = Path(kw["cwd"])
        calls.append(cmd)
        assert "Jacoby Brissett (QB, ACT)" in (folder / "context.json").read_text()
        rec = _record()
        if "--resume" not in cmd:
            rec["upset_buzz"] = 7  # out of range: the repair turn fixes it
            _transcript(folder, [URL_A, URL_B], ["Ravens QB week 8"])
        else:
            with (folder / "transcript1.jsonl").open("w") as f:
                f.write(json.dumps({"type": "result", "num_turns": 2, "total_cost_usd": 0.7, "usage": {"output_tokens": 50}}) + "\n")  # fmt: skip
        (folder / "record.json").write_text(json.dumps(rec))
        return subprocess.CompletedProcess(cmd, 0)

    run = cr.research_game(paths, _row(), store=True, run=fake_claude, fetcher=_Pages(), now=NOW)
    assert run.ok and run.stored and len(calls) == 2 and "--resume" in calls[1]
    assert run.pages == 2 and run.searches == 1 and run.api_equiv_usd == 0.7 and run.turns == 11
    stored = load_records(paths)
    assert [r.producer for r in stored] == ["claude_max"] and stored[
        0
    ].prompt_version == "claude_v1"
    assert stored[0].searches == ["Ravens QB week 8"]
    kept = list(cr.runs_dir(paths, 2026, 8).glob("2026_08_BAL_BUF_*"))
    assert kept and (kept[0] / "record.checked.json").exists() and not (kept[0] / "settings.json").exists()  # fmt: skip
    log = read_calls(paths)
    assert (
        log.row(-1, named=True)["job"] == "research_claude"
        and log.row(-1, named=True)["pages"] == 2
    )


def test_a_failed_game_is_logged_and_never_stored(tmp_path, monkeypatch):
    paths = _games(tmp_path)
    monkeypatch.setattr(cr, "now_utc", lambda: NOW)

    def no_record(cmd, **kw):
        _transcript(Path(kw["cwd"]), [], [], {"session_id": None})
        return subprocess.CompletedProcess(cmd, 1)

    run = cr.research_game(paths, _row(), run=no_record, fetcher=_Pages(), now=NOW)
    assert not run.ok and "exited 1: ValueError: no record.json" in run.error
    assert load_records(paths) == []
    assert read_calls(paths).row(-1, named=True)["ok"] is False


def test_summarize_counts_drops():
    a, b = (
        cr.ClaudeRun("g1", ok=True, seconds=120, api_equiv_usd=0.5),
        cr.ClaudeRun("g2", seconds=60),
    )
    a.dropped = Counter({"claim: team": 2})
    assert cr.summarize([a, b]) == {"games": 2, "ok": 1, "minutes": 3.0, "api_equiv_usd": 0.5, "dropped": {"claim: team": 2}}  # fmt: skip


def test_the_pre_lock_check_counts_claude_records(tmp_path):
    from nfl.llm import narrative as nar

    paths = _games(tmp_path)
    d = example() | {"producer": "claude_max", "prompt_version": "claude_v1"}
    f = tmp_path / "r.json"
    f.write_text(json.dumps(d))
    nar.ingest(paths, f, now=datetime(2026, 10, 30, 12, 0))
    assert nar.stored_since(paths, 2026, 8, datetime(2026, 10, 29)) == {"2026_08_BAL_BUF"}
    d["producer"] = "claude_code"  # the skill's records are development only
    f.write_text(json.dumps(d))
    nar.ingest(paths, f, now=datetime(2026, 10, 30, 13, 0))
    assert nar.stored_since(paths, 2026, 8, datetime(2026, 10, 30, 12, 30)) == set()


def test_the_call_log_reads_files_written_before_the_new_columns(tmp_path):
    from nfl.llm.client import LOG_SCHEMA, append_call, calls_path

    paths = Paths(tmp_path)
    old = {k: v for k, v in LOG_SCHEMA.items() if k not in ("turns", "api_equiv_usd", "pages")}
    calls_path(paths).parent.mkdir(parents=True)
    pl.DataFrame([{"run_id": "r0", "job": "extract", "ok": True}], schema=old).write_parquet(calls_path(paths))  # fmt: skip
    append_call(paths, {"run_id": "r1", "job": "research_claude", "ok": True, "turns": 20, "api_equiv_usd": 0.6})  # fmt: skip
    log = read_calls(paths)
    assert log.columns == list(LOG_SCHEMA) and log["turns"].to_list() == [None, 20]
