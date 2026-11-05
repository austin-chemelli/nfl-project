"""RSS and Atom parsing, team filtering and the Open-Meteo forecast (MockTransport only)."""

from __future__ import annotations

from datetime import date, datetime

import httpx

from nfl.llm.feeds import LEAGUE_FEEDS, STADIUM_NAMES, Feeds, _stadiums, forecast, parse

RSS = b"""<rss version="2.0"><channel><title>Eagles</title>
<item><title>Giants vs. Eagles Injury Report</title><link>https://www.philadelphiaeagles.com/a</link>
<description>Wednesday</description><pubDate>Wed, 04 Nov 2026 23:24:07 GMT</pubDate></item>
<item><title>Five takeaways</title><link>https://www.philadelphiaeagles.com/b</link>
<pubDate>Tue, 03 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Old story</title><link>https://www.philadelphiaeagles.com/c</link>
<pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>No link</title></item>
</channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>PFT</title>
<entry><title>Eagles QB limited in practice</title><link rel="alternate" href="https://pft.example/1"/>
<published>2026-11-05T00:41:06Z</published></entry>
<entry><title>Bears sign a kicker</title><link href="https://pft.example/2"/>
<updated>2026-11-04T10:00:00Z</updated></entry>
</feed>"""


class _Fetcher:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies
        self.reads: list[str] = []

    def raw(self, url: str) -> bytes | None:
        self.reads.append(url)
        return self.bodies.get(url)


def _feeds() -> tuple[Feeds, _Fetcher]:
    f = _Fetcher({"https://www.philadelphiaeagles.com/rss/news": RSS, LEAGUE_FEEDS[1]: ATOM})
    return Feeds(f, 9), f


def test_parse_rss_and_atom() -> None:
    rss = parse(RSS)
    assert [i.url[-1] for i in rss] == ["a", "b", "c"]
    assert rss[0].published == date(2026, 11, 4)
    atom = parse(ATOM)
    assert [(i.url, i.published) for i in atom] == [
        ("https://pft.example/1", date(2026, 11, 5)),
        ("https://pft.example/2", date(2026, 11, 4)),
    ]


def test_malformed_feed_is_empty() -> None:
    assert parse(b"<html><body>nope") == []


def test_pools_split_by_kind_keep_the_window_and_name_the_team() -> None:
    feeds, _ = _feeds()
    pools = feeds.pools("PHI", "Philadelphia Eagles", date(2026, 11, 5))
    assert [r.url for r in pools["injury"]] == [
        "https://pft.example/1",  # newest first; the Bears item isn't theirs
        "https://www.philadelphiaeagles.com/a",
    ]
    assert [r.url for r in pools["news"]] == ["https://www.philadelphiaeagles.com/b"]
    assert pools["news"][0].published == date(2026, 11, 3)


def test_each_feed_is_read_once_per_pass() -> None:
    feeds, f = _feeds()
    for _ in range(2):
        feeds.pools("PHI", "Philadelphia Eagles", date(2026, 11, 5))
    assert len(f.reads) == len(set(f.reads))


def test_a_dead_feed_leaves_the_pools_empty() -> None:
    feeds = Feeds(_Fetcher({}), 9)
    assert feeds.pools("BUF", "Buffalo Bills", date(2026, 11, 5)) == {"injury": [], "news": []}


def _wx(status: int = 200, hours: list[str] | None = None) -> httpx.Client:
    body = {"hourly": {"time": hours or ["2026-11-08T17:00", "2026-11-08T18:00"],
                       "temperature_2m": [50.2, 48.6], "precipitation_probability": [10, 30],
                       "wind_speed_10m": [8.0, 12.4], "wind_gusts_10m": [15.0, 21.0]}}  # fmt: skip
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))


def test_forecast_reads_the_kickoff_hour() -> None:
    url, text = forecast("Lincoln Financial Field", datetime(2026, 11, 8, 18, 0), _wx())
    assert "api.open-meteo.com" in url
    assert "temperature 49 F" in text and "30 percent" in text and "wind 12 mph" in text


def test_kickoff_at_a_quarter_past_uses_that_hour() -> None:
    assert "wind 12 mph" in forecast("Lincoln Financial Field", datetime(2026, 11, 8, 18, 15), _wx())[1]  # fmt: skip


def test_no_forecast_without_a_stadium_or_data() -> None:
    kick = datetime(2026, 11, 8, 18, 0)
    assert forecast("Unknown Park", kick, _wx()) is None
    assert forecast(None, kick, _wx()) is None
    assert forecast("Lincoln Financial Field", kick, _wx(status=400)) is None
    assert forecast("Lincoln Financial Field", kick, _wx(hours=["2026-11-08T17:00", "2026-11-08T19:00"])) is None  # fmt: skip


def test_every_schedule_alias_has_coordinates() -> None:
    assert all(name in _stadiums() for name in STADIUM_NAMES.values())
