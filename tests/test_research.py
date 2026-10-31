"""Local narrative research: every URL comes from a fetched page, ids map back, unsupported numbers
and percentages are dropped, the date window holds (stub search, pages and LLM server)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import httpx

from nfl.config import Paths
from nfl.llm.client import LLMClient, LLMConfig
from nfl.llm.fetch import Page
from nfl.llm.narrative import GameNarrative
from nfl.llm.research import Game, queries, research_game
from nfl.llm.search import SearchResult

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
    if "preview" in q:
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
            "confidence": "high",
        },
    ],
    "https://buffalonews.com/a": [
        {
            "text": "Analysts expect the Bills pass rush to exploit the BAL backup tackle.",
            "category": "other",
            "team": "game",
            "confidence": "medium",
        },
    ],
    "https://www.cbssports.com/b": [
        {
            "text": "Preview says the Bills pass rush has the edge over a reshuffled BAL line.",
            "category": "other",
            "team": "game",
            "confidence": "medium",
        },
    ],
    "https://www.covers.com/consensus": [
        {
            "text": "Consensus shows 64% of bets on the Bills.",
            "category": "public",
            "team": "game",
            "confidence": "high",
        },
    ],
}


def _team(f_ids_ok: list[str]) -> dict:
    return {
        "notes": [
            {"text": "Starting left tackle is out; a backup starts.", "kind": "injury", "impact": -2, "fact_ids": f_ids_ok},
            {"text": "Line has allowed 12 sacks in three games.", "kind": "form", "impact": -1, "fact_ids": f_ids_ok},
            {"text": "Note citing a fact id that doesn't exist.", "kind": "other", "impact": 0, "fact_ids": ["F99"]},
        ],
        "scheme_trends": [],
        "key_absences": ["Ronnie Stanley (OT, Out)"],
        "qb_name": "Lamar Jackson", "qb_status": 0, "injury_impact": 2, "sentiment": 0.0,
        "hype": 0.5, "coaching_turmoil": 0.0, "motivation": 0.3, "revenge": False,
        "lookahead": False, "summary": "The team is missing its starting left tackle this week.",
    }  # fmt: skip


def _llm(seen: list[dict]):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body)
        name = body["response_format"]["json_schema"]["name"]
        if name == "PageFacts":
            text = body["messages"][-1]["content"]
            doc_url = next((u for u in FACTS if f"({_dom(u)}," in text), None)
            out = {"facts": FACTS.get(doc_url, [])}
        elif name == "TeamOut":
            out = _team(["F1"])
        else:
            out = {
                "matchup_notes": [{"text": "Bills pass rush against a backup tackle.", "fact_ids": ["F2", "Fact 4"]}],
                "consensus_narrative": "Buffalo hosts a Baltimore team missing its left tackle.",
                "public_pick": "home", "public_bet_pct_home": 0.64, "public_bet_fact_id": "[F3]",
                "upset_buzz": 0.2, "weather_concern": 0.3,
            }  # fmt: skip
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:9b",
                "choices": [{"message": {"content": json.dumps(out)}, "finish_reason": "stop"}],
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
    assert rec["producer"] == "local" and rec["model"] == "qwen3.5:9b"


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
    assert run.dropped["note with an unsupported number"] == 2  # "12 sacks", once per team
    assert run.dropped["note without a valid fact"] == 2


def test_public_share_needs_a_percentage_fact(tmp_path, monkeypatch):
    monkeypatch.setitem(
        FACTS,
        "https://www.covers.com/consensus",
        [
            {
                "text": "Most bettors are backing Buffalo this week.",
                "category": "public",
                "team": "game",
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
    sys = extract[0]["messages"][0]["content"]
    assert "Baltimore Ravens (BAL) at Buffalo Bills (BUF)" in sys
    team_enum = extract[0]["response_format"]["json_schema"]["schema"]["$defs"]["Fact"][
        "properties"
    ]["team"]
    assert set(team_enum["enum"]) == {"BAL", "BUF", "game"}
    assert all(b["reasoning_effort"] == "none" for b in seen)


def test_started_games_are_refused(tmp_path):
    late = datetime(2026, 11, 1, 19, 0, tzinfo=UTC)
    client = LLMClient(Paths(tmp_path), LLMConfig(base_url="http://desk/v1"), log=False)
    run = research_game(
        Paths(tmp_path), GAME, client, _Fetcher(), store=False, now=late, search_fn=_search
    )
    assert not run.ok and "kicked off" in run.error


def test_weather_query_only_outdoors():
    kinds = [k for k, _ in queries(GAME)]
    assert "weather" in kinds
    dome = Game(**{**GAME.__dict__, "roof": "dome"})
    assert "weather" not in [k for k, _ in queries(dome)]
