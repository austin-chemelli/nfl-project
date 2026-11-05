"""Local narrative research: every URL comes from a fetched page, ids map back, unsupported numbers
and percentages are dropped, the date window holds (stub search, pages and LLM server). v2: status
facts deduped and capped, analysis reaches the prompts, every sentence is grounded."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta

import httpx
import polars as pl

from nfl.config import Paths
from nfl.llm import research
from nfl.llm.client import LLMClient, LLMConfig
from nfl.llm.fetch import Page
from nfl.llm.narrative import GameNarrative
from nfl.llm.research import (
    BLOCK_WAIT_MAX_S,
    BLOCK_WAIT_S,
    FACT_REF,
    LINE,
    MAX_STATUS_FACTS,
    Doc,
    Fact,
    Game,
    GameRun,
    SearchReuse,
    Sources,
    _aliases,
    _facts_for,
    _mispaired,
    _players,
    _unsupported,
    _whole,
    _wrong_team,
    gather,
    queries,
    research_game,
    run_week,
)
from nfl.llm.search import EnginesBlocked, SearchResult

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
GAME = Game(
    game_id="2026_08_BAL_BUF", season=2026, week=8, home="BUF", away="BAL",
    kickoff_utc=datetime(2026, 11, 1, 18, 0), roof="outdoors", stadium="Highmark Stadium",
    home_qb="Josh Allen", away_qb="Lamar Jackson",
)  # fmt: skip

TEXT = "Long enough article text about the game. " * 20
PAGES = {
    "https://www.espn.com/bal": (date(2026, 10, 29), "injury"),
    "https://buffalonews.com/a": (date(2026, 10, 28), "matchup"),
    "https://www.cbssports.com/b": (date(2026, 10, 27), "matchup"),
    "https://old.example.com/x": (date(2026, 9, 1), "stale"),
    "https://undated.example.com/y": (None, "undated"),
    "https://www.covers.com/consensus": (None, "betting"),
}


def _search(q: str, max_results: int = 8) -> list[SearchResult]:
    def res(u):
        return SearchResult(u, "t", "s", None, ("x",))

    if "public betting" in q:
        return [res("https://www.covers.com/consensus")]
    if "injury report" in q and "Baltimore" in q:
        urls = ["https://old.example.com/x", "https://undated.example.com/y"]
        return [res(u) for u in urls + ["https://www.espn.com/bal"]]
    if "preview" in q and "betting" not in q:
        return [res("https://buffalonews.com/a"), res("https://www.cbssports.com/b")]
    return []


class _Fetcher:
    def get(self, url: str) -> Page:
        pub, _ = PAGES[url]
        return Page(url, url, "title", TEXT, pub, NOW, 200, True, None)


FACTS = {  # by page: what the stub model "extracts"
    "https://www.espn.com/bal": [
        {
            "text": "BAL left tackle Ronnie Stanley is out with an ankle injury.",
            "category": "injury",
            "team": "BAL",
            "player": "Ronnie Stanley",
            "confidence": "high",
        },
    ],
    "https://buffalonews.com/a": [
        {
            "text": "Analysts expect the Bills pass rush to exploit the BAL backup tackle.",
            "category": "matchup",
            "team": "game",
            "player": None,
            "confidence": "medium",
        },
    ],
    "https://www.cbssports.com/b": [
        {
            "text": "Preview says the Bills pass rush has the edge over a reshuffled BAL line.",
            "category": "matchup",
            "team": "game",
            "player": None,
            "confidence": "medium",
        },
        {
            "text": "Lamar Jackson is cleared to start after missing three games.",
            "category": "qb",
            "team": "BAL",
            "player": "Lamar Jackson",
            "confidence": "high",
        },
    ],
    "https://www.covers.com/consensus": [
        {
            "text": "Consensus shows 64% of bets on the Bills.",
            "category": "public",
            "team": "game",
            "player": None,
            "confidence": "high",
        },
    ],
}


QB_REPLY = {"qb_name": "Lamar Jackson", "qb_status": 1, "fact_ids": ["F5"]}
MATCHUPS = [
    {"kind": "unit", "offense_team": "BAL", "defense_team": "BUF", "edge": "defense",
     "text": "Bills pass rush against a backup tackle.", "fact_ids": ["F2", "Fact 4"]},
    {"kind": "game", "offense_team": None, "defense_team": None, "edge": None,
     "text": "Baltimore is missing its starting left tackle.", "fact_ids": ["F1"]},
]  # fmt: skip


def _team(f_ids_ok: list[str]) -> dict:
    return {
        "notes": [
            {"text": "Starting left tackle is out; a backup starts.", "kind": "injury", "impact": -2, "fact_ids": f_ids_ok},
            {"text": "Line has allowed 12 sacks in three games.", "kind": "form", "impact": -1, "fact_ids": f_ids_ok},
            {"text": "Note citing a fact id that doesn't exist.", "kind": "other", "impact": 0, "fact_ids": ["F99"]},
            {"text": "Ronnie Stanley is out with an ankle injury.", "kind": "injury", "impact": -2, "fact_ids": ["F3"]},
        ],
        "scheme_trends": [],
        "key_absences": ["Ronnie Stanley (OT, Out)"],
        "injury_impact": 2, "sentiment": 0.0,
        "hype": 0.5, "coaching_turmoil": 0.0, "motivation": 0.3, "revenge": False,
        "lookahead": False,
        "summary": [
            {"text": "The team is missing its starting left tackle this week.", "fact_ids": f_ids_ok},
            {"text": "He has a history of back issues.", "fact_ids": f_ids_ok},
        ],
    }  # fmt: skip


THINK_RUNS_OUT = False  # thinking calls hit max_tokens
MISSING_MODEL = ""  # a model the stub server doesn't have (HTTP 404)


def _llm(seen: list[dict]):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body)
        if body["model"] == MISSING_MODEL:
            return httpx.Response(404, json={"error": f"model '{MISSING_MODEL}' not found"})
        name = body["response_format"]["json_schema"]["name"]
        if name == "PageFacts":
            text = body["messages"][-1]["content"]
            doc_url = next((u for u in FACTS if f"({_dom(u)}," in text), None)
            out = {"facts": FACTS.get(doc_url, [])}
        elif name == "QbOut":
            out = QB_REPLY
        elif name == "NotesOut":
            out = {k: v for k, v in _team(["F1"]).items() if k not in ("summary", "scheme_trends")}
        elif name == "TrendsOut":
            out = {"scheme_trends": []}
        elif name == "SummaryOut":
            out = {"summary": _team(["F1"])["summary"]}
        elif name == "MatchupsOut":
            out = {"matchup_notes": MATCHUPS}
        else:
            out = {
                "consensus": [
                    {"text": "Buffalo hosts a Baltimore team missing its left tackle.", "fact_ids": ["F2"]},
                    {"text": "Both teams sit atop the AFC North.", "fact_ids": ["F2"]},
                ],
                "public_pick": "home", "public_bet_pct_home": 0.64, "public_bet_fact_id": "[F3]",
                "upset_buzz": 0.2, "weather_concern": 0.3,
            }  # fmt: skip
        stop = "length" if THINK_RUNS_OUT and body["reasoning_effort"] != "none" else "stop"
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "choices": [{"message": {"content": json.dumps(out)}, "finish_reason": stop}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    return handler


def _dom(url: str) -> str:
    host = url.split("//")[1].split("/")[0]
    return host.removeprefix("www.")


def _run(tmp_path):
    seen: list[dict] = []
    http = httpx.Client(transport=httpx.MockTransport(_llm(seen)))
    client = LLMClient(Paths(tmp_path), LLMConfig(base_url="http://desk/v1"), http=http)
    run = research_game(
        Paths(tmp_path), GAME, client, _Fetcher(), store=False, now=NOW, search_fn=_search
    )
    drafts = sorted((tmp_path / "raw" / "narrative_local").rglob("*_2026*Z.json"))
    rec = json.loads(drafts[-1].read_text()) if drafts else None
    return run, rec, seen


def test_record_is_valid_and_every_url_was_fetched(tmp_path):
    run, rec, _ = _run(tmp_path)
    assert run.ok, run.error
    GameNarrative.model_validate(rec)
    fetched = {u for u, (pub, kind) in PAGES.items() if kind not in ("stale", "undated")}
    urls = [c["source_url"] for c in rec["claims"]]
    for side in ("home", "away"):
        urls += [n["source_url"] for n in rec[side]["notes"]]
        urls += [u for t in rec[side]["scheme_trends"] for u in t["sources"]]
    urls += [u for m in rec["matchup_notes"] for u in m["sources"]]
    assert urls and set(urls) <= fetched
    assert rec["producer"] == "local" and rec["model"] == "qwen3.5:9b + qwen3:14b (matchup)"


def test_date_window_and_undated_policy(tmp_path):
    run, rec, _ = _run(tmp_path)
    assert run.pages["dropped: outside date window"] == 1
    assert run.pages["dropped: undated"] == 1
    bet = next(c for c in rec["claims"] if c["category"] == "public")
    assert bet["published_at"] is None and bet["confidence"] == "low"  # undated betting page kept


def test_ids_map_to_sources_and_support_counts_domains(tmp_path):
    run, rec, _ = _run(tmp_path)
    m = rec["matchup_notes"][0]
    assert (
        m["support"] == 2 and len(m["sources"]) == 2
    )  # F2 and "Fact 4": two sites (pages are picked round-robin)
    assert rec["public_bet_pct_home"] == 0.64  # F3 (the betting page) states a percentage
    notes = rec["home"]["notes"]
    assert [n["text"] for n in notes] == ["Starting left tackle is out; a backup starts."]
    assert notes[0]["source_url"] == "https://www.espn.com/bal"
    # Stanley's note cites F3 (the betting page): re-cited to F1 in the BAL block; the BUF block
    # may only borrow BUF or game facts, so there it's dropped.
    away = rec["away"]["notes"]
    assert away[1]["text"] == "Ronnie Stanley is out with an ankle injury."
    assert away[1]["source_url"] == "https://www.espn.com/bal"
    assert run.recited["note"] == 1
    assert run.dropped["note with an unsupported name"] == 1
    assert run.dropped["note with an unsupported number"] == 2  # "12 sacks", once per team
    assert run.dropped["note without a valid fact"] == 2


def test_every_sentence_is_grounded(tmp_path):
    run, rec, _ = _run(tmp_path)
    # "back issues" and the "AFC North" are in no cited fact: those sentences go.
    assert rec["home"]["summary"] == "The team is missing its starting left tackle this week."
    assert run.dropped["summary sentence with an unsupported condition"] == 2
    assert rec["consensus_narrative"] == "Buffalo hosts a Baltimore team missing its left tackle."
    assert run.dropped["consensus sentence with an unsupported name"] == 1
    # an injury fact alone doesn't make a matchup note
    assert [m["text"] for m in rec["matchup_notes"]] == ["Bills pass rush against a backup tackle."]
    assert run.dropped["matchup note without a matchup or scheme fact"] == 1


def test_claims_rotate_categories(tmp_path):
    _, rec, _ = _run(tmp_path)
    assert [c["category"] for c in rec["claims"]][:4] == ["injury", "qb", "matchup", "public"]


def test_qb_is_its_own_checked_call(tmp_path, monkeypatch):
    run, rec, seen = _run(tmp_path)
    qb_calls = [b for b in seen if b["response_format"]["json_schema"]["name"] == "QbOut"]
    assert len(qb_calls) == 1  # BUF has no QB facts: no call, the schedule's starter
    assert "F5 [qb, BAL]" in qb_calls[0]["messages"][0]["content"]
    assert (rec["away"]["qb_name"], rec["away"]["qb_status"]) == ("Lamar Jackson", 1)
    assert (rec["home"]["qb_name"], rec["home"]["qb_status"]) == ("Josh Allen", 0)
    assert any("BUF: no quarterback facts" in w for w in run.warnings)
    # a pick that is neither the schedule's starter nor named in its facts becomes undecided
    monkeypatch.setitem(QB_REPLY, "qb_name", "Tyler Huntley")
    run, rec, _ = _run(tmp_path)
    assert (rec["away"]["qb_name"], rec["away"]["qb_status"]) == (None, 2)
    assert run.dropped["qb pick not named in its facts"] == 1


def _fact(n: int, category: str, player: str | None, day: int, conf: str = "high", team: str = "BAL") -> Fact:  # fmt: skip
    doc = Doc(f"D{n}", f"https://x.com/{n}", "t", "x.com", date(2026, 10, day), "news", "")
    return Fact(f"F{n}", doc, f"fact {n}", category, team, conf, player)


def test_status_facts_are_deduped_and_capped():
    facts = [_fact(i, "injury", f"Player {i}", 20) for i in range(1, 31)]  # 30 players
    facts += [_fact(31 + i, "injury", "Lamar Jackson", 20 + i) for i in range(4)]  # 4 reports
    facts += [_fact(40 + i, "scheme", None, 25, "medium") for i in range(10)]
    team = _facts_for(facts, "BAL")
    status = [f for f in team if f.category == "injury"]
    assert len(status) == MAX_STATUS_FACTS
    assert {f.id for f in facts[-10:]} <= {f.id for f in team}  # every scheme fact gets in
    lamar = [f.id for f in facts if f.player == "Lamar Jackson"]
    kept = [f.id for f in team if f.player == "Lamar Jackson"]
    assert kept == lamar[-2:]  # the two newest reports
    game = _facts_for(facts, None)
    assert {f.category for f in game} == {"scheme"}


def test_unsupported_checks_numbers_names_and_conditions():
    src = "Lamar Jackson returns from a high ankle sprain. James Cook ran for 120 yards."
    assert _unsupported("Quarterback Lamar Jackson is back from his ankle sprain.", src) is None
    assert _unsupported("Running back James Cook ran for 120 yards.", src) is None
    assert _unsupported("Lamar Jackson's ankle is fine.", src) is None
    assert _unsupported("James Cook ran for 130 yards.", src) == "number"
    assert _unsupported("Josh Allen will start.", src) == "name"
    assert _unsupported("Lamar Jackson has a back injury.", src) == "condition"
    assert _unsupported("Lamar Jackson tweaked his knee.", src) == "condition"
    assert (
        _unsupported("They face Josh Allen.", "Josh Allen starts.") is None
    )  # sentence-final period
    assert _unsupported("A back injury.", "The backup starts.") == "condition"  # back is not backup
    assert _unsupported("Caleb Williams' offense leads.", "Caleb Williams starts.") is None
    assert _unsupported("A Monday Night Football game.", "Monday Night Football") is None


def test_recite_combines_two_facts():
    from nfl.llm.research import _recite

    pool = [
        _fact(1, "matchup", None, 25),
        _fact(2, "matchup", None, 25),
        _fact(3, "form", None, 25),
    ]
    pool[0].text, pool[1].text = (
        "Caleb Williams faces the top pass defense.",
        "Jeffery Simmons debuts.",
    )
    got = _recite("Caleb Williams faces it while Jeffery Simmons debuts.", ["F3"], pool, "", ())
    assert [f.id for f in got] == ["F1", "F2"]


def test_public_share_needs_a_percentage_fact(tmp_path, monkeypatch):
    monkeypatch.setitem(
        FACTS,
        "https://www.covers.com/consensus",
        [
            {
                "text": "Most bettors are backing Buffalo this week.",
                "category": "public",
                "team": "game",
                "player": None,
                "confidence": "high",
            }
        ],
    )
    run, rec, _ = _run(tmp_path)
    assert rec["public_bet_pct_home"] is None
    assert run.dropped["public % without a supporting fact"] == 1


def test_extract_prompt_is_per_game_and_thinking_is_off(tmp_path):
    _, _, seen = _run(tmp_path)
    extract = [b for b in seen if b["response_format"]["json_schema"]["name"] == "PageFacts"]
    assert len(extract) == 4  # one call per kept page
    system = extract[0]["messages"][0]["content"]
    assert "Baltimore Ravens (BAL) at Buffalo Bills (BUF)" in system
    team_enum = extract[0]["response_format"]["json_schema"]["schema"]["$defs"]["Fact"][
        "properties"
    ]["team"]
    assert set(team_enum["enum"]) == {"BAL", "BUF", "game"}
    assert all(b["reasoning_effort"] == "none" for b in extract)


def test_started_games_are_refused(tmp_path):
    late = datetime(2026, 11, 1, 19, 0, tzinfo=UTC)
    client = LLMClient(Paths(tmp_path), LLMConfig(base_url="http://desk/v1"), log=False)
    run = research_game(
        Paths(tmp_path), GAME, client, _Fetcher(), store=False, now=late, search_fn=_search
    )
    assert not run.ok and "kicked off" in run.error


def test_open_ended_queries_only():
    assert [k for k, _ in queries(GAME)] == ["qb", "qb", "scheme", "scheme", "matchup", "matchup", "betting"]  # fmt: skip


class _Feeds:
    def __init__(self, team_items):
        self.team_items = team_items

    def pools(self, team, name, today):
        return self.team_items.get(team, {"injury": [], "news": []})


def _item(url):
    return SearchResult(url, "t", "s", date(2026, 10, 29), ("feed",))


def test_feeds_replace_searches_and_an_empty_feed_falls_back():
    feeds = _Feeds({"BAL": {"injury": [_item("https://www.espn.com/bal")], "news": []}})
    sent: list[str] = []

    def spy(q, max_results=8):
        sent.append(q)
        return []

    docs, searches = gather(GAME, _Fetcher(), GameRun(GAME.game_id), NOW, spy, Sources(feeds))
    assert [d.url for d in docs] == ["https://www.espn.com/bal"]
    assert "feed: Baltimore Ravens injury" in searches
    assert "Baltimore Ravens injury report week 8 2026" not in sent
    assert "Buffalo Bills injury report week 8 2026" in sent  # its feed was empty
    assert len(sent) == 3 + len(queries(GAME))


def test_forecast_is_a_page_for_outdoor_games_only():
    wx = lambda stadium, kickoff: ("https://api.open-meteo.com/x", "Forecast: 40 F, wind 9 mph.")
    src = Sources(forecast=wx)
    docs, searches = gather(GAME, _Fetcher(), GameRun(GAME.game_id), NOW, lambda q, max_results=8: [], src)  # fmt: skip
    assert [(d.kind, d.domain) for d in docs] == [("weather", "open-meteo.com")]
    assert "forecast: open-meteo" in searches
    dome = Game(**{**GAME.__dict__, "roof": "dome"})
    assert gather(dome, _Fetcher(), GameRun(GAME.game_id), NOW, lambda q, max_results=8: [], src)[0] == []  # fmt: skip


def test_film_results_are_reused_within_the_week_only(tmp_path):
    reuse = SearchReuse(Paths(tmp_path))
    calls: list[str] = []

    def spy(q, max_results=8):
        calls.append(q)
        return [SearchResult("https://www.espn.com/bal", "t", "s", date(2026, 10, 29), ("x",))]

    def film_calls():
        return [q for q in calls if "film" in q]

    for when in (NOW, NOW + timedelta(days=3)):
        gather(GAME, _Fetcher(), GameRun(GAME.game_id), when, spy, Sources(reuse=reuse))
    assert len(film_calls()) == 2  # two teams, once
    assert sum("status" in q for q in calls) == 4  # the rest ran on both passes
    gather(GAME, _Fetcher(), GameRun(GAME.game_id), NOW + timedelta(days=7), spy, Sources(reuse=reuse))  # fmt: skip
    assert len(film_calls()) == 4


def test_blocked_engines_fail_the_game_without_a_thin_record(tmp_path):
    def blocked(q, max_results=8):
        raise EnginesBlocked("search engines blocked: brave too many requests")

    feeds = _Feeds({"BAL": {"injury": [_item("https://www.espn.com/bal")], "news": []}})
    client = LLMClient(Paths(tmp_path), LLMConfig(base_url="http://desk/v1"), log=False)
    run = research_game(Paths(tmp_path), GAME, client, _Fetcher(), store=False, now=NOW, search_fn=blocked, sources=Sources(feeds))  # fmt: skip
    assert run.blocked and not run.ok and "brave" in run.error


def _week(monkeypatch, results, done=()):
    rows = pl.DataFrame({
        "game_id": ["2026_09_AAA_BBB", "2026_09_CCC_DDD"], "home_team": ["BBB", "DDD"],
        "away_team": ["AAA", "CCC"], "kickoff_utc": [datetime(2099, 1, 1)] * 2,
    })  # fmt: skip
    tried: list[str] = []

    def fake(paths, g, client, fetcher, **kw):
        tried.append(g.game_id)
        return results.pop(0) if results else GameRun(g.game_id, ok=True)

    monkeypatch.setattr("nfl.llm.narrative.slate", lambda *a: rows)
    monkeypatch.setattr("nfl.llm.narrative.stored_since", lambda *a: set(done))
    monkeypatch.setattr("nfl.llm.research.research_game", fake)
    return tried


def test_a_rerun_skips_games_stored_in_this_pass(monkeypatch, tmp_path):
    tried = _week(monkeypatch, [], done=["2026_09_AAA_BBB"])
    runs = run_week(Paths(tmp_path), 2026, 9)
    assert tried == ["2026_09_CCC_DDD"] and all(r.ok for r in runs)


def test_named_games_run_even_if_stored(monkeypatch, tmp_path):
    tried = _week(monkeypatch, [], done=["2026_09_AAA_BBB"])
    run_week(Paths(tmp_path), 2026, 9, ["2026_09_AAA_BBB"])
    assert tried == ["2026_09_AAA_BBB"]


def test_blocked_game_waits_and_retries(monkeypatch, tmp_path):
    blocked = GameRun("2026_09_AAA_BBB", blocked=True, error="EnginesBlocked: x")
    tried = _week(monkeypatch, [blocked])
    waits: list[float] = []
    runs = run_week(Paths(tmp_path), 2026, 9, sleep=waits.append)
    assert waits == [BLOCK_WAIT_S]
    assert tried == ["2026_09_AAA_BBB", "2026_09_AAA_BBB", "2026_09_CCC_DDD"]
    assert all(r.ok for r in runs)


def test_waiting_is_capped_per_pass(monkeypatch, tmp_path):
    many = [GameRun("g", blocked=True, error="EnginesBlocked: x") for _ in range(50)]
    tried = _week(monkeypatch, many)
    waits: list[float] = []
    runs = run_week(Paths(tmp_path), 2026, 9, sleep=waits.append)
    assert sum(waits) == BLOCK_WAIT_MAX_S
    assert len(tried) == len(waits) + 2  # after the cap each game is tried once more
    assert [r.ok for r in runs] == [False, False]


def test_line_statements_are_recognized():
    for text in (
        "The Bears are favored by three points.",
        "Chicago is a 3-point favorite.",
        "The public backs the Bears as an underdog (+145).",
        "Seattle -3 with a total of 46.5.",
        "Most bets are on the moneyline.",
    ):
        assert LINE.search(text), text
    for text in ("Chicago is 5-2 after a 30-24 win.", "Seattle allows 30+ yard plays rarely."):
        assert not LINE.search(text), text


def test_whole_trims_cut_off_text():
    assert _whole("One sentence. Two sentences.") == "One sentence. Two sentences."
    assert (
        _whole("First point holds. Then the model ran out at Indianapolis, a")
        == "First point holds."
    )
    assert _whole("Cut off with no sentence end, a") is None
    assert _whole('He said "it is done."') == 'He said "it is done."'


def test_line_facts_stay_out_and_line_sentences_drop(tmp_path, monkeypatch):
    line = {"text": "The Bills are favored by 3 points at home.", "category": "public", "team": "game", "player": None, "confidence": "high"}  # fmt: skip
    monkeypatch.setitem(FACTS, "https://www.covers.com/consensus", [*FACTS["https://www.covers.com/consensus"], line])  # fmt: skip
    _, rec, seen = _run(tmp_path)
    game_prompt = next(b for b in seen if b["response_format"]["json_schema"]["name"] == "GameOut")
    assert "favored by 3" not in game_prompt["messages"][0]["content"]
    assert "64% of bets" in game_prompt["messages"][0]["content"]  # betting action stays
    assert any("favored by 3" in c["claim"] for c in rec["claims"])  # still a cited claim


def test_matchup_pairing_and_whole_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tests.test_research.MATCHUPS",
        [
            *MATCHUPS,
            {"kind": "unit", "offense_team": "BUF", "defense_team": "BUF", "edge": None,
             "text": "Buffalo's pass rush against Buffalo's pass defense.", "fact_ids": ["F2"]},
            {"kind": "game", "offense_team": None, "defense_team": None, "edge": None,
             "text": "The article about the game is long enough to read.", "fact_ids": ["D2"]},
        ],
    )  # fmt: skip
    run, rec, seen = _run(tmp_path)
    prompt = next(b for b in seen if b["response_format"]["json_schema"]["name"] == "MatchupsOut")
    assert "D2 (buffalonews.com" in prompt["messages"][0]["content"]  # read whole
    assert run.dropped["matchup note pairing a unit with its own team"] == 1
    page_note = next(m for m in rec["matchup_notes"] if m["text"].startswith("The article"))
    assert page_note["sources"] == ["https://buffalonews.com/a"]


def test_one_job_per_call(tmp_path):
    _, _, seen = _run(tmp_path)
    names = [b["response_format"]["json_schema"]["name"] for b in seen]
    assert names[4:] == [  # after 4 extract calls
        "QbOut", "NotesOut", "TrendsOut", "SummaryOut",  # away (BAL has QB facts)
        "NotesOut", "TrendsOut", "SummaryOut",  # home (no QB facts: no QB call)
        "GameOut", "MatchupsOut",  # matchup last: the one call on another model
    ]  # fmt: skip
    assert all(b["reasoning_effort"] == "none" for b in seen)  # THINK is empty by default
    models = {b["response_format"]["json_schema"]["name"]: b["model"] for b in seen}
    assert models.pop("MatchupsOut") == "qwen3:14b"  # JOB_MODELS
    assert set(models.values()) == {"qwen3.5:9b"}


def test_job_model_failure_falls_back_to_the_client_model(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "JOB_MODELS", {"matchup": "missing:1b"})
    monkeypatch.setattr(sys.modules[__name__], "MISSING_MODEL", "missing:1b")
    run, rec, seen = _run(tmp_path)
    tries = [b["model"] for b in seen if b["response_format"]["json_schema"]["name"] == "MatchupsOut"]  # fmt: skip
    assert tries == ["missing:1b", "qwen3.5:9b"]
    assert rec["matchup_notes"] and rec["model"] == "qwen3.5:9b"
    assert any("missing:1b failed" in w for w in run.warnings)


def test_thinking_past_budget_redone_without(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "THINK", {"matchup": "low"})
    monkeypatch.setattr(sys.modules[__name__], "THINK_RUNS_OUT", True)
    run, rec, seen = _run(tmp_path)
    tries = [b["reasoning_effort"] for b in seen if b["response_format"]["json_schema"]["name"] == "MatchupsOut"]  # fmt: skip
    assert tries == ["low", "none"]
    assert rec["matchup_notes"]
    assert any("thinking ran past its budget" in w for w in run.warnings)


def _f(team: str, text: str) -> Fact:
    return Fact("F1", None, text, "scheme", team, "high")  # type: ignore[arg-type]


def test_stat_on_the_wrong_team():
    chi = Game(game_id="2026_08_CHI_SEA", season=2026, week=8, home="SEA", away="CHI", kickoff_utc=NOW, roof="outdoors", stadium=None, home_qb="Sam Darnold", away_qb="Caleb Williams")  # fmt: skip
    facts = [_f("CHI", "The Bears defense allows only 87.6 rushing yards per game, ranking 4th."),
             _f("CHI", "Chicago blitzes on 41.1% of pass plays."), _f("SEA", "Sam Darnold ranks 23rd in QBR.")]  # fmt: skip
    teams, players = _aliases(chi), _players(chi, facts, {"CHI": "Caleb Williams", "SEA": "Sam Darnold"})  # fmt: skip

    def wrong(text: str) -> bool:
        return _wrong_team(text, facts, teams, players)

    assert wrong("Chicago's rushing attack targets Seattle's run defense (87.6 ypg allowed).")
    assert not wrong("Seattle's offense faces a Bears run defense allowing 87.6 yards per game.")
    # a player claims a stat only when the sentence makes it theirs
    assert not wrong("The Bears will blitz Sam Darnold on 41.1% of pass plays.")
    assert not wrong("The Bears will pressure Sam Darnold and limit his 23rd-ranked QBR.")
    assert wrong("Chicago's Caleb Williams faces Seattle, whose 41.1% blitz rate is high.")
    # records, scores and single digits are not tied to one team
    assert not wrong("The 5-2 Chicago Bears visit the 4-3 Seattle Seahawks.")


def test_matchup_pairing_a_team_with_itself():
    teams, qbs = _aliases(GAME), {"BAL": "Lamar Jackson", "BUF": "Josh Allen"}
    assert _mispaired("Josh Allen leads the most efficient offense, which will test a Buffalo defense.", teams, qbs)  # fmt: skip
    assert _mispaired("Baltimore's blitz package faces Buffalo's top-ranked pass defense.", teams, qbs)  # fmt: skip
    assert not _mispaired("Lamar Jackson's return tests a Buffalo defense that ranks 31st.", teams, qbs)  # fmt: skip
    assert not _mispaired("Buffalo's offense faces a Ravens defense, while Buffalo's defense must contain Jackson.", teams, qbs)  # fmt: skip
    assert not _mispaired("Buffalo's pass rush could pressure Lamar Jackson behind a Ravens line missing its tackle.", teams, qbs)  # fmt: skip
    assert not _mispaired("Analysts expect another high-scoring shootout.", teams, qbs)


def test_fact_ids_stripped_from_text():
    assert (
        FACT_REF.sub("", "It allows 144.4 yards per game (F27).")
        == "It allows 144.4 yards per game."
    )
    assert (
        FACT_REF.sub("", "Bears are 5-2 [F3, F4] at home (2024).")
        == "Bears are 5-2 at home (2024)."
    )
