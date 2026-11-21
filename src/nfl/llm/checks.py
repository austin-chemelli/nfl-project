"""Checks code runs on a narrative record before it is stored (ADR 0030).

The research model writes the record; these decide what of it may be published. Each check drops
the items it can't stand behind (a claim, a note, a trend, a matchup note, an absence, a sentence of
a summary) and counts them; none rewrites text. A record that loses so much that it no longer
validates fails the game.

- `rosters`: a player named under a team must be on that team's latest weekly roster (absences,
  injury notes, the QB) or at least on one of the two teams (summaries, other notes, trends,
  claims). Names on no roster (coaches, former players) pass: the check catches players placed on
  the wrong team, the error the site checks found (2026-11-15), mostly trades the coverage or the
  model hadn't caught.
- `standings`: a record "W-L" or "W-L-T" in text must be one either team actually had this season
  (the site checks found "5-2-1" for a 5-3-1 team).
- `sources`: every cited URL must be a page the model opened in this run (`opened`); the page date
  is code's when code could read one (`pages`), and items citing a page outside the window drop.
- `line`: no betting line in text (`research.LINE`); `public` claims may state one.
- `on_page`: every number, two-word name and injury word in a note, trend, matchup note or claim
  should appear in the text of a page it cites (`research._unsupported`). A flag, not a drop
  (`Context.on_page_drops`): on the first Claude records most misses were the check's own (outlet
  names read as people, code's extractor keeping a third of an article), so it is measured first.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

import polars as pl

from nfl.config import Paths
from nfl.llm.research import LINE, NAME, NAME_LEAD, _unsupported

SUFFIX = re.compile(r"\b(?:jr|sr|ii|iii|iv|v)\b\.?", re.IGNORECASE)
RECORD = re.compile(r"(?<![\w.-])(\d{1,2})-(\d{1,2})(?:-(\d))?(?![\w-]|\.\d|-\d)")
# "0-4 at home", "3-1 in the division": a split, not the season record
SPLIT_AFTER = re.compile(
    r"\s+(?:at home|on the road|away|in (?:the )?(?:division|conference|one-score|close|road|home|"
    r"prime ?time|night)\w*|against|vs\.?|versus|ats|when|in games|in their last|over (?:the|their) last|"
    r"in the last|since|this month|in november|in october|in december|straight|in a row|run|stretch|"
    r"start|to start|to open|record (?:at|on|in|against))",
    re.IGNORECASE,
)
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9'\"“])")


def norm_name(n: str) -> str:
    n = SUFFIX.sub("", n.lower().replace("’", "'"))
    n = re.sub(r"[^a-z\s]", "", n.replace("-", " "))
    return " ".join(n.split()[-2:])


def norm_url(u: str) -> str:
    p = urlparse(str(u))
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")).lower()


def names_in(text: str) -> list[str]:
    """Candidate player names in text, normalized like the roster (last two words, no suffix)."""
    out = []
    for m in NAME.finditer(text or ""):
        words = [w.removesuffix("'s").removesuffix("’s").rstrip(".,;:!?'’") for w in m.group().split()]  # fmt: skip
        words = [w for w in words if w and not SUFFIX.fullmatch(w)]
        while words and words[0].lower() in NAME_LEAD:
            words.pop(0)
        for i in range(len(words) - 1):  # "Ravens QB Jacoby Brissett": every adjacent pair
            out.append(norm_name(" ".join(words[i : i + 2])))
    return [n for n in out if " " in n]


# ------------------------------------------------------------------------------------ inputs


def roster_index(paths: Paths, season: int, week: int) -> dict[str, set[str]]:
    """Normalized player name -> teams, from the latest weekly roster at or before `week`."""
    root = paths.curated / "rosters_weekly" / f"season={season}"
    if not root.exists():
        return {}
    r = pl.read_parquet(root).filter(pl.col("week") <= week)
    if r.is_empty():
        return {}
    r = r.filter(pl.col("week") == r["week"].max())
    r = r.filter(pl.col("status").is_in(["ACT", "INA", "RES", "DEV", "EXE", "TRC"]))
    idx: dict[str, set[str]] = {}
    for team, full, first, last in r.select("team", "full_name", "football_name", "last_name").iter_rows():  # fmt: skip
        for n in {full, f"{first} {last}" if first and last else None}:
            if n:
                idx.setdefault(norm_name(n), set()).add(team)
    return idx


def same_person(a: str, b: str) -> bool:
    """Two names for one player, tolerant to initials and suffixes: the same last name and first
    names that agree on their first letter ("J. Brissett" = "Jacoby Brissett Jr.")."""
    x, y = norm_name(a).split(), norm_name(b).split()
    if not x or not y or x[-1] != y[-1]:
        return False
    return len(x) == 1 or len(y) == 1 or x[0][0] == y[0][0]


def on_roster(name: str, team: str, roster: dict[str, set[str]]) -> bool:
    """`name` is on `team`'s roster. True without any roster (nothing to check against)."""
    if not roster:
        return True
    if team in roster.get(norm_name(name), set()):
        return True
    return any(team in teams and same_person(name, k) for k, teams in roster.items())


