"""Local narrative research (M6.2L, ADR 0014): one game in, one validated v2 record out.

Code does everything that must be true: the queries, searching (SearXNG), fetching and the date
window, every URL, date and source count in the record. The desktop model does three small,
schema-constrained jobs: extract facts from one page at a time (`extract_v1`), write each team's
block from numbered facts (`compose_team_v1`), and write the game block (`compose_game_v1`). The
model cites fact ids, never URLs, so a fabricated URL is impossible by construction.

Per game:
    queries (templates) -> search -> fetch, keep pages dated within WINDOW_DAYS -> D1..Dn
    -> extract facts per page -> F1..Fm (each tied to its page)
    -> compose home, away, game (citing F ids) -> map ids to URLs/dates/domains
    -> drop items whose numbers aren't in their cited facts -> GameNarrative -> ingest

Undated pages are dropped, except for weather and betting-consensus queries, whose facts become
claims with `published_at: null` and `confidence: low`. Every LLM call is logged with the game id
(`nfl llm calls`); the draft record and a run summary are kept under raw/narrative_local/.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from string import Template
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, create_model

from nfl.config import Paths, now_utc, snapshot_ts
from nfl.llm.client import LLMClient, LLMError
from nfl.llm.fetch import Fetcher
from nfl.llm.narrative import Category, GameNarrative, ingest
from nfl.llm.search import SearchError, search

PROMPTS = Path(__file__).parent / "prompts"
EXTRACT_V = "extract_v1"
TEAM_V = "compose_team_v1"
GAME_V = "compose_game_v1"
RECORD_PROMPT_VERSION = "local_v1"  # the record's prompt_version (feature rows carry it)

WINDOW_DAYS = 9  # one day inside the validator's 10, so a run that crosses midnight still passes
PER_QUERY = 3  # pages kept per query at most
MAX_DOCS = 20  # pages per game, picked round-robin across queries
MAX_FACTS_IN_PROMPT = 80
MAX_CLAIMS = 30
UNDATED_OK = {"betting", "weather"}
NUMBER = re.compile(r"\d+(?:\.\d+)?")


# ------------------------------------------------------------------------------- model outputs


class NoteOut(BaseModel):
    text: str = Field(min_length=10, max_length=300)
    kind: Literal["injury", "coaching", "scheme", "form", "other"]
    impact: int = Field(ge=-2, le=2)
    fact_ids: list[str] = Field(min_length=1, max_length=4)


class TrendOut(BaseModel):
    unit: Literal["offense", "defense"]
    trend: str = Field(min_length=10, max_length=300)
    working: bool | None
    fact_ids: list[str] = Field(min_length=1, max_length=4)


class TeamOut(BaseModel):
    notes: list[NoteOut] = Field(max_length=8)
    scheme_trends: list[TrendOut] = Field(max_length=4)
    key_absences: list[str] = Field(max_length=8)
    qb_name: str | None
    qb_status: int = Field(ge=0, le=2)
    injury_impact: int = Field(ge=0, le=3)
    sentiment: float = Field(ge=-1, le=1)
    hype: float = Field(ge=0, le=1)
    coaching_turmoil: float = Field(ge=0, le=1)
    motivation: float = Field(ge=-1, le=1)
    revenge: bool
    lookahead: bool
    summary: str = Field(min_length=20, max_length=1200)


class MatchupOut(BaseModel):
    text: str = Field(min_length=10, max_length=300)
    fact_ids: list[str] = Field(min_length=1, max_length=6)


class GameOut(BaseModel):
    matchup_notes: list[MatchupOut] = Field(max_length=5)
    consensus_narrative: str = Field(min_length=20, max_length=900)
    public_pick: Literal["home", "away", "none"] | None
    public_bet_pct_home: float | None = Field(ge=0, le=1)
    public_bet_fact_id: str | None
    upset_buzz: float = Field(ge=0, le=1)
    weather_concern: float = Field(ge=0, le=1)


def page_facts_model(home: str, away: str) -> type[BaseModel]:
    """Extraction schema for one game: `team` is an enum of the two teams plus 'game'."""
    fact = create_model(
        "Fact",
        text=(str, Field(min_length=10, max_length=300)),
        category=(Category, ...),
        team=(Literal[(away, home, "game")], ...),  # type: ignore[valid-type]
        confidence=(Literal["high", "medium", "low"], ...),
    )
    return create_model("PageFacts", facts=(list[fact], Field(max_length=12)))  # type: ignore[valid-type]


# ------------------------------------------------------------------------------------- inputs


@dataclass
class Game:
    game_id: str
    season: int
    week: int
    home: str
    away: str
    kickoff_utc: datetime  # naive UTC
    roof: str | None
    stadium: str | None
    home_qb: str | None
    away_qb: str | None

    @classmethod
    def from_slate(cls, row: dict) -> Game:
        season, week = (int(x) for x in row["game_id"].split("_")[:2])
        return cls(
            game_id=row["game_id"], season=season, week=week, home=row["home_team"],
            away=row["away_team"], kickoff_utc=row["kickoff_utc"], roof=row.get("roof") or None,
            stadium=row.get("stadium"), home_qb=row.get("home_qb_name"),
            away_qb=row.get("away_qb_name"),
        )  # fmt: skip

    @property
    def outdoors(self) -> bool:
        return self.roof not in ("dome", "closed")


def full_names() -> dict[str, str]:
    from nfl.odds import TEAMS

    return {abbr: name for name, abbr in TEAMS.items()}


def queries(g: Game) -> list[tuple[str, str]]:
    """(kind, query) in search order, the /nfl-narrative skill's set as templates."""
    names = full_names()
    a, h = names.get(g.away, g.away), names.get(g.home, g.home)
    q: list[tuple[str, str]] = []
    for team in (a, h):
        q.append(("injury", f"{team} injury report week {g.week} {g.season}"))
    for team, qb in ((a, g.away_qb), (h, g.home_qb)):
        if qb:
            q.append(("qb", f"{team} {qb} status week {g.week}"))
    for team in (a, h):
        q.append(("news", f"{team} news week {g.week} {g.season}"))
    for team in (a, h):
        q.append(("scheme", f"{team} offense defense film breakdown {g.season}"))
    q.append(("matchup", f"{a} vs {h} week {g.week} preview"))
    q.append(("matchup", f"{a} vs {h} matchup keys to the game"))
    q.append(("betting", f"{a} vs {h} public betting percentages week {g.week}"))
    if g.outdoors and g.stadium:
        q.append(("weather", f"{g.stadium} weather {g.kickoff_utc:%B %-d %Y}"))
    return q


