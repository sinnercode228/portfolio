"""Polite async HTTP fetcher.

* concurrency limit      — asyncio.Semaphore
* rate limit             — at most N requests per second across all tasks
* retries with backoff   — exponential + jitter, honours `Retry-After`
* caching                — optional DiskCache, cache hits skip the network
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from bookscraper import USER_AGENT
from bookscraper.cache import DiskCache

log = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    def __init__(self, url: str, reason: str, status: int | None = None) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason
        self.status = status


class RateLimiter:
    """Spaces request *starts* at least `1 / rate` seconds apart."""

    def __init__(self, rate_per_sec: float) -> None:
        self.interval = 1.0 / rate_per_sec if rate_per_sec and rate_per_sec > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def wait(self) -> None:
        if not self.interval:
            return
        loop = asyncio.get_running_loop()
        async with self._lock:
            now = loop.time()
            if self._next_slot > now:
                await asyncio.sleep(self._next_slot - now)
                now = self._next_slot
            self._next_slot = now + self.interval


@dataclass
class FetchStats:
    requests: int = 0
    cache_hits: int = 0
    retries: int = 0
    failures: int = 0
    statuses: dict[int, int] = field(default_factory=dict)


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class Fetcher:
    """Use as an async context manager:

    >>> async with Fetcher(concurrency=5, rate=4) as f:   # doctest: +SKIP
    ...     html = await f.get_text("https://books.toscrape.com/")
    """

    def __init__(
        self,
        *,
        concurrency: int = 5,
        rate: float = 4.0,
        retries: int = 3,
        timeout: float = 20.0,
        backoff_base: float = 0.5,
        backoff_max: float = 30.0,
        cache: DiskCache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.retries = max(0, retries)
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.cache = cache
        self.stats = FetchStats()
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._limiter = RateLimiter(rate)
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en", **(headers or {})},
            limits=httpx.Limits(max_connections=max(1, concurrency)),
            transport=transport,
        )

    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _backoff(self, attempt: int) -> float:
        # attempt=1 -> base, 2 -> 2*base, 3 -> 4*base ... with "equal jitter"
        delay = min(self.backoff_max, self.backoff_base * 2 ** (attempt - 1))
        return delay / 2 + random.uniform(0, delay / 2)

    async def get_text(self, url: str, *, use_cache: bool = True) -> str:
        if use_cache and self.cache is not None:
            cached = await self.cache.get(url)
            if cached is not None:
                self.stats.cache_hits += 1
                log.debug("cache hit %s", url)
                return cached

        last_reason = "unknown error"
        last_status: int | None = None
        for attempt in range(1, self.retries + 2):
            retry_after: float | None = None
            async with self._semaphore:
                await self._limiter.wait()
                self.stats.requests += 1
                try:
                    response = await self._client.get(url)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_reason, last_status = f"{type(exc).__name__}: {exc}".rstrip(": "), None
                else:
                    status = response.status_code
                    self.stats.statuses[status] = self.stats.statuses.get(status, 0) + 1
                    if status == 200:
                        # Decode explicitly: the sandbox sends no charset header.
                        text = response.content.decode(response.charset_encoding or "utf-8", errors="replace")
                        if self.cache is not None:
                            try:
                                await self.cache.set(url, text)
                            except OSError as exc:  # full disk etc.: the page itself is fine
                                log.warning("cache write failed for %s: %s", url, exc)
                        return text
                    last_reason, last_status = f"HTTP {status}", status
                    if status not in RETRY_STATUSES:
                        self.stats.failures += 1
                        raise FetchError(url, last_reason, status)
                    retry_after = _retry_after_seconds(response.headers.get("Retry-After"))

            if attempt > self.retries:
                break
            delay = self._backoff(attempt)
            if retry_after is not None:
                delay = min(self.backoff_max, max(delay, retry_after))
            self.stats.retries += 1
            log.warning("retry %d/%d in %.1fs for %s (%s)", attempt, self.retries, delay, url, last_reason)
            await asyncio.sleep(delay)  # sleep *outside* the semaphore

        self.stats.failures += 1
        raise FetchError(url, f"gave up after {self.retries + 1} attempts ({last_reason})", last_status)