def season_records(games: pl.DataFrame, season: int, teams: tuple[str, ...], before: datetime) -> set[str]:  # fmt: skip
    """Every record ("W-L" and, with ties, "W-L-T") the teams had this season before `before`."""
    g = games.filter(
        (pl.col("season") == season) & pl.col("result").is_not_null()
        & (pl.col("game_type") == "REG") & (pl.col("kickoff_utc").dt.replace_time_zone(None) < before)
    ).sort("kickoff_utc")  # fmt: skip
    out = set()
    for t in teams:
        w = l = ties = 0
        out.add("0-0")
        for home, away, res in g.select("home_team", "away_team", "result").iter_rows():
            if t not in (home, away):
                continue
            m = res if t == home else -res
            w, l, ties = w + (m > 0), l + (m < 0), ties + (m == 0)
            out.add(f"{w}-{l}-{ties}" if ties else f"{w}-{l}")
            out.add(f"{w}-{l}-{ties}")
    return out


@dataclass
class Context:
    """What the checks compare a record against."""

    home: str
    away: str
    roster: dict[str, set[str]]
    records: set[str]  # every season record either team had
    games_played: int  # most games either team has played
    opened: set[str] | None = None  # normalized URLs the model opened; None = don't check
    pages: dict[str, Any] = field(default_factory=dict)  # url -> Fetcher Page (code's own read)
    known_as_of: date | None = None
    window_days: int = 9
    extra_text: str = ""  # game context the text may use (names, week, teams)
    on_page_drops: bool = False  # False: a miss is flagged and counted, the item stays


# ------------------------------------------------------------------------------------ checks


def wrong_team(text: str, team: str | None, ctx: Context, *, strict: bool) -> str | None:
    """The first name in `text` the roster places elsewhere: strict = must be on `team`; else on
    either team of the game. None when everything checks out (or the name is on no roster)."""
    game = {ctx.home, ctx.away}
    for n in names_in(text):
        teams = ctx.roster.get(n)
        if not teams:
            continue
        if strict and team and team not in teams:
            return f"{n} ({'/'.join(sorted(teams))}) under {team}"
        if not teams & game:
            return f"{n} ({'/'.join(sorted(teams))}) not on {ctx.away} or {ctx.home}"
    return None


def bad_record(text: str, ctx: Context) -> str | None:
    """A season record in `text` neither team had. Scores (more games than played) and splits
    ("0-4 at home") are left alone."""
    for m in RECORD.finditer(text or ""):
        w, l, t = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        if w + l + t > ctx.games_played or SPLIT_AFTER.match(text, m.end()):
            continue
        if m.group(0) not in ctx.records:
            return m.group(0)
    return None


def _page_text(urls: list[str], ctx: Context) -> str | None:
    """Joined text of the cited pages code could read, or None when it could read none of them."""
    texts = [ctx.pages[u].text for u in urls if u in ctx.pages and ctx.pages[u].ok]
    return "\n".join(texts) if texts else None


def _page_date(url: str, ctx: Context) -> date | None:
    p = ctx.pages.get(url)
    return p.published if p is not None and p.ok else None


def _url_ok(url: str, ctx: Context) -> str | None:
    if ctx.opened is not None and norm_url(url) not in ctx.opened:
        return "not opened"
    d = _page_date(url, ctx)
    if d and ctx.known_as_of and not (0 <= (ctx.known_as_of - d).days <= ctx.window_days):
        return "outside window"
    return None


def _text_issue(text: str, team: str | None, ctx: Context, *, strict: bool, line_ok: bool, urls: list[str]) -> str | None:  # fmt: skip
    if not line_ok and LINE.search(text):
        return "line"
    if why := wrong_team(text, team, ctx, strict=strict):
        return f"team: {why}"
    if why := bad_record(text, ctx):
        return f"record {why}"
    src = _page_text(urls, ctx)
    if src is not None and (why := _unsupported(text, src + "\n" + ctx.extra_text)):
        return f"not on page: {why}"
    return None


def _sentences(text: str, team: str | None, ctx: Context, urls: list[str], drops: Counter, log: list) -> str:  # fmt: skip
    keep = []
    for s in SENTENCE.split(text.strip()):
        why = _text_issue(s, team, ctx, strict=False, line_ok=False, urls=urls)
        flag = bool(why) and why.startswith("not on page") and not ctx.on_page_drops
        if why:
            drops[f"{'flag ' if flag else ''}sentence: {why.split(':')[0]}"] += 1
            log.append(("flag sentence" if flag else "sentence", team, why, s))
        if not why or flag:
            keep.append(s)
    return " ".join(keep)