# ------------------------------------------------------------------------------ docs and facts


@dataclass
class Doc:
    id: str
    url: str
    title: str | None
    domain: str
    published: date | None
    kind: str
    text: str


@dataclass
class Fact:
    id: str
    doc: Doc
    text: str
    category: str
    team: str  # abbreviation or "game"
    confidence: str

    def line(self) -> str:
        when = self.doc.published.isoformat() if self.doc.published else "undated"
        return f"{self.id} [{self.category}] ({self.doc.domain}, {when}) {self.text}"


@dataclass
class GameRun:
    game_id: str
    ok: bool = False
    error: str | None = None
    stored: str | None = None
    pages: Counter = field(default_factory=Counter)  # kept / dropped reasons
    facts: int = 0
    dropped: Counter = field(default_factory=Counter)  # items dropped while mapping
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def gather(g: Game, fetcher: Fetcher, run: GameRun, now: datetime, search_fn=search) -> tuple[list[Doc], list[str]]:  # fmt: skip
    """Run every query first, then pick pages round-robin across the queries (each query's best
    remaining result in turn) until MAX_DOCS, so every kind of search gets pages; a query keeps at
    most PER_QUERY. Pages outside the date window don't count. Returns the pages and the queries."""
    today = now.date()
    sent: list[str] = []
    pools: list[tuple[str, list]] = []
    for kind, q in queries(g):
        sent.append(q)
        try:
            pools.append((kind, list(search_fn(q, max_results=8))))
        except SearchError as e:
            run.warnings.append(f"search failed for {q!r}: {e}")
    docs: list[Doc] = []
    seen: set[str] = set()
    kept = [0] * len(pools)
    while len(docs) < MAX_DOCS and any(pool for _, pool in pools):
        for i, (kind, pool) in enumerate(pools):
            if len(docs) >= MAX_DOCS:
                break
            while pool and kept[i] < PER_QUERY:  # this query's next usable page, if any
                r = pool.pop(0)
                if r.url in seen:
                    continue
                seen.add(r.url)
                if (doc := _admit(r, kind, fetcher, run, today, len(docs) + 1)) is not None:
                    docs.append(doc)
                    kept[i] += 1
                    break
            if kept[i] >= PER_QUERY:
                pool.clear()
    return docs, sent


