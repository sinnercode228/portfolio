"""Fetcher tests: retries/backoff, non-retryable errors, cache, rate & concurrency limits.
All offline — httpx.MockTransport stands in for the network."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from bookscraper.cache import DiskCache
from bookscraper.fetcher import Fetcher, FetchError, RateLimiter, _retry_after_seconds

URL = "https://books.toscrape.com/index.html"


def make_fetcher(handler, **kw) -> Fetcher:
    kw.setdefault("rate", 0)            # no rate limit unless a test wants one
    kw.setdefault("backoff_base", 0.001)  # fast retries in tests
    return Fetcher(transport=httpx.MockTransport(handler), **kw)


def test_success_decodes_utf8_without_charset():
    def handler(request):
        return httpx.Response(200, content="£51.77 — ok".encode(), headers={"content-type": "text/html"})

    async def go():
        async with make_fetcher(handler) as f:
            return await f.get_text(URL), f.stats

    text, stats = asyncio.run(go())
    assert text == "£51.77 — ok"
    assert stats.requests == 1 and stats.retries == 0


def test_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] <= 2 else httpx.Response(200, text="ok")

    async def go():
        async with make_fetcher(handler, retries=3) as f:
            return await f.get_text(URL), f.stats

    text, stats = asyncio.run(go())
    assert text == "ok"
    assert calls["n"] == 3
    assert stats.retries == 2 and stats.failures == 0


def test_network_errors_are_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, text="ok")

    async def go():
        async with make_fetcher(handler, retries=2) as f:
            return await f.get_text(URL)

    assert asyncio.run(go()) == "ok"
    assert calls["n"] == 2


def test_gives_up_after_max_retries():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500)

    async def go():
        async with make_fetcher(handler, retries=2) as f:
            await f.get_text(URL)

    with pytest.raises(FetchError) as info:
        asyncio.run(go())
    assert calls["n"] == 3  # 1 try + 2 retries
    assert info.value.status == 500
    assert "gave up after 3 attempts" in str(info.value)


def test_404_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    async def go():
        async with make_fetcher(handler, retries=5) as f:
            await f.get_text(URL)

    with pytest.raises(FetchError) as info:
        asyncio.run(go())
    assert calls["n"] == 1
    assert info.value.status == 404


def test_retry_after_header_is_respected():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0.3"})
        return httpx.Response(200, text="ok")

    async def go():
        async with make_fetcher(handler, retries=1) as f:
            start = time.perf_counter()
            await f.get_text(URL)
            return time.perf_counter() - start

    assert asyncio.run(go()) >= 0.28


@pytest.mark.parametrize(("value", "expected"), [("5", 5.0), ("0", 0.0), ("junk", None), (None, None)])
def test_retry_after_parsing(value, expected):
    assert _retry_after_seconds(value) == expected


def test_retry_after_http_date_in_past_is_zero():
    assert _retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0


def test_cache_hit_skips_network(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=f"body {calls['n']}")

    async def go():
        cache = DiskCache(tmp_path / "cache")
        async with make_fetcher(handler, cache=cache) as f:
            first = await f.get_text(URL)
            second = await f.get_text(URL)
            return first, second, f.stats

    first, second, stats = asyncio.run(go())
    assert first == second == "body 1"
    assert calls["n"] == 1
    assert stats.cache_hits == 1


def test_cache_ttl_expiry(tmp_path):
    cache = DiskCache(tmp_path, ttl_seconds=0.05)
    cache.set_sync(URL, "hello")
    assert cache.get_sync(URL) == "hello"
    time.sleep(0.08)
    assert cache.get_sync(URL) is None
    assert DiskCache(tmp_path, ttl_seconds=0).get_sync(URL) == "hello"  # 0 = never expires


def test_errors_are_not_cached(tmp_path):
    def handler(request):
        return httpx.Response(404)

    async def go():
        async with make_fetcher(handler, cache=DiskCache(tmp_path)) as f:
            with pytest.raises(FetchError):
                await f.get_text(URL)

    asyncio.run(go())
    assert DiskCache(tmp_path).get_sync(URL) is None


def test_rate_limiter_spaces_requests():
    async def go():
        limiter = RateLimiter(20)  # one request per 50 ms
        start = time.perf_counter()
        await asyncio.gather(*(limiter.wait() for _ in range(6)))
        return time.perf_counter() - start

    assert asyncio.run(go()) >= 0.24  # 5 gaps * 50 ms, minus timer slack


def test_concurrency_limit_is_enforced():
    state = {"now": 0, "peak": 0}

    async def handler(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.02)
        state["now"] -= 1
        return httpx.Response(200, text="ok")

    async def go():
        async with make_fetcher(handler, concurrency=3) as f:
            await asyncio.gather(*(f.get_text(f"{URL}?p={i}") for i in range(12)))

    asyncio.run(go())
    assert state["peak"] == 3


def test_cache_write_failure_is_not_fatal(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")  # the cache "directory" is a file -> every write fails

    def handler(request):
        return httpx.Response(200, text="ok")

    async def go():
        async with make_fetcher(handler, cache=DiskCache(blocker)) as f:
            return await f.get_text(URL)

    assert asyncio.run(go()) == "ok"


def test_cache_leaves_no_temp_files(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set_sync(URL, "a")
    cache.set_sync(URL, "b")
    assert cache.get_sync(URL) == "b"
    assert not list(tmp_path.rglob("*.tmp"))