def apply(rec: dict, ctx: Context) -> tuple[dict, Counter, list]:
    """Drop what fails; return (record, drops by reason, [(where, team, why, text)]). Flags that
    don't drop are counted as "flag <where>: ..." and logged the same way."""
    drops: Counter = Counter()
    log: list = []

    def gone(where: str, team, why: str, text: str) -> bool:
        """Count the issue; True when the item goes."""
        flag = why.startswith("not on page") and not ctx.on_page_drops
        drops[f"{'flag ' if flag else ''}{where}: {why.split(':')[0]}"] += 1
        log.append((f"flag {where}" if flag else where, team, why, text))
        return not flag

    claims = []
    for c in rec.get("claims", []):
        url = str(c["source_url"])
        if why := _url_ok(url, ctx):
            gone("claim", c.get("team"), why, c["claim"])
            continue
        if d := _page_date(url, ctx):  # code's date wins over the model's
            c["published_at"] = d.isoformat()
        elif c.get("published_at") and ctx.known_as_of:
            pd = date.fromisoformat(str(c["published_at"])[:10])
            if not 0 <= (ctx.known_as_of - pd).days <= ctx.window_days:
                gone("claim", c.get("team"), "outside window", c["claim"])
                continue
        why = _text_issue(c["claim"], c.get("team"), ctx, strict=False, line_ok=c["category"] == "public", urls=[url])  # fmt: skip
        if why and gone("claim", c.get("team"), why, c["claim"]):
            continue
        claims.append(c)
    rec["claims"] = claims

    cited = {str(c["source_url"]) for c in claims}
    for side in ("home", "away"):
        t = rec[side]
        team = t["team"]
        notes = []
        for n in t.get("notes", []):
            urls = [str(n["source_url"])] if n.get("source_url") else []
            why = next((w for u in urls if (w := _url_ok(u, ctx))), None) or _text_issue(
                n["text"], team, ctx, strict=n["kind"] == "injury", line_ok=False, urls=urls)  # fmt: skip
            if not (why and gone("note", team, why, n["text"])):
                notes.append(n)
                cited |= set(urls)
        t["notes"] = notes
        trends = []
        for x in t.get("scheme_trends", []):
            x["sources"] = [u for u in map(str, x["sources"]) if not _url_ok(u, ctx)]
            why = "no source left" if not x["sources"] else _text_issue(
                x["trend"], team, ctx, strict=False, line_ok=False, urls=x["sources"])  # fmt: skip
            if not (why and gone("trend", team, why, x["trend"])):
                trends.append(x)
                cited |= set(x["sources"])
        t["scheme_trends"] = trends
        absences = []
        for a in t.get("key_absences", []):
            if why := wrong_team(a, team, ctx, strict=True):
                gone("absence", team, f"team: {why}", a)
            else:
                absences.append(a)
        t["key_absences"] = absences
        # v3 countable facts (ADR 0032): on the team's roster, and the starter with a claim
        if t.get("qb_named_starter"):
            q = t["qb_named_starter"]
            last = norm_name(q).split()[-1] if norm_name(q) else ""
            if not on_roster(q, team, ctx.roster):
                gone("qb_named", team, f"team: {q} not on the {team} roster", q)
                t["qb_named_starter"] = None
            elif not any(c["category"] == "qb" and c.get("team") == team and last
                         and last in c["claim"].lower().replace("’", "'") for c in claims):  # fmt: skip
                gone("qb_named", team, "no claim", q)
                t["qb_named_starter"] = None
        out = []
        for n in t.get("starters_ruled_out", []):
            if on_roster(n, team, ctx.roster):
                out.append(n)
            else:
                gone("ruled_out", team, f"team: {n} not on the {team} roster", n)
        t["starters_ruled_out"] = out
        if t.get("qb_name") and (why := wrong_team(t["qb_name"], team, ctx, strict=True)):
            gone("qb", team, f"team: {why}", t["qb_name"])
            t["qb_name"], t["qb_status"] = None, 2

    matchups = []
    for m in rec.get("matchup_notes", []):
        m["sources"] = [u for u in map(str, m["sources"]) if not _url_ok(u, ctx)]
        m["support"] = min(m["support"], len(m["sources"]))
        why = "no source left" if not m["sources"] else _text_issue(
            m["text"], None, ctx, strict=False, line_ok=False, urls=m["sources"])  # fmt: skip
        if not (why and gone("matchup", None, why, m["text"])):
            matchups.append(m)
            cited |= set(m["sources"])
    rec["matchup_notes"] = matchups

    # summaries and the consensus cite nothing per sentence: check them against every kept page
    every = sorted(cited)
    for side in ("home", "away"):
        rec[side]["summary"] = _sentences(rec[side]["summary"], rec[side]["team"], ctx, every, drops, log)  # fmt: skip
    rec["consensus_narrative"] = _sentences(
        rec["consensus_narrative"], None, ctx, every, drops, log
    )
    return rec, drops, log
