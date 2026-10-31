"""SearXNG client and polite page fetcher (MockTransport only; no network)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest

from nfl.config import Paths
from nfl.llm.fetch import Fetcher
from nfl.llm.search import SearchError, search

BASE = "http://searx.test:8080"

PARA = (
    "The Green Bay Packers listed the starting left tackle as questionable on the Wednesday "
    "injury report after he missed practice with a knee issue, according to the team. "
)
ARTICLE = f"""<html><head><title>Packers injury report: Wednesday update</title>
<meta property="article:published_time" content="2026-10-27T12:00:00Z">
</head><body><nav>Home Sports Menu</nav><article><h1>Packers injury report</h1>
{"".join(f"<p>{PARA}Paragraph {i}.</p>" for i in range(8))}
</article><footer>Copyright</footer></body></html>"""
SHORT = (
    "<html><head><title>Stub</title></head><body><article><p>Subscribe.</p></article></body></html>"
)


def _searx(payload: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))


def test_search_parses_dedupes_and_caps() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://a.com/x#top", "title": "A", "content": "sa",
                     "publishedDate": "2026-10-27T00:00:00", "engines": ["google", "bing"]},
                    {"url": "https://a.com/x", "title": "A dup", "content": "", "engines": []},
                    {"url": "ftp://b.com/f", "title": "ftp", "content": ""},
                    {"url": "https://c.com/?q=1", "title": "C", "content": "sc",
                     "publishedDate": None, "engines": ["bing"]},
                    {"url": "https://d.com/", "title": "D", "content": "sd",
                     "publishedDate": "garbage"},
                ],
                "unresponsive_engines": [],
            },
        )  # fmt: skip

    http = httpx.Client(transport=httpx.MockTransport(handler))
    res = search("packers injuries", base_url=BASE + "/", http=http, max_results=2)
    assert [r.url for r in res] == ["https://a.com/x", "https://c.com/?q=1"]
    assert res[0].published == date(2026, 10, 27)
    assert res[0].engines == ("google", "bing")
    assert res[1].published is None
    q = seen[0].url.params
    assert (q["q"], q["format"], q["time_range"], q["language"]) == (
        "packers injuries", "json", "month", "en",
    )  # fmt: skip
    assert seen[0].url.path == "/search"
    bad_date = search("x", base_url=BASE, http=http, max_results=10)[-1]
    assert bad_date.url == "https://d.com/" and bad_date.published is None


def test_search_placeholder_or_missing_url(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SearchError):
        search("x", base_url="http://<desktop-tailscale-ip>:8080", http=_searx({}))
    monkeypatch.delenv("SEARX_URL", raising=False)
    with pytest.raises(SearchError):
        search("x", http=_searx({}))


def test_search_retries_once_then_succeeds_or_fails() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"results": [{"url": "https://a.com/", "title": "A"}]})

    http = httpx.Client(transport=httpx.MockTransport(flaky))
    res = search("x", base_url=BASE, http=http, sleep=sleeps.append)
    assert len(res) == 1 and calls["n"] == 2 and sleeps == [2.0]

    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    http = httpx.Client(transport=httpx.MockTransport(down))
    with pytest.raises(SearchError, match="ConnectError"):
        search("x", base_url=BASE, http=http, sleep=lambda s: None)

    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    with pytest.raises(SearchError, match="http 400"):
        search("x", base_url=BASE, http=http, sleep=lambda s: None)


class Site:
    """Stub web server recording requests."""

    def __init__(self, robots: str | None = None, page: httpx.Response | None = None) -> None:
        self.robots = robots
        self.page = page or httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, text=ARTICLE
        )
        self.requests: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(str(req.url))
        if req.url.path == "/robots.txt":
            if self.robots is None:
                return httpx.Response(404)
            return httpx.Response(200, text=self.robots)
        return self.page

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def page_requests(self) -> list[str]:
        return [u for u in self.requests if not u.endswith("/robots.txt")]


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def _fetcher(tmp_path, site: Site, **kw) -> Fetcher:
    kw.setdefault("sleep", lambda s: None)
    return Fetcher(Paths(tmp_path), http=site.client(), now=lambda: NOW, **kw)


def test_fetch_extracts_article(tmp_path) -> None:
    site = Site()
    page = _fetcher(tmp_path, site).get("https://news.test/packers")
    assert page.ok and page.reason is None and page.status == 200
    assert page.title and "Packers injury report" in page.title
    assert page.published == date(2026, 10, 27)
    assert "questionable" in page.text and "Copyright" not in page.text
    assert page.fetched_at == NOW and page.fetched_at.tzinfo is not None


def test_fetch_truncates_at_whitespace(tmp_path) -> None:
    page = _fetcher(tmp_path, Site(), max_chars=500).get("https://news.test/p")
    assert page.ok and len(page.text) <= 500 and not page.text.endswith(" ")


def test_cache_hit_makes_no_request(tmp_path) -> None:
    site = Site()
    first = _fetcher(tmp_path, site).get("https://news.test/packers")
    n = len(site.requests)
    site2 = Site()
    second = _fetcher(tmp_path, site2).get("https://news.test/packers")
    assert site2.requests == [] and n > 0
    assert second == first
    # use_cache=False refetches
    third = _fetcher(tmp_path, site2, use_cache=False).get("https://news.test/packers")
    assert third.ok and site2.page_requests()


def test_cache_expires_so_next_week_refetches(tmp_path) -> None:
    from datetime import timedelta

    _fetcher(tmp_path, Site()).get("https://news.test/packers")
    later = Site()
    f = Fetcher(Paths(tmp_path), http=later.client(), now=lambda: NOW + timedelta(days=7))
    page = f.get("https://news.test/packers")
    assert later.page_requests() and page.fetched_at == NOW + timedelta(days=7)


def test_robots_disallow(tmp_path) -> None:
    site = Site(robots="User-agent: *\nDisallow: /private/\n")
    f = _fetcher(tmp_path, site)
    page = f.get("https://news.test/private/story")
    assert not page.ok and page.reason == "robots"
    assert site.page_requests() == []
    assert f.get("https://news.test/public/story").ok
    assert sum(u.endswith("/robots.txt") for u in site.requests) == 1


def test_403_cached_as_not_ok(tmp_path) -> None:
    site = Site(page=httpx.Response(403, text="no"))
    page = _fetcher(tmp_path, site).get("https://news.test/a")
    assert not page.ok and page.reason == "http 403" and page.status == 403
    site2 = Site()
    again = _fetcher(tmp_path, site2).get("https://news.test/a")
    assert site2.requests == [] and again.reason == "http 403"


def test_timeout_not_cached(tmp_path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ReadTimeout("slow")

    f = Fetcher(Paths(tmp_path), http=httpx.Client(transport=httpx.MockTransport(handler)),
                sleep=lambda s: None)  # fmt: skip
    page = f.get("https://news.test/a")
    assert not page.ok and page.reason == "timeout" and page.status is None
    assert not f.cache_path("https://news.test/a").exists()


def test_not_html_and_too_short(tmp_path) -> None:
    pdf = Site(page=httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"x"))
    assert _fetcher(tmp_path, pdf).get("https://news.test/a.pdf").reason == "not html"
    short = Site(page=httpx.Response(200, headers={"content-type": "text/html"}, text=SHORT))
    page = _fetcher(tmp_path, short).get("https://news.test/stub")
    assert not page.ok and page.reason == "too short" and page.text == ""


def test_per_domain_delay_sleeps(tmp_path) -> None:
    sleeps: list[float] = []
    f = _fetcher(tmp_path, Site(), delay_s=1.0, sleep=sleeps.append)
    f.get("https://news.test/one")  # robots.txt, then the page: the page waits out the delay
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1.0
    sleeps.clear()
    f.get("https://news.test/two")  # same domain, robots cached: one wait
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1.0
    sleeps.clear()
    f.get("https://other.test/one")  # new domain: robots has no wait, the page does
    assert len(sleeps) == 1
