"""Narrative records: the contract between the research step and the pipeline (ideas note §3).

One JSON record per game per research run, in marts/narrative/season=YYYY/week=WW/<game_id>_<ts>.json.
`producer` says who did the research: 'claude_code' (the /nfl-narrative skill, development) or 'api'
(the Sonnet job, production). The pipeline treats them identically; `nfl.features.narrative` turns
records into feature rows stamped with the record's `known_as_of`.

Rules enforced here: every claim is dated at or before `known_as_of`; the record is stamped before
kickoff; numbers are in range; the teams match the game. Nothing here calls an LLM.

v2 (2026-10-27, `.notes/ui-feedback.md` #6): per team a paragraph `summary`, bullet `notes` (each
with a kind, an impact direction and a source) and `scheme_trends` (what the offense or defense has
been doing and whether it's working, per public analysis); per game `matchup_notes` with `support`,
the number of independent sources saying it. These are text with citations: they never feed model
numbers (ADR 0007). `known_as_of` is set by `ingest` to the ingest clock; the producer's own claim is
kept as `reported_finished_at`. v1 records still load (the new lists default to empty).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from nfl.config import Paths

SCHEMA_VERSION = "2"
PROMPT_VERSION = "narrative_v2"
MAX_SOURCE_AGE_DAYS = 10

Category = Literal["injury", "qb", "coaching", "motivation", "public", "weather", "form", "other"]


class Claim(BaseModel):
    claim: str = Field(min_length=10, max_length=300)
    category: Category
    team: str | None = None  # abbreviation, or None for game-level
    source_url: HttpUrl
    source_title: str | None = None
    published_at: date | None = None
    confidence: Literal["high", "medium", "low"]


class Note(BaseModel):
    text: str = Field(min_length=10, max_length=300)
    kind: Literal["injury", "coaching", "scheme", "form", "other"]
    impact: int = Field(ge=-2, le=2)  # for this team: −2 hurts a lot … +2 helps a lot
    source_url: HttpUrl | None = None


class SchemeTrend(BaseModel):
    unit: Literal["offense", "defense"]
    trend: str = Field(min_length=10, max_length=300)
    working: bool | None = None  # per the coverage: is it producing results?
    sources: list[HttpUrl] = Field(min_length=1)


class MatchupNote(BaseModel):
    text: str = Field(min_length=10, max_length=300)
    support: int = Field(ge=1)  # independent sources saying this
    sources: list[HttpUrl] = Field(min_length=1)

    @model_validator(mode="after")
    def _support_matches_sources(self) -> MatchupNote:
        if self.support > len(self.sources):
            raise ValueError("support cannot exceed the number of cited sources")
        return self


class TeamNarrative(BaseModel):
    team: str
    qb_status: int = Field(
        ge=0, le=2
    )  # 0 healthy starter, 1 questionable/limited/new, 2 backup or unknown
    qb_name: str | None = None
    injury_impact: int = Field(ge=0, le=3)
    key_absences: list[str] = []
    sentiment: float = Field(ge=-1, le=1)  # media tone
    hype: float = Field(ge=0, le=1)  # coverage volume
    coaching_turmoil: float = Field(ge=0, le=1)
    motivation: float = Field(ge=-1, le=1)  # -1 nothing to play for, +1 must-win
    revenge: bool = False
    lookahead: bool = False
    summary: str = Field(min_length=20, max_length=1200)
    notes: list[Note] = []
    scheme_trends: list[SchemeTrend] = []


class GameNarrative(BaseModel):
    schema_version: Literal["1", "2"] = SCHEMA_VERSION
    game_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    kickoff_utc: datetime
    known_as_of: datetime
    reported_finished_at: datetime | None = None  # what the producer said; known_as_of is the clock
    producer: Literal["claude_code", "api", "local"]  # local = desktop open-weight model (ADR 0014)
    model: str
    prompt_version: str = PROMPT_VERSION
    home: TeamNarrative
    away: TeamNarrative
    public_pick: Literal["home", "away", "none"] | None = None
    public_bet_pct_home: float | None = Field(default=None, ge=0, le=1)
    upset_buzz: float = Field(ge=0, le=1)
    weather_concern: float = Field(ge=0, le=1)
    consensus_narrative: str = Field(min_length=20, max_length=900)
    matchup_notes: list[MatchupNote] = []
    claims: list[Claim] = Field(min_length=1)
    searches: list[str] = Field(min_length=1)

    @field_validator("kickoff_utc", "known_as_of", "reported_finished_at")
    @classmethod
    def _naive_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        return v.astimezone(UTC).replace(tzinfo=None) if v.tzinfo else v

    @model_validator(mode="after")
    def _consistent(self) -> GameNarrative:
        if self.home.team != self.home_team or self.away.team != self.away_team:
            raise ValueError("home/away team blocks must match home_team/away_team")
        if self.known_as_of >= self.kickoff_utc:
            raise ValueError("known_as_of must be before kickoff")
        kao = self.known_as_of.date()
        for c in self.claims:
            if c.published_at and c.published_at > kao:
                raise ValueError(f"claim published after known_as_of: {c.claim[:60]!r}")
            if c.published_at and (kao - c.published_at).days > MAX_SOURCE_AGE_DAYS:
                raise ValueError(f"claim older than {MAX_SOURCE_AGE_DAYS} days: {c.claim[:60]!r}")
            if c.team and c.team not in (self.home_team, self.away_team):
                raise ValueError(f"claim team {c.team!r} not in game")
        return self


# --------------------------------------------------------------------------------------- store


def store_dir(paths: Paths, season: int, week: int) -> Path:
    return paths.marts / "narrative" / f"season={season}" / f"week={week:02d}"


def ingest(paths: Paths, src: Path, now: datetime | None = None) -> Path:
    """Validate a record file and store it under its game and the ingest time. Returns the path.

    known_as_of is the ingest clock, never the producer's word (2026-10-27: a producer stamped a
    record four minutes after it was actually written). The producer's value is kept as
    reported_finished_at. Research ingested at or after kickoff is rejected."""
    raw = json.loads(src.read_text())
    now = now or datetime.now(UTC)
    # naive datetimes are UTC throughout this project (astimezone would read them as local time)
    clock = (now.astimezone(UTC) if now.tzinfo else now).replace(tzinfo=None, microsecond=0)
    raw["reported_finished_at"] = raw.get("reported_finished_at") or raw.get("known_as_of")
    raw["known_as_of"] = clock.isoformat()
    _check_against_schedule(paths, raw)
    rec = GameNarrative.model_validate(raw)
    d = store_dir(paths, rec.season, rec.week)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{rec.game_id}_{rec.known_as_of.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(rec.model_dump_json(indent=1))
    return out


def _check_against_schedule(paths: Paths, raw: dict) -> None:
    """The game must exist in the curated schedule with the same season, week and teams; the
    schedule's kickoff (not the producer's copy) is the one the record must precede, and it
    overwrites the record's kickoff_utc. Review 2026-10-28: a wrong or flexed kickoff used to pass
    ingest and then break every feature build."""
    from nfl.features.store import games_frame

    g = games_frame(paths).filter(pl.col("game_id") == raw.get("game_id"))
    if g.is_empty():
        raise ValueError(f"unknown game_id {raw.get('game_id')!r} (not in the curated schedule)")
    r = g.row(0, named=True)
    for key, col in (
        ("season", "season"),
        ("week", "week"),
        ("home_team", "home_team"),
        ("away_team", "away_team"),
    ):
        if raw.get(key) != r[col]:
            raise ValueError(f"{key} {raw.get(key)!r} does not match the schedule ({r[col]!r})")
    kick = r["kickoff_utc"]
    kick = kick.replace(tzinfo=None) if kick.tzinfo else kick
    raw["kickoff_utc"] = kick.isoformat()


def load_records(paths: Paths, seasons: tuple[int, int] | None = None) -> list[GameNarrative]:
    root = paths.marts / "narrative"
    out = []
    for f in sorted(root.glob("season=*/week=*/*.json")):
        season = int(f.parent.parent.name.split("=")[1])
        if seasons and not (seasons[0] <= season <= seasons[1]):
            continue
        out.append(GameNarrative.model_validate_json(f.read_text()))
    return out


def slate(paths: Paths, season: int, week: int) -> pl.DataFrame:
    """What the research step needs per game: teams, kickoff, the current consensus line."""
    from nfl import odds
    from nfl.features.store import games_frame

    g = games_frame(paths).filter((pl.col("season") == season) & (pl.col("week") == week))
    cols = ["game_id", "kickoff_utc", "away_team", "home_team", "roof", "stadium", "spread_line",
            "total_line", "away_qb_name", "home_qb_name", "away_coach", "home_coach"]  # fmt: skip
    out = g.select(cols)
    lines = odds.read_lines(paths)
    if not lines.is_empty():
        c = odds.consensus(lines).sort("snapshot_ts").group_by("game_id").last()
        out = out.join(
            c.select("game_id", pl.col("spread_home").alias("odds_spread"), pl.col("total").alias("odds_total"),
                     pl.col("p_home_vigfree"), pl.col("snapshot_ts").alias("odds_as_of")),
            on="game_id", how="left",
        )  # fmt: skip
    return out.sort("kickoff_utc")


def example() -> dict:
    """A complete, valid record (used by the skill and the tests)."""
    return {
        "game_id": "2026_08_BAL_BUF",
        "season": 2026,
        "week": 8,
        "home_team": "BUF",
        "away_team": "BAL",
        "kickoff_utc": "2026-11-01T18:00:00Z",
        "known_as_of": "2026-10-28T20:00:00Z",
        "producer": "claude_code",
        "model": "claude-code",
        "prompt_version": PROMPT_VERSION,
        "home": {
            "team": "BUF",
            "qb_status": 0,
            "qb_name": "Josh Allen",
            "injury_impact": 1,
            "key_absences": ["Example Player (WR, Out)"],
            "sentiment": 0.3,
            "hype": 0.7,
            "coaching_turmoil": 0.0,
            "motivation": 0.4,
            "revenge": False,
            "lookahead": False,
            "summary": "Example summary of the home team's week: who is out, what the beat writers expect.",
            "notes": [
                {
                    "text": "Example: starting WR ruled out; the slot role shifts to a rookie.",
                    "kind": "injury",
                    "impact": -1,
                    "source_url": "https://www.example.com/article",
                },
            ],
            "scheme_trends": [
                {
                    "unit": "defense",
                    "trend": "Example: blitzing on third down far more over the last three weeks.",
                    "working": True,
                    "sources": ["https://www.example.com/article"],
                },
            ],
        },
        "away": {
            "team": "BAL",
            "qb_status": 1,
            "qb_name": "Lamar Jackson",
            "injury_impact": 2,
            "key_absences": ["Example Player (OT, Doubtful)"],
            "sentiment": -0.2,
            "hype": 0.6,
            "coaching_turmoil": 0.1,
            "motivation": 0.5,
            "revenge": True,
            "lookahead": False,
            "summary": "Example summary of the away team's week.",
        },
        "public_pick": "home",
        "public_bet_pct_home": 0.64,
        "upset_buzz": 0.2,
        "weather_concern": 0.3,
        "consensus_narrative": "Example of the week's story in two or three neutral sentences.",
        "matchup_notes": [
            {
                "text": "Example: analysts expect the home pass rush to overwhelm a reshuffled line.",
                "support": 2,
                "sources": ["https://www.example.com/a", "https://www.example.com/b"],
            },
        ],
        "claims": [
            {
                "claim": "Example claim that a named player is listed as Doubtful on Friday's report.",
                "category": "injury",
                "team": "BAL",
                "source_url": "https://www.example.com/article",
                "source_title": "Example title",
                "published_at": "2026-10-28",
                "confidence": "high",
            }
        ],
        "searches": ["Ravens injury report week 8 2026"],
    }
