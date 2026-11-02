"""Local narrative research (M6.2L, ADR 0014): one game in, one validated v2 record out.

Code does everything that must be true: the queries, searching (SearXNG), fetching and the date
window, every URL, date and source count in the record. The desktop model does three small,
schema-constrained jobs: extract facts from one page at a time (`extract_v2`), write each team's
block from numbered facts (`compose_team_v2`), and write the game block (`compose_game_v2`). The
model cites fact ids, never URLs, so a fabricated URL is impossible by construction. Before each
team block, a small call (`qb_v1`) picks the starting quarterback from that team's QB facts alone.

Per game:
    queries (templates) -> search -> fetch, keep pages dated within WINDOW_DAYS -> D1..Dn
    -> extract facts per page -> F1..Fm (each tied to its page)
    -> compose home, away, game (citing F ids) -> map ids to URLs/dates/domains
    -> drop items the cited facts don't support -> GameNarrative -> ingest

v2 (2026-10-30, after the first BAL @ BUF run lost the matchup analysis): extraction has `scheme`
and `matchup` categories and names the player a fact is about; injury and QB facts are deduped per
player and capped, so they no longer crowd analysis out of the compose prompts; the game prompt
sees no injury facts (the team summaries carry them); summary and consensus sentences cite facts
like everything else; one check (`_unsupported`) covers numbers, two-word names and injury words;
matchup notes and scheme trends must rest on a matchup or scheme fact; claims rotate categories.
The first v2 run named the backup (Huntley) for BAL with 15 facts saying Jackson was cleared: the
starter is now its own call over QB facts sorted newest first, and fact lines carry their team.

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
EXTRACT_V = "extract_v2"
TEAM_V = "compose_team_v2"
GAME_V = "compose_game_v2"
QB_V = "qb_v1"
RECORD_PROMPT_VERSION = "local_v2"  # the record's prompt_version (feature rows carry it)

WINDOW_DAYS = 9  # one day inside the validator's 10, so a run that crosses midnight still passes
PER_QUERY = 3  # pages kept per query at most
MAX_DOCS = 20  # pages per game, picked round-robin across queries
MAX_FACTS_IN_PROMPT = 80
MAX_STATUS_FACTS = 25  # injury + QB facts per compose prompt, after the per-player dedupe
MAX_PER_PLAYER = 2  # status facts kept per player, newest page first
MAX_QB_FACTS = 30
MAX_CLAIMS = 30
STATUS = ("injury", "qb")
ANALYSIS = ("matchup", "scheme")
CLAIM_ORDER = ("injury", "qb", "matchup", "scheme", "public", "form", "coaching", "motivation", "weather", "other")  # fmt: skip
UNDATED_OK = {"betting", "weather"}
RANK = {"high": 0, "medium": 1, "low": 2}
NUMBER = re.compile(r"\d+(?:\.\d+)?")
# Runs of capitalized words ("Josh Allen", "C.J. Gardner-Johnson", "AFC North").
NAME = re.compile(r"[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)+")
NAME_LEAD = {
    "the", "a", "an", "in", "on", "at", "with", "after", "before", "while", "both", "but", "and",
    "as", "for", "against", "despite", "this", "that", "their", "his", "its", "when", "under",
    "without", "quarterback", "coach", "head", "defensive", "offensive", "safety", "receiver",
    "tackle", "cornerback", "linebacker", "guard", "center", "rookie", "veteran", "star",
}  # fmt: skip
# Injury and condition words a sentence may only use when a cited fact does ("back" only with an
# injury word after it: "running back" and "is back" are not conditions).
CONDITION = re.compile(
    r"\b(ankle|knee|hamstring|groin|shoulder|concussion|illness|toe|hip|calf|quad|wrist|elbow|"
    r"neck|rib|chest|achilles|acl|mcl|pectoral|oblique|thumb|foot|suspen|sprain|torn|fractur|"
    r"back(?=\s+(?:injury|injuries|issue|problem|spasm|tightness|surgery)))",
    re.IGNORECASE,
)


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


class SentenceOut(BaseModel):
    text: str = Field(min_length=10, max_length=400)
    fact_ids: list[str] = Field(min_length=1, max_length=4)


class TeamOut(BaseModel):
    notes: list[NoteOut] = Field(max_length=8)
    scheme_trends: list[TrendOut] = Field(max_length=4)
    key_absences: list[str] = Field(max_length=8)
    injury_impact: int = Field(ge=0, le=3)
    sentiment: float = Field(ge=-1, le=1)
    hype: float = Field(ge=0, le=1)
    coaching_turmoil: float = Field(ge=0, le=1)
    motivation: float = Field(ge=-1, le=1)
    revenge: bool
    lookahead: bool
    summary: list[SentenceOut] = Field(min_length=1, max_length=6)


class QbOut(BaseModel):
    qb_name: str | None
    qb_status: int = Field(ge=0, le=2)
    fact_ids: list[str] = Field(max_length=4)


class MatchupOut(BaseModel):
    text: str = Field(min_length=10, max_length=300)
    fact_ids: list[str] = Field(min_length=1, max_length=6)


class GameOut(BaseModel):
    matchup_notes: list[MatchupOut] = Field(max_length=5)
    consensus: list[SentenceOut] = Field(min_length=1, max_length=4)
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
        player=(str | None, ...),
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
    player: str | None = None

    def line(self) -> str:
        when = self.doc.published.isoformat() if self.doc.published else "undated"
        return f"{self.id} [{self.category}, {self.team}] ({self.doc.domain}, {when}) {self.text}"


@dataclass
class GameRun:
    game_id: str
    ok: bool = False
    error: str | None = None
    stored: str | None = None
    pages: Counter = field(default_factory=Counter)  # kept / dropped reasons
    facts: int = 0
    dropped: Counter = field(default_factory=Counter)  # items dropped while mapping
    recited: Counter = field(default_factory=Counter)  # items kept under a corrected citation
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
                Fact(f"F{len(facts) + 1}", d, f.text.strip(), f.category, f.team, f.confidence,
                     (f.player or "").strip() or None)
            )  # fmt: skip
    run.facts = len(facts)
    return facts


def _num(f: Fact) -> int:
    return int(f.id[1:])


def _freshest(f: Fact) -> tuple:
    """Sort key: most confident, then newest page, then latest fact."""
    return (RANK[f.confidence], -(f.doc.published or date.min).toordinal(), -_num(f))


def _latest_status(facts: list[Fact]) -> list[Fact]:
    """Injury and QB facts, at most MAX_PER_PLAYER per (team, player): newest page first, then
    most confident. Every page repeats the injury report, so without this it fills the prompt."""
    newest = sorted(facts, key=lambda f: (f.doc.published or date.min, -RANK[f.confidence], _num(f)), reverse=True)  # fmt: skip
    seen: Counter = Counter()
    out = []
    for f in newest:
        if f.player:
            key = (f.team, re.sub(r"[^a-z0-9]", "", f.player.lower()))
            seen[key] += 1
            if seen[key] > MAX_PER_PLAYER:
                continue
        out.append(f)
    return out


def _facts_for(facts: list[Fact], team: str | None) -> list[Fact]:
    """The facts a compose call sees, in id order. A team block gets that team's and the game's
    facts; the game block (team=None) gets everything but injury and QB facts. Status facts are
    deduped per player and capped at MAX_STATUS_FACTS; the rest fill up to MAX_FACTS_IN_PROMPT,
    most confident first."""
    if team is None:
        pool = [f for f in facts if f.category not in STATUS]
    else:
        pool = [f for f in facts if f.team in (team, "game")]
    status = _latest_status([f for f in pool if f.category in STATUS])
    status = sorted(status, key=_freshest)[:MAX_STATUS_FACTS]
    rest = sorted((f for f in pool if f.category not in STATUS), key=lambda f: (RANK[f.confidence], _num(f)))  # fmt: skip
    pick = status + rest[: MAX_FACTS_IN_PROMPT - len(status)]
    return sorted(pick, key=_num)


@dataclass
class Qb:
    """The starter as checked by code, the facts behind it, and the model's raw pick (None when
    there were no facts)."""

    name: str | None
    status: int
    raw: QbOut | None
    facts: list[Fact] = field(default_factory=list)

    def line(self) -> str:
        """For the team prompt: the name and the reports themselves, not the status rubric (the
        model copied "questionable, limited, or returning" into a note about a cleared starter)."""
        if self.name is None:
            return "undecided (no report settles it)"
        if not self.facts:
            return f"{self.name} (no injury reports this week)"
        return f"{self.name}. The reports: " + " ".join(f"{f.id}: {f.text}" for f in self.facts)


@dataclass
class Composed:
    away: TeamOut
    home: TeamOut
    game: GameOut
    qb: dict[str, Qb]  # by side


def _player_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _qb_facts(facts: list[Fact], team: str, schedule_qb: str | None) -> list[Fact]:
    """The team's QB facts and every fact about a player a QB fact names (or the schedule's
    starter), newest page first."""
    qbs = {_player_key(f.player) for f in facts if f.team == team and f.category == "qb" and f.player}  # fmt: skip
    if schedule_qb:
        qbs.add(_player_key(schedule_qb))
    pick = [f for f in facts if f.team == team and (f.category == "qb" or (f.player and _player_key(f.player) in qbs))]  # fmt: skip
    pick.sort(key=lambda f: (-(f.doc.published or date.min).toordinal(), -_num(f)))
    return pick[:MAX_QB_FACTS]


def pick_qb(g: Game, team: str, schedule_qb: str | None, facts: list[Fact], client: LLMClient, run: GameRun, now: datetime) -> Qb:  # fmt: skip
    """This week's starter from the team's QB facts alone. The pick must be the schedule's starter
    or named in a fact it cites; otherwise it becomes undecided (status 2)."""
    pool = _qb_facts(facts, team, schedule_qb)
    if not pool:
        run.warnings.append(f"{team}: no quarterback facts; the schedule's starter is used")
        return Qb(schedule_qb, 0 if schedule_qb else 2, None)
    names = full_names()
    system = _prompt(
        QB_V, **_ctx(g, now), team=team, team_full=names.get(team, team),
        qb_name=schedule_qb or "unknown", facts="\n".join(f.line() for f in pool),
    )  # fmt: skip
    raw = client.complete(
        [{"role": "user", "content": f"Who starts at quarterback for {team}?"}], system=system,
        schema=QbOut, job="narrative.qb", prompt_version=QB_V, game_id=g.game_id, max_tokens=400,
    ).parsed  # fmt: skip
    if raw.qb_name is None:
        return Qb(None, 2, raw)
    by_id = {f.id: f for f in facts}
    last = raw.qb_name.split()[-1].lower()
    cited = [f for f in _cited(raw.fact_ids, by_id) if last in f.text.lower()]
    if cited or (schedule_qb and _player_key(raw.qb_name) == _player_key(schedule_qb)):
        return Qb(raw.qb_name, raw.qb_status, raw, cited)
    run.dropped["qb pick not named in its facts"] += 1
    return Qb(None, 2, raw)


def compose(g: Game, facts: list[Fact], client: LLMClient, run: GameRun, now: datetime) -> Composed:  # fmt: skip
    ctx = _ctx(g, now)
    names = full_names()
    teams, qbs = {}, {}
    for side, team, opp, sched in (("away", g.away, g.home, g.away_qb), ("home", g.home, g.away, g.home_qb)):  # fmt: skip
        qbs[side] = pick_qb(g, team, sched, facts, client, run, now)
        lines = "\n".join(f.line() for f in _facts_for(facts, team)) or "(no facts found)"
        system = _prompt(
            TEAM_V, **ctx, side=side, team=team, team_full=names.get(team, team), opp=opp,
            opp_full=names.get(opp, opp), qb_line=qbs[side].line(), facts=lines,
        )  # fmt: skip
        teams[side] = client.complete(
            [{"role": "user", "content": f"Write the {team} block."}], system=system,
            schema=TeamOut, job="narrative.compose_team", prompt_version=TEAM_V,
            game_id=g.game_id, max_tokens=3000,
        ).parsed  # fmt: skip
    lines = "\n".join(f.line() for f in _facts_for(facts, None)) or "(no facts found)"
    system = _prompt(
        GAME_V, **ctx, away_summary=_joined(teams["away"].summary),
        home_summary=_joined(teams["home"].summary), facts=lines,
    )  # fmt: skip
    game = client.complete(
        [{"role": "user", "content": "Write the game block."}], system=system, schema=GameOut,
        job="narrative.compose_game", prompt_version=GAME_V, game_id=g.game_id, max_tokens=2000,
    ).parsed  # fmt: skip
    return Composed(teams["away"], teams["home"], game, qbs)


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


def _joined(sentences: list[SentenceOut]) -> str:
    return " ".join(x.text.strip() for x in sentences)


def _names(text: str) -> list[str]:
    """Names of two or more capitalized words, each as its last two words lowercased ("Quarterback
    Lamar Jackson's" -> "lamar jackson"), after dropping leading role and filler words."""
    out = []
    for m in NAME.finditer(text):
        words = [w.removesuffix("'s").removesuffix("’s") for w in m.group().split()]
        words[-1] = words[-1].rstrip(".,;:!?")
        while words and words[0].lower() in NAME_LEAD:
            words.pop(0)
        if len(words) >= 2:
            out.append(" ".join(words[-2:]).lower())
    return out


def _condition_in(root: str, low: str) -> bool:
    # stems match their forms (suspended, sprained); whole words only match themselves and plurals
    # ("back" must not match "backup")
    pattern = rf"\b{root}" if root in ("suspen", "sprain", "fractur") else rf"\b{root}s?\b"
    return re.search(pattern, low) is not None


def _unsupported(text: str, source: str) -> str | None:
    """What in `text` its source doesn't back, or None. The source is the cited facts' text plus
    the game's context. Every number, every name of two or more capitalized words (`_names`) and
    every injury or condition word must appear in it."""
    low = source.lower()
    have = set(NUMBER.findall(source))
    if any(n not in have for n in NUMBER.findall(text)):
        return "number"
    if any(n not in low for n in _names(text)):
        return "name"
    if any(not _condition_in(m.group(1).lower(), low) for m in CONDITION.finditer(text)):
        return "condition"
    return None


def _recite(text: str, ids: list[str], pool: list[Fact], context: str, need: tuple) -> Fact | None:
    """The 9B often cites a neighbor of the right fact (F24 for F23). When the cited facts don't
    back `text`, the one fact that backs it on its own, nearest the cited ids, if any. Only for
    text with something checkable in it (a number, name or condition), so a vague sentence never
    borrows an unrelated source."""
    if not (NUMBER.search(text) or _names(text) or CONDITION.search(text)):
        return None
    near = [int(m.group()) for i in ids if (m := re.search(r"\d+", i))] or [0]
    ok = [f for f in pool if (not need or f.category in need) and _unsupported(text, _source([f], context)) is None]  # fmt: skip
    return min(ok, key=lambda f: (min(abs(_num(f) - n) for n in near), RANK[f.confidence]), default=None)  # fmt: skip


def _source(cited: list[Fact], context: str) -> str:
    return " ".join(f.text for f in cited) + " " + context


def _distinct_urls(cited: list[Fact]) -> list[str]:
    return list(dict.fromkeys(f.doc.url for f in cited))


def _context(g: Game) -> str:
    """Words any sentence may use without a citation: the teams, the venue, the week."""
    names = full_names()
    return " ".join([
        g.home, g.away, names.get(g.home, ""), names.get(g.away, ""), g.stadium or "",
        f"week {g.week} {g.season}",
    ])  # fmt: skip


def _claims(facts: list[Fact]) -> list[dict]:
    """Up to MAX_CLAIMS facts, one category at a time in CLAIM_ORDER (injury and QB facts deduped
    per player), each category most confident and newest first."""
    queues = {c: [] for c in CLAIM_ORDER}
    for f in [*_latest_status([f for f in facts if f.category in STATUS]), *(f for f in facts if f.category not in STATUS)]:  # fmt: skip
        queues.setdefault(f.category, []).append(f)
    for q in queues.values():
        q.sort(key=_freshest)
    picked: list[Fact] = []
    while len(picked) < MAX_CLAIMS and any(queues.values()):
        for q in queues.values():
            if q and len(picked) < MAX_CLAIMS:
                picked.append(q.pop(0))
    return [
        {
            "claim": f.text[:300], "category": f.category,
            "team": None if f.team == "game" else f.team, "source_url": f.doc.url,
            "source_title": f.doc.title,
            "published_at": f.doc.published.isoformat() if f.doc.published else None,
            "confidence": f.confidence if f.doc.published else "low",
        }
        for f in picked
    ]  # fmt: skip


def build_record(g: Game, c: Composed, facts: list[Fact], searches: list[str], model: str, run: GameRun, now: datetime) -> dict:  # fmt: skip
    """The v2 record as a dict. Every item the model wrote (note, trend, matchup note, summary or
    consensus sentence) must cite a valid fact and pass `_unsupported` against what it cites;
    matchup notes and trends must cite a matchup or scheme fact. An item whose citation is off is
    re-cited when exactly checkable content points to another fact (`_recite`); the rest are
    dropped. Both are counted (run.recited, run.dropped)."""
    by_id = {f.id: f for f in facts}
    ctx = _context(g)
    game = c.game

    def check(what: str, text: str, ids: list[str], extra: str = "", need: tuple = (), teams: tuple | None = None) -> list[Fact] | None:  # fmt: skip
        """The facts that back `text`: the cited ones if they do, else one found by `_recite`
        among the facts about `teams` (counted in run.recited), else None (reason counted)."""
        cited = _cited(ids, by_id)
        context = ctx + " " + extra
        if not cited:
            why = "without a valid fact"
        elif need and not any(f.category in need for f in cited):
            why = f"without a {' or '.join(need)} fact"
        elif (bad := _unsupported(text, _source(cited, context))) is not None:
            why = f"with an unsupported {bad}"
        else:
            return cited
        pool = [f for f in facts if teams is None or f.team in teams]
        if (f := _recite(text, ids, pool, context, need)) is not None:
            run.recited[what] += 1
            return [f]
        run.dropped[f"{what} {why}"] += 1
        return None

    def sentences(what: str, items: list[SentenceOut], extra: str = "", teams: tuple | None = None) -> str:  # fmt: skip
        kept = [x.text.strip() for x in items if check(what, x.text, x.fact_ids, extra, teams=teams)]  # fmt: skip
        if not kept:
            run.warnings.append(f"no {what} passed the source check")
            return "No summary: none of the generated sentences passed the source check."
        return " ".join(kept)

    def team_block(t: TeamOut, team: str, qb: Qb) -> dict:
        mine = (team, "game")
        notes = []
        for n in t.notes:
            if cited := check("note", n.text, n.fact_ids, teams=mine):
                notes.append({"text": n.text, "kind": n.kind, "impact": n.impact, "source_url": cited[0].doc.url})  # fmt: skip
        trends = []
        for s in t.scheme_trends:
            if cited := check("trend", s.trend, s.fact_ids, need=ANALYSIS, teams=mine):
                trends.append({"unit": s.unit, "trend": s.trend, "working": s.working, "sources": _distinct_urls(cited)})  # fmt: skip
        return {
            "team": team, "qb_status": qb.status, "qb_name": qb.name,
            "injury_impact": t.injury_impact, "key_absences": t.key_absences,
            "sentiment": t.sentiment, "hype": t.hype, "coaching_turmoil": t.coaching_turmoil,
            "motivation": t.motivation, "revenge": t.revenge, "lookahead": t.lookahead,
            "summary": sentences("summary sentence", t.summary, teams=mine), "notes": notes,
            "scheme_trends": trends,
        }  # fmt: skip

    home_b = team_block(c.home, g.home, c.qb["home"])
    away_b = team_block(c.away, g.away, c.qb["away"])
    matchups = []
    for m in game.matchup_notes:
        if cited := check("matchup note", m.text, m.fact_ids, need=ANALYSIS):
            support = len({f.doc.domain for f in cited})
            matchups.append({"text": m.text, "support": support, "sources": _distinct_urls(cited)})
    # The consensus may repeat what the (already checked) team summaries say.
    consensus = sentences("consensus sentence", game.consensus, home_b["summary"] + " " + away_b["summary"])  # fmt: skip

    # The public share must come from a cited fact that states a percentage.
    pct = game.public_bet_pct_home
    bet = by_id.get(_norm_id(game.public_bet_fact_id)) if game.public_bet_fact_id else None
    if pct is not None and (bet is None or "%" not in bet.text and "percent" not in bet.text.lower()):  # fmt: skip
        run.dropped["public % without a supporting fact"] += 1
        pct = None

    return {
        "schema_version": "2", "game_id": g.game_id, "season": g.season, "week": g.week,
        "home_team": g.home, "away_team": g.away, "kickoff_utc": g.kickoff_utc.isoformat(),
        "known_as_of": now.replace(tzinfo=None, microsecond=0).isoformat(),
        "producer": "local", "model": model, "prompt_version": RECORD_PROMPT_VERSION,
        "home": home_b, "away": away_b,
        "public_pick": game.public_pick, "public_bet_pct_home": pct,
        "upset_buzz": game.upset_buzz,
        "weather_concern": game.weather_concern if g.outdoors else 0.0,
        "consensus_narrative": consensus, "matchup_notes": matchups,
        "claims": _claims(facts), "searches": searches,
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
        composed = compose(g, facts, client, run, now)
        d = drafts_dir(paths, g.season, g.week)
        d.mkdir(parents=True, exist_ok=True)
        stem = f"{g.game_id}_{snapshot_ts(now)}"
        _write_debug(d / f"{stem}.debug.json", docs, facts, composed)
        rec = build_record(g, composed, facts, searches, client.config.model, run, now)
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


def _write_debug(path: Path, docs: list[Doc], facts: list[Fact], c: Composed) -> None:
    """Pages, facts and the raw compose outputs: what M6.2e and prompt tuning need to see."""
    out = {
        "docs": [{"id": d.id, "url": d.url, "domain": d.domain, "kind": d.kind, "title": d.title,
                  "published": d.published.isoformat() if d.published else None} for d in docs],
        "facts": [{"id": f.id, "doc": f.doc.id, "team": f.team, "category": f.category,
                   "player": f.player, "confidence": f.confidence, "text": f.text} for f in facts],
        "compose": {"away": c.away.model_dump(), "home": c.home.model_dump(), "game": c.game.model_dump()},
        "qb": {side: {"name": q.name, "status": q.status, "raw": q.raw.model_dump() if q.raw else None}
               for side, q in c.qb.items()},
    }  # fmt: skip
    path.write_text(json.dumps(out, indent=1))


def _write_summary(paths: Paths, g: Game, run: GameRun) -> None:
    d = drafts_dir(paths, g.season, g.week)
    d.mkdir(parents=True, exist_ok=True)
    out = {
        "game_id": run.game_id, "ok": run.ok, "error": run.error, "stored": run.stored,
        "pages": dict(run.pages), "facts": run.facts, "dropped": dict(run.dropped),
        "recited": dict(run.recited),
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