def _admit(r, kind: str, fetcher: Fetcher, run: GameRun, today: date, n: int) -> Doc | None:
    page = fetcher.get(r.url)
    if not page.ok:
        run.pages[f"dropped: {page.reason}"] += 1
        return None
    # Page metadata is the main date source, but live-updated hub pages (team injury pages) carry
    # stale dates; the newer of page and search-engine date wins.
    pub = max((d for d in (page.published, r.published) if d), default=None)
    if pub is None and kind not in UNDATED_OK:
        run.pages["dropped: undated"] += 1
        return None
    if pub is not None and not (today - timedelta(days=WINDOW_DAYS) <= pub <= today):
        run.pages["dropped: outside date window"] += 1
        return None
    url = page.final_url or page.url
    run.pages["kept"] += 1
    return Doc(f"D{n}", url, page.title or r.title, _domain(url), pub, kind, page.text)


def _ctx(g: Game, now: datetime) -> dict[str, Any]:
    names = full_names()
    return {
        "away": g.away, "home": g.home, "away_full": names.get(g.away, g.away),
        "home_full": names.get(g.home, g.home), "season": g.season, "week": g.week,
        "kickoff_date": f"{g.kickoff_utc:%Y-%m-%d %H:%M}", "today": now.date().isoformat(),
        "venue": f"{g.stadium or 'stadium unknown'} ({g.roof or 'roof unknown'})",
    }  # fmt: skip


def _prompt(name: str, **kw: Any) -> str:
    return Template((PROMPTS / f"{name}.md").read_text()).substitute(**kw)


def extract(g: Game, docs: list[Doc], client: LLMClient, run: GameRun, now: datetime) -> list[Fact]:
    schema = page_facts_model(g.home, g.away)
    system = _prompt(EXTRACT_V, **_ctx(g, now))
    facts: list[Fact] = []
    for d in docs:
        when = d.published.isoformat() if d.published else "unknown"
        msg = f'Page {d.id}: "{d.title or ""}" ({d.domain}, published {when})\n\n{d.text}'
        try:
            r = client.complete(
                [{"role": "user", "content": msg}], system=system, schema=schema,
                job="narrative.extract", prompt_version=EXTRACT_V, game_id=g.game_id,
                max_tokens=1500,
            )  # fmt: skip
        except LLMError as e:
            run.warnings.append(f"extract failed for {d.id} ({d.domain}): {e}")
            continue
        for f in r.parsed.facts:
            facts.append(
                Fact(f"F{len(facts) + 1}", d, f.text.strip(), f.category, f.team, f.confidence)
            )
    run.facts = len(facts)
    return facts


def _facts_for(facts: list[Fact], team: str | None) -> list[Fact]:
    """The facts a compose call sees: about this team or the game (team=None: all), highest
    confidence first, capped to fit the context."""
    pick = [f for f in facts if team is None or f.team in (team, "game")]
    rank = {"high": 0, "medium": 1, "low": 2}
    pick = sorted(pick, key=lambda f: (rank[f.confidence], int(f.id[1:])))[:MAX_FACTS_IN_PROMPT]
    return sorted(pick, key=lambda f: int(f.id[1:]))


def compose(g: Game, facts: list[Fact], client: LLMClient, now: datetime) -> tuple[TeamOut, TeamOut, GameOut]:  # fmt: skip
    ctx = _ctx(g, now)
    names = full_names()
    teams = {}
    for side, team, opp, qb in (("away", g.away, g.home, g.away_qb), ("home", g.home, g.away, g.home_qb)):  # fmt: skip
        lines = "\n".join(f.line() for f in _facts_for(facts, team)) or "(no facts found)"
        system = _prompt(
            TEAM_V, **ctx, side=side, team=team, team_full=names.get(team, team), opp=opp,
            opp_full=names.get(opp, opp), qb_name=qb or "unknown", facts=lines,
        )  # fmt: skip
        teams[side] = client.complete(
            [{"role": "user", "content": f"Write the {team} block."}], system=system,
            schema=TeamOut, job="narrative.compose_team", prompt_version=TEAM_V,
            game_id=g.game_id, max_tokens=3000,
        ).parsed  # fmt: skip
    lines = "\n".join(f.line() for f in _facts_for(facts, None)) or "(no facts found)"
    system = _prompt(
        GAME_V, **ctx, away_summary=teams["away"].summary, home_summary=teams["home"].summary,
        facts=lines,
    )  # fmt: skip
    game = client.complete(
        [{"role": "user", "content": "Write the game block."}], system=system, schema=GameOut,
        job="narrative.compose_game", prompt_version=GAME_V, game_id=g.game_id, max_tokens=2000,
    ).parsed  # fmt: skip
    return teams["away"], teams["home"], game


