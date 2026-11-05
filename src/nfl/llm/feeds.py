"""Known sources for the narrative research: RSS feeds and the Open-Meteo forecast.

General web search is for open-ended questions. What each team's injuries and news are, and what
the weather will be, have known homes, so they come from here and cost no search query. A
team/kind with nothing in its feeds falls back to a search (`research.gather`).

`Feeds` reads each feed once per pass and returns items as `SearchResult`s, so they go through the
same page fetch, date window and extraction as search results. Feed text is never used directly.
"""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from functools import cache
from typing import Any
from urllib.parse import urlencode

import httpx

from nfl.features.environment import STADIUMS_CSV
from nfl.llm.fetch import Fetcher
from nfl.llm.search import SearchResult

TEAM_SITES = {
    "ARI": "azcardinals.com", "ATL": "atlantafalcons.com", "BAL": "baltimoreravens.com",
    "BUF": "buffalobills.com", "CAR": "panthers.com", "CHI": "chicagobears.com",
    "CIN": "bengals.com", "CLE": "clevelandbrowns.com", "DAL": "dallascowboys.com",
    "DEN": "denverbroncos.com", "DET": "detroitlions.com", "GB": "packers.com",
    "HOU": "houstontexans.com", "IND": "colts.com", "JAX": "jaguars.com", "KC": "chiefs.com",
    "LV": "raiders.com", "LAC": "chargers.com", "LA": "therams.com", "MIA": "miamidolphins.com",
    "MIN": "vikings.com", "NE": "patriots.com", "NO": "neworleanssaints.com", "NYG": "giants.com",
    "NYJ": "newyorkjets.com", "PHI": "philadelphiaeagles.com", "PIT": "steelers.com",
    "SF": "49ers.com", "SEA": "seahawks.com", "TB": "buccaneers.com", "TEN": "tennesseetitans.com",
    "WAS": "commanders.com",
}  # fmt: skip
LEAGUE_FEEDS = (
    "https://sports.yahoo.com/nfl/rss.xml",
    "https://www.nbcsports.com/profootballtalk.atom",
)
INJURY = re.compile(
    r"injur|questionable|doubtful|ruled out|inactive|practice|limited|concussion|\bIR\b|activated",
    re.IGNORECASE,
)
ATOM = "{http://www.w3.org/2005/Atom}"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_FIELDS = "temperature_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m"
# Schedule names that differ from stadiums.csv (2026).
STADIUM_NAMES = {
    "Bernabeu": "Estadio Santiago Bernabeu",
    "Estadio Banorte": "Estadio Azteca",
    "FC Bayern Munich Stadium": "Allianz Arena (Munich)",
    "Highmark Stadium": "Highmark Stadium (Orchard Park)",
    "Huntington Bank Field": "Cleveland Browns Stadium",
    "Reliant Stadium": "NRG Stadium",
}


@dataclass(frozen=True)
class FeedItem:
    url: str
    title: str
    summary: str
    published: date | None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()  # RSS
    except TypeError, ValueError:
        pass
    try:
        return datetime.fromisoformat(value.strip()).date()  # Atom
    except ValueError:
        return None


def _text(node: ET.Element, tag: str) -> str:
    return (node.findtext(tag) or "").strip()


def parse(xml: bytes) -> list[FeedItem]:
    """The items of an RSS or Atom document; a malformed one has none."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out = []
    for n in root.iter("item"):
        out.append(FeedItem(_text(n, "link"), _text(n, "title"), _text(n, "description"),
                            _date(n.findtext("pubDate"))))  # fmt: skip
    for n in root.iter(f"{ATOM}entry"):
        link = next((x.get("href") for x in n.findall(f"{ATOM}link")
                     if x.get("rel", "alternate") == "alternate"), "")  # fmt: skip
        out.append(FeedItem(link or "", _text(n, f"{ATOM}title"), _text(n, f"{ATOM}summary"),
                            _date(n.findtext(f"{ATOM}published") or n.findtext(f"{ATOM}updated"))))  # fmt: skip
    return [i for i in out if i.url.startswith(("http://", "https://"))]


class Feeds:
    def __init__(self, fetcher: Fetcher, window_days: int) -> None:
        self.fetcher = fetcher
        self.window = timedelta(days=window_days)
        self._items: dict[str, list[FeedItem]] = {}

    def _read(self, url: str) -> list[FeedItem]:
        if url not in self._items:
            raw = self.fetcher.raw(url)
            self._items[url] = parse(raw) if raw else []
        return self._items[url]

    def team_items(self, team: str, full_name: str, today: date) -> list[FeedItem]:
        """The team's own feed plus league items naming it, inside the window, newest first."""
        nickname = full_name.split()[-1]
        names = re.compile(rf"\b({re.escape(full_name)}|{re.escape(nickname)})\b")
        items = list(self._read(f"https://www.{TEAM_SITES[team]}/rss/news")) if team in TEAM_SITES else []  # fmt: skip
        for feed in LEAGUE_FEEDS:
            items += [i for i in self._read(feed) if names.search(f"{i.title} {i.summary}")]
        seen: set[str] = set()
        kept = []
        for i in items:
            if i.url not in seen and (i.published is None or i.published >= today - self.window):
                seen.add(i.url)
                kept.append(i)
        return sorted(kept, key=lambda i: i.published or date.min, reverse=True)

    def pools(self, team: str, full_name: str, today: date) -> dict[str, list[SearchResult]]:
        """{"injury": [...], "news": [...]} for one team."""
        out: dict[str, list[SearchResult]] = {"injury": [], "news": []}
        for i in self.team_items(team, full_name, today):
            kind = "injury" if INJURY.search(i.title) else "news"
            out[kind].append(SearchResult(i.url, i.title, i.summary, i.published, ("feed",)))
        return out


@cache
def _stadiums() -> dict[str, tuple[float, float]]:
    with STADIUMS_CSV.open() as f:
        return {r["name"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)}


def forecast(stadium: str | None, kickoff_utc: datetime, http: httpx.Client | None = None) -> tuple[str, str] | None:  # fmt: skip
    """(source url, plain-text forecast at kickoff) from Open-Meteo, or None when the stadium isn't
    in stadiums.csv, the game is past the forecast's range, or the request fails."""
    where = _stadiums().get(STADIUM_NAMES.get(stadium or "", stadium or ""))
    if where is None:
        return None
    day = kickoff_utc.date().isoformat()
    url = f"{FORECAST_URL}?" + urlencode({
        "latitude": where[0], "longitude": where[1], "hourly": FORECAST_FIELDS, "timezone": "UTC",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "start_date": day, "end_date": day,
    })  # fmt: skip
    client = http or httpx.Client(timeout=15.0)
    try:
        resp = client.get(url)
        hourly: dict[str, Any] = resp.json()["hourly"] if resp.status_code == 200 else {}
        i = hourly["time"].index(f"{kickoff_utc:%Y-%m-%dT%H}:00")
        temp, rain, wind, gusts = (hourly[k][i] for k in FORECAST_FIELDS.split(","))
    except KeyError, ValueError, TypeError, httpx.HTTPError:
        return None
    finally:
        if http is None:
            client.close()
    if None in (temp, wind):
        return None
    return url, (
        f"Open-Meteo forecast for {stadium} at kickoff on {day}: temperature {temp:.0f} F, "
        f"chance of precipitation {rain if rain is not None else 'unknown'} percent, wind "
        f"{wind:.0f} mph, gusts {gusts if gusts is not None else 'unknown'} mph."
    )
