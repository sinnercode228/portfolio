"""Crawl orchestration: home -> categories -> listing pages -> product pages."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from bookscraper import USER_AGENT
from bookscraper.fetcher import Fetcher, FetchError
from bookscraper.models import Book, Category
from bookscraper.parsers import (
    ParseError,
    parse_categories,
    parse_listing,
    parse_product,
)

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://books.toscrape.com/"


@dataclass
class CrawlResult:
    books: list[Book] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    categories: list[Category] = field(default_factory=list)


def select_categories(all_categories: list[Category], wanted: list[str] | None) -> list[Category]:
    """Match categories by name or slug, case-insensitive ('Mystery', 'mystery',
    'science-fiction', 'Science Fiction' all work)."""
    if not wanted:
        return list(all_categories)

    def norm(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    index: dict[str, Category] = {}
    for cat in all_categories:
        index.setdefault(norm(cat.name), cat)
        index.setdefault(norm(cat.slug), cat)

    selected: list[Category] = []
    unknown: list[str] = []
    for name in wanted:
        cat = index.get(norm(name))
        if cat is None:
            unknown.append(name)
        elif cat not in selected:
            selected.append(cat)
    if unknown:
        known = ", ".join(c.name for c in all_categories)
        raise ValueError(f"unknown category: {', '.join(unknown)}. Available: {known}")
    return selected


class BookCrawler:
    def __init__(
        self,
        fetcher: Fetcher,
        *,
        base_url: str = DEFAULT_BASE_URL,
        respect_robots: bool = True,
        progress_every: int = 10,
    ) -> None:
        self.fetcher = fetcher
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.respect_robots = respect_robots
        self.progress_every = max(1, progress_every)
        self._robots: RobotFileParser | None = None

    # ---------------------------------------------------------------- robots
    async def _load_robots(self) -> None:
        robots = RobotFileParser()
        try:
            text = await self.fetcher.get_text(urljoin(self.base_url, "robots.txt"))
        except FetchError as exc:
            # No robots.txt (404) means "everything allowed" by convention.
            log.debug("robots.txt unavailable (%s) — assuming allow-all", exc.reason)
            robots.parse([])
        else:
            robots.parse(text.splitlines())
        self._robots = robots

    def allowed(self, url: str) -> bool:
        if not self.respect_robots or self._robots is None:
            return True
        return self._robots.can_fetch(USER_AGENT, url)

    async def _get(self, url: str) -> str:
        if not self.allowed(url):
            raise FetchError(url, "disallowed by robots.txt")
        return await self.fetcher.get_text(url)

    # ------------------------------------------------------------- listings
    async def fetch_categories(self) -> list[Category]:
        if self.respect_robots and self._robots is None:
            await self._load_robots()
        home = urljoin(self.base_url, "index.html")
        return parse_categories(await self._get(home), home)

    async def category_product_urls(
        self, category: Category, limit: int | None = None, errors: list[str] | None = None
    ) -> list[str]:
        """All product URLs of one category. Page 1 tells us the page count,
        the remaining pages are fetched concurrently. Pages that fail after all
        retries are skipped and reported to `errors` (if given)."""

        def report(page_url: str, exc: BaseException) -> None:
            log.error("listing page failed: %s (%s)", page_url, exc)
            if errors is not None:
                errors.append(f"listing {page_url}: {exc}")

        first = parse_listing(await self._get(category.url), category.url)
        urls = list(first.product_urls)
        if limit is not None and len(urls) >= limit:
            return urls[:limit]

        if first.total_pages > 1 and first.next_url:
            per_page = max(1, len(first.product_urls))
            pages_needed = first.total_pages
            if limit is not None:
                pages_needed = min(pages_needed, -(-limit // per_page))  # ceil
            page_urls = [urljoin(category.url, f"page-{n}.html") for n in range(2, pages_needed + 1)]
            results = await asyncio.gather(*(self._get(u) for u in page_urls), return_exceptions=True)
            for page_url, html in zip(page_urls, results, strict=True):
                if isinstance(html, BaseException):
                    report(page_url, html)
                    continue
                try:
                    urls.extend(parse_listing(html, page_url).product_urls)
                except ParseError as exc:
                    report(page_url, exc)
        elif first.next_url:
            # Fallback for sites without "Page X of N": follow `next` links.
            next_url = first.next_url
            while next_url and (limit is None or len(urls) < limit):
                try:
                    page = parse_listing(await self._get(next_url), next_url)
                except (FetchError, ParseError) as exc:
                    report(next_url, exc)  # keep what we already have
                    break
                urls.extend(page.product_urls)
                next_url = page.next_url

        return urls[:limit] if limit is not None else urls

    # ------------------------------------------------------------- products
    async def _fetch_book(self, url: str, category: str) -> Book:
        return parse_product(await self._get(url), url, category=category)

    async def crawl(self, categories: list[str] | None = None, limit: int | None = None) -> CrawlResult:
        result = CrawlResult()
        all_categories = await self.fetch_categories()
        result.categories = select_categories(all_categories, categories)
        log.info("categories: %d selected of %d", len(result.categories), len(all_categories))

        # 1) collect product URLs (category by category, stop at --limit)
        targets: list[tuple[str, str]] = []  # (url, category name)
        seen: set[str] = set()
        for cat in result.categories:
            remaining = None if limit is None else limit - len(targets)
            if remaining is not None and remaining <= 0:
                break
            try:
                urls = await self.category_product_urls(cat, remaining, result.errors)
            except (FetchError, ParseError) as exc:
                result.errors.append(f"category {cat.name}: {exc}")
                log.error("category %s failed: %s", cat.name, exc)
                continue
            new = [u for u in urls if u not in seen]
            seen.update(new)
            targets.extend((u, cat.name) for u in new)
            log.info("  %-22s %4d product links", cat.name, len(new))
        if limit is not None:
            targets = targets[:limit]
        log.info("fetching %d product pages ...", len(targets))

        # 2) fetch product pages concurrently (fetcher enforces the limits)
        done = 0

        async def worker(index: int, url: str, category: str) -> tuple[int, Book | None]:
            nonlocal done
            try:
                book = await self._fetch_book(url, category)
            except (FetchError, ParseError) as exc:
                result.errors.append(f"product {url}: {exc}")
                log.error("product failed: %s", exc)
                book = None
            except Exception as exc:  # one odd page must not kill a long run
                result.errors.append(f"product {url}: unexpected {type(exc).__name__}: {exc}")
                log.exception("product failed unexpectedly: %s", url)
                book = None
            done += 1
            if done % self.progress_every == 0 or done == len(targets):
                log.info("  progress %d/%d", done, len(targets))
            return index, book

        pairs = await asyncio.gather(*(worker(i, u, c) for i, (u, c) in enumerate(targets)))
        # keep the listing order, regardless of which request finished first
        result.books = [book for _, book in sorted(pairs, key=lambda p: p[0]) if book is not None]
        return result