# ----------------------------------------------------------------------------------- mapping


def _norm_id(x: str) -> str:
    """'F12', '12', 'Fact 12', '[F12]' all mean F12."""
    m = re.search(r"\d+", x)
    return f"F{int(m.group())}" if m else x


def _cited(ids: list[str], by_id: dict[str, Fact]) -> list[Fact]:
    out, seen = [], set()
    for i in ids:
        f = by_id.get(_norm_id(i))
        if f and f.id not in seen:
            out.append(f)
            seen.add(f.id)
    return out


def _numbers_supported(text: str, cited: list[Fact]) -> bool:
    """Every number in generated text must appear in one of the facts it cites."""
    source = " ".join(f.text for f in cited)
    have = set(NUMBER.findall(source))
    return all(n in have for n in NUMBER.findall(text))


def _distinct_urls(cited: list[Fact]) -> list[str]:
    return list(dict.fromkeys(f.doc.url for f in cited))


def build_record(g: Game, away: TeamOut, home: TeamOut, game: GameOut, facts: list[Fact], searches: list[str], model: str, run: GameRun, now: datetime) -> dict:  # fmt: skip
    """The v2 record as a dict. Items citing no valid fact, or stating a number their facts don't
    contain, are dropped (counted in run.dropped)."""
    by_id = {f.id: f for f in facts}

    def team_block(t: TeamOut, team: str) -> dict:
        notes = []
        for n in t.notes:
            cited = _cited(n.fact_ids, by_id)
            if not cited:
                run.dropped["note without a valid fact"] += 1
            elif not _numbers_supported(n.text, cited):
                run.dropped["note with an unsupported number"] += 1
            else:
                notes.append({"text": n.text, "kind": n.kind, "impact": n.impact, "source_url": cited[0].doc.url})  # fmt: skip
        trends = []
        for s in t.scheme_trends:
            cited = _cited(s.fact_ids, by_id)
            if not cited:
                run.dropped["trend without a valid fact"] += 1
            elif not _numbers_supported(s.trend, cited):
                run.dropped["trend with an unsupported number"] += 1
            else:
                trends.append({"unit": s.unit, "trend": s.trend, "working": s.working, "sources": _distinct_urls(cited)})  # fmt: skip
        if not _numbers_supported(t.summary, facts):
            run.warnings.append(f"{team} summary has a number not found in any fact")
        return {
            "team": team, "qb_status": t.qb_status, "qb_name": t.qb_name,
            "injury_impact": t.injury_impact, "key_absences": t.key_absences,
            "sentiment": t.sentiment, "hype": t.hype, "coaching_turmoil": t.coaching_turmoil,
            "motivation": t.motivation, "revenge": t.revenge, "lookahead": t.lookahead,
            "summary": t.summary, "notes": notes, "scheme_trends": trends,
        }  # fmt: skip

    matchups = []
    for m in game.matchup_notes:
        cited = _cited(m.fact_ids, by_id)
        if not cited:
            run.dropped["matchup note without a valid fact"] += 1
        elif not _numbers_supported(m.text, cited):
            run.dropped["matchup note with an unsupported number"] += 1
        else:
            support = len({f.doc.domain for f in cited})
            matchups.append({"text": m.text, "support": support, "sources": _distinct_urls(cited)})

    # The public share must come from a cited fact that states a percentage.
    pct = game.public_bet_pct_home
    bet = by_id.get(_norm_id(game.public_bet_fact_id)) if game.public_bet_fact_id else None
    if pct is not None and (bet is None or "%" not in bet.text and "percent" not in bet.text.lower()):  # fmt: skip
        run.dropped["public % without a supporting fact"] += 1
        pct = None

    claims = []
    rank = {"high": 0, "medium": 1, "low": 2}
    for f in sorted(facts, key=lambda f: (f.category not in ("injury", "qb"), rank[f.confidence])):
        if len(claims) >= MAX_CLAIMS:
            break
        claims.append({
            "claim": f.text[:300], "category": f.category,
            "team": None if f.team == "game" else f.team, "source_url": f.doc.url,
            "source_title": f.doc.title,
            "published_at": f.doc.published.isoformat() if f.doc.published else None,
            "confidence": f.confidence if f.doc.published else "low",
        })  # fmt: skip

    return {
        "schema_version": "2", "game_id": g.game_id, "season": g.season, "week": g.week,
        "home_team": g.home, "away_team": g.away, "kickoff_utc": g.kickoff_utc.isoformat(),
        "known_as_of": now.replace(tzinfo=None, microsecond=0).isoformat(),
        "producer": "local", "model": model, "prompt_version": RECORD_PROMPT_VERSION,
        "home": team_block(home, g.home), "away": team_block(away, g.away),
        "public_pick": game.public_pick, "public_bet_pct_home": pct,
        "upset_buzz": game.upset_buzz,
        "weather_concern": game.weather_concern if g.outdoors else 0.0,
        "consensus_narrative": game.consensus_narrative, "matchup_notes": matchups,
        "claims": claims, "searches": searches,
    }  # fmt: skip


