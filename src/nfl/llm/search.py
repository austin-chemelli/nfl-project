"""Web search: Tavily when `TAVILY_API_KEY` is set, the self-hosted SearXNG otherwise (M6.2L).

`search` runs one query and returns deduplicated `SearchResult`s in the engine's order. URLs are
normalized (fragment stripped, query string kept) and only http(s) URLs are returned. A Tavily
failure (out of credits, rate limit, network) logs a warning and falls back to SearXNG.

SearXNG scrapes public engines from one home IP, so they block it: 2026-11-04 lost 7 of 15 games
that way. It still answers 200 with no results, naming the engines in `unresponsive_engines`, so
that case raises `EnginesBlocked`, which is not the same as a query with no hits.

Connection errors, timeouts and 5xx are retried once after a short pause; anything else raises
`SearchError` carrying the HTTP status or the exception type name (never the URL or the key).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urldefrag, urlparse

import httpx

log = logging.getLogger(__name__)

RETRY_PAUSE_S = 2.0
QUERY_PAUSE_S = 3.0  # between queries in a pass; the blocks came from 17-query bursts
TAVILY_URL = "https://api.tavily.com/search"
BLOCK_WORDS = ("suspended", "too many", "captcha", "denied")


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    published: date | None
    engines: tuple[str, ...]


class SearchError(RuntimeError):
    pass


class EnginesBlocked(SearchError):
    """SearXNG returned nothing because its engines refused it, not because nothing matched."""


def paced(fn: Callable[..., list[SearchResult]], pause_s: float = QUERY_PAUSE_S, sleep: Callable[[float], None] = time.sleep) -> Callable[..., list[SearchResult]]:  # fmt: skip
    """`fn`, waiting so that calls start at least `pause_s` apart."""
    last: list[float] = []

    def call(*args: Any, **kw: Any) -> list[SearchResult]:
        if last and (wait := pause_s - (time.monotonic() - last[0])) > 0:
            sleep(wait)
        last[:] = [time.monotonic()]
        return fn(*args, **kw)

    return call


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _resolve_base(base_url: str | None) -> str:
    base = base_url or os.environ.get("SEARX_URL") or ""
    if not base or "<" in base:
        raise SearchError("SEARX_URL is not set (or still the .env.example placeholder)")
    return base.rstrip("/")


def _get_json(
    client: httpx.Client, url: str, params: dict[str, str], sleep: Callable[[float], None]
) -> dict[str, Any]:
    last = "unknown"
    for attempt in range(2):
        try:
            resp = client.get(url, params=params)
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last = type(e).__name__
        else:
            if resp.status_code < 400:
                try:
                    body = resp.json()
                except ValueError as e:
                    raise SearchError(f"invalid JSON from SearXNG ({type(e).__name__})") from e
                if not isinstance(body, dict):
                    raise SearchError("unexpected SearXNG response shape")
                return body
            last = f"http {resp.status_code}"
            if resp.status_code < 500:
                raise SearchError(f"SearXNG request failed: {last}")
        if attempt == 0:
            sleep(RETRY_PAUSE_S)
    raise SearchError(f"SearXNG request failed after retry: {last}")


def _clean(url: Any) -> str | None:
    """The URL without its fragment, or None unless it is http(s)."""
    out = urldefrag(str(url or "").strip())[0]
    return out if urlparse(out).scheme in ("http", "https") and urlparse(out).netloc else None


def _tavily(query: str, key: str, time_range: str, max_results: int, client: httpx.Client) -> list[SearchResult]:  # fmt: skip
    body = {"query": query, "search_depth": "basic", "topic": "general", "time_range": time_range,
            "max_results": max_results, "include_answer": False, "include_published_date": True}  # fmt: skip
    try:
        resp = client.post(TAVILY_URL, json=body, headers={"Authorization": f"Bearer {key}"})
    except (httpx.TransportError, httpx.TimeoutException) as e:
        raise SearchError(f"Tavily request failed: {type(e).__name__}") from None
    if resp.status_code != 200:
        raise SearchError(f"Tavily request failed: http {resp.status_code}")
    try:
        rows = resp.json().get("results") or []
    except (ValueError, AttributeError) as e:
        raise SearchError(f"invalid JSON from Tavily ({type(e).__name__})") from None
    out: dict[str, SearchResult] = {}
    for r in rows:
        if isinstance(r, dict) and (url := _clean(r.get("url"))) and url not in out:
            out[url] = SearchResult(url, str(r.get("title") or ""), str(r.get("content") or ""),
                                    _parse_date(r.get("published_date")), ("tavily",))  # fmt: skip
    return list(out.values())[:max_results]


def search(
    query: str,
    *,
    base_url: str | None = None,
    time_range: str = "month",
    max_results: int = 8,
    http: httpx.Client | None = None,
    timeout_s: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[SearchResult]:
    key = os.environ.get("TAVILY_API_KEY") or ""
    if key and "<" not in key:
        client = http or httpx.Client(timeout=timeout_s)
        try:
            return _tavily(query, key, time_range, max_results, client)
        except SearchError as e:
            log.warning("%s; using SearXNG for this query", e)
        finally:
            if http is None:
                client.close()
    base = _resolve_base(base_url)
    client = http or httpx.Client(timeout=timeout_s)
    params = {"q": query, "format": "json", "time_range": time_range, "language": "en"}
    try:
        body = _get_json(client, f"{base}/search", params, sleep)
    finally:
        if http is None:
            client.close()

    out: list[SearchResult] = []
    seen: set[str] = set()
    for r in body.get("results") or []:
        if not isinstance(r, dict):
            continue
        url = _clean(r.get("url"))
        if url is None or url in seen:
            continue
        seen.add(url)
        out.append(
            SearchResult(
                url=url,
                title=str(r.get("title") or ""),
                snippet=str(r.get("content") or ""),
                published=_parse_date(r.get("publishedDate")),
                engines=tuple(str(e) for e in r.get("engines") or []),
            )
        )
        if len(out) >= max_results:
            break
    if not out:
        bad = [" ".join(str(x) for x in e) for e in body.get("unresponsive_engines") or []]
        if any(w in b.lower() for b in bad for w in BLOCK_WORDS):
            raise EnginesBlocked(f"search engines blocked: {'; '.join(bad)}")
    return out
