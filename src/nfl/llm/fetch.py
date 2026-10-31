"""Polite page fetch, main-text extraction and the page cache (M6.2L).

`Fetcher.get(url)` always returns a `Page` and never raises. Steps: cache lookup, robots.txt check
(per domain, once per Fetcher; unreadable robots means allowed), a per-domain delay, the request,
then trafilatura extraction of the main text, title and publish date. Pages with too little text
(paywall stubs, cookie walls) are `ok=False, reason="too short"`.

Cache: `<root>/raw/web/<sha256(url)[:2]>/<sha256(url)>.json`, the latest snapshot of the page with
its `fetched_at`, reused only within `max_age` (12 h): same-day re-runs hit the cache, next week's
run refetches. Non-ok pages are cached too (a 403 is not retried every run), except timeouts and
connection errors, which are transient.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from nfl.config import Paths

USER_AGENT = "nfl-project-research/0.1 (+https://github.com/austin-chemelli/nfl-project)"
MAX_BYTES = 3 * 1024 * 1024
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


@dataclass
class Page:
    url: str
    final_url: str
    title: str | None
    text: str
    published: date | None
    fetched_at: datetime
    status: int | None
    ok: bool
    reason: str | None


def _to_json(page: Page) -> dict[str, Any]:
    d = asdict(page)
    d["published"] = page.published.isoformat() if page.published else None
    d["fetched_at"] = page.fetched_at.isoformat()
    return d


def _from_json(d: dict[str, Any]) -> Page:
    return Page(
        url=d["url"],
        final_url=d["final_url"],
        title=d.get("title"),
        text=d.get("text", ""),
        published=date.fromisoformat(d["published"]) if d.get("published") else None,
        fetched_at=datetime.fromisoformat(d["fetched_at"]),
        status=d.get("status"),
        ok=bool(d["ok"]),
        reason=d.get("reason"),
    )


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    i = max(cut.rfind(" "), cut.rfind("\n"))
    return (cut[:i] if i > 0 else cut).rstrip()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class Fetcher:
    def __init__(
        self,
        paths: Paths,
        *,
        http: httpx.Client | None = None,
        delay_s: float = 1.0,
        max_chars: int = 8000,
        min_chars: int = 400,
        use_cache: bool = True,
        max_age: timedelta = timedelta(hours=12),
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.paths = paths
        self.http = http or httpx.Client(
            timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        self.delay_s = delay_s
        self.max_chars = max_chars
        self.min_chars = min_chars
        self.use_cache = use_cache
        self.max_age = max_age
        self.sleep = sleep
        self.now = now or (lambda: datetime.now(UTC))
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    # --- cache -------------------------------------------------------------------------------
    def cache_path(self, url: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()
        return self.paths.root / "raw" / "web" / h[:2] / f"{h}.json"

    def _read_cache(self, url: str) -> Page | None:
        path = self.cache_path(url)
        if not path.exists():
            return None
        try:
            return _from_json(json.loads(path.read_text()))
        except OSError, ValueError, KeyError:
            return None

    def _write_cache(self, page: Page) -> None:
        path = self.cache_path(page.url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(_to_json(page), ensure_ascii=False))
            tmp.replace(path)
        except OSError:
            pass

    # --- network -----------------------------------------------------------------------------
    def _throttle(self, domain: str) -> None:
        last = self._last_request.get(domain)
        if last is not None:
            wait = self.delay_s - (time.monotonic() - last)
            if wait > 0:
                self.sleep(wait)
        self._last_request[domain] = time.monotonic()

    def _request(self, url: str, domain: str) -> httpx.Response:
        self._throttle(domain)
        return self.http.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True
        )

    def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = None
            try:
                resp = self._request(f"{origin}/robots.txt", p.netloc)
                if resp.status_code == 200:
                    parser = RobotFileParser()
                    parser.parse(resp.text.splitlines())
            except Exception:  # noqa: BLE001 - unreadable robots means allowed
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    # --- public ------------------------------------------------------------------------------
    def get(self, url: str) -> Page:
        # Expiry matters: hub pages (team injury pages) keep their URL week to week, so a cached
        # copy is reused only within max_age (re-runs the same day), never for next week's run.
        cached = self._read_cache(url) if self.use_cache else None
        if cached is not None and self.now() - cached.fetched_at < self.max_age:
            return cached
        page, transient = self._fetch(url)
        if not transient:
            self._write_cache(page)
        return page

    def _fail(
        self, url: str, reason: str, status: int | None = None, final: str | None = None
    ) -> Page:
        return Page(url, final or url, None, "", None, self.now(), status, False, reason)

    def _fetch(self, url: str) -> tuple[Page, bool]:
        """Return (page, transient). Transient failures are not cached."""
        try:
            if urlparse(url).scheme not in ("http", "https"):
                return self._fail(url, "bad url"), False
            if not self._allowed(url):
                return self._fail(url, "robots"), False
            resp = self._request(url, urlparse(url).netloc)
        except httpx.TimeoutException:
            return self._fail(url, "timeout"), True
        except httpx.TransportError as e:
            return self._fail(url, type(e).__name__), True
        except Exception as e:  # noqa: BLE001 - never raise for a single bad page
            return self._fail(url, type(e).__name__), False

        final = str(resp.url)
        status = resp.status_code
        if not 200 <= status < 300:
            return self._fail(url, f"http {status}", status, final), False
        if "html" not in resp.headers.get("content-type", "").lower():
            return self._fail(url, "not html", status, final), False
        if len(resp.content) > MAX_BYTES:
            return self._fail(url, "too large", status, final), False
        try:
            doc = trafilatura.bare_extraction(resp.text, url=final, with_metadata=True)
        except Exception as e:  # noqa: BLE001
            return self._fail(url, type(e).__name__, status, final), False
        text = (getattr(doc, "text", None) or "").strip() if doc is not None else ""
        title = getattr(doc, "title", None) if doc is not None else None
        published = _parse_date(getattr(doc, "date", None)) if doc is not None else None
        if len(text) < self.min_chars:
            page = self._fail(url, "too short", status, final)
            page.title, page.published = title, published
            return page, False
        page = Page(
            url, final, title, _truncate(text, self.max_chars), published,
            self.now(), status, True, None,
        )  # fmt: skip
        return page, False