# ------------------------------------------------------------------------------------- run


def drafts_dir(paths: Paths, season: int, week: int) -> Path:
    return paths.root / "raw" / "narrative_local" / f"season={season}" / f"week={week:02d}"


def research_game(paths: Paths, g: Game, client: LLMClient, fetcher: Fetcher, *, store: bool = True, now: datetime | None = None, search_fn=search) -> GameRun:  # fmt: skip
    """Research one game end to end. Never raises: failures are in the returned GameRun."""
    run = GameRun(g.game_id)
    t0 = time.perf_counter()
    now = now or now_utc()
    try:
        if g.kickoff_utc <= now.replace(tzinfo=None):
            raise ValueError("already kicked off")
        docs, searches = gather(g, fetcher, run, now, search_fn)
        if not docs:
            raise ValueError("no usable pages")
        facts = extract(g, docs, client, run, now)
        if not facts:
            raise ValueError("no facts extracted")
        away, home, game = compose(g, facts, client, now)
        d = drafts_dir(paths, g.season, g.week)
        d.mkdir(parents=True, exist_ok=True)
        stem = f"{g.game_id}_{snapshot_ts(now)}"
        _write_debug(d / f"{stem}.debug.json", docs, facts, away, home, game)
        rec = build_record(g, away, home, game, facts, searches, client.config.model, run, now)
        GameNarrative.model_validate(rec)  # fail here, with the draft kept, before ingest
        draft = d / f"{stem}.json"
        draft.write_text(json.dumps(rec, indent=1))
        if store:
            run.stored = str(ingest(paths, draft))
        run.ok = True
    except (LLMError, ValueError) as e:  # pydantic's ValidationError is a ValueError
        run.error = f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
    run.seconds = time.perf_counter() - t0
    _write_summary(paths, g, run)
    return run


def _write_debug(path: Path, docs: list[Doc], facts: list[Fact], *outs: BaseModel) -> None:
    """Pages, facts and the raw compose outputs: what M6.2e and prompt tuning need to see."""
    out = {
        "docs": [{"id": d.id, "url": d.url, "domain": d.domain, "kind": d.kind, "title": d.title,
                  "published": d.published.isoformat() if d.published else None} for d in docs],
        "facts": [{"id": f.id, "doc": f.doc.id, "team": f.team, "category": f.category,
                   "confidence": f.confidence, "text": f.text} for f in facts],
        "compose": {k: o.model_dump() for k, o in zip(("away", "home", "game"), outs, strict=True)},
    }  # fmt: skip
    path.write_text(json.dumps(out, indent=1))


def _write_summary(paths: Paths, g: Game, run: GameRun) -> None:
    d = drafts_dir(paths, g.season, g.week)
    d.mkdir(parents=True, exist_ok=True)
    out = {
        "game_id": run.game_id, "ok": run.ok, "error": run.error, "stored": run.stored,
        "pages": dict(run.pages), "facts": run.facts, "dropped": dict(run.dropped),
        "warnings": run.warnings, "seconds": round(run.seconds, 1),
        "finished_at": datetime.now(UTC).isoformat(),
    }  # fmt: skip
    (d / f"{g.game_id}_{snapshot_ts()}.summary.json").write_text(json.dumps(out, indent=1))


def run_week(paths: Paths, season: int, week: int, game_ids: list[str] | None = None, *, store: bool = True) -> list[GameRun]:  # fmt: skip
    from nfl.llm.narrative import slate

    rows = slate(paths, season, week).to_dicts()
    if game_ids:
        unknown = set(game_ids) - {r["game_id"] for r in rows}
        if unknown:
            raise ValueError(f"not in {season} week {week}: {sorted(unknown)}")
        rows = [r for r in rows if r["game_id"] in game_ids]
    else:  # the default skips games already under way
        now = now_utc().replace(tzinfo=None)
        rows = [r for r in rows if r["kickoff_utc"] > now]
    client = LLMClient(paths)
    fetcher = Fetcher(paths)
    return [research_game(paths, Game.from_slate(r), client, fetcher, store=store) for r in rows]
