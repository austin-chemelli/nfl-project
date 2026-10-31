"""SearXNG client (M6.2L).

`search` runs one query against the self-hosted SearXNG instance at `SEARX_URL` (JSON output,
English, a time range) and returns deduplicated `SearchResult`s in the engine's order. URLs are
normalized (fragment stripped, query string kept) and only http(s) URLs are returned.

Connection errors, timeouts and 5xx are retried once after a short pause; anything else raises
`SearchError` carrying the HTTP status or the exception type name (never the URL).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urldefrag, urlparse

import httpx

RETRY_PAUSE_S = 2.0


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    published: date | None
    engines: tuple[str, ...]


class SearchError(RuntimeError):
    pass


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
        url = urldefrag(str(r.get("url") or "").strip())[0]
        if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
            continue
        if url in seen:
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
    return out
