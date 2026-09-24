"""End-to-end crawl against an offline copy of the site (see conftest.FakeSite)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from bookscraper.crawler import BookCrawler, select_categories
from bookscraper.fetcher import Fetcher
from bookscraper.models import Category


def crawl(site, categories=None, limit=None, **fetcher_kw):
    async def go():
        fetcher_kw.setdefault("rate", 0)
        fetcher_kw.setdefault("backoff_base", 0.001)
        async with Fetcher(transport=httpx.MockTransport(site), **fetcher_kw) as f:
            return await BookCrawler(f).crawl(categories, limit)

    return asyncio.run(go())


def test_crawl_category_with_pagination(fake_site):
    result = crawl(fake_site, ["mystery"])
    assert len(result.books) == 32  # 20 on page 1 + 12 on page 2
    assert len({b.product_url for b in result.books}) == 32
    assert result.errors == []
    assert [c.name for c in result.categories] == ["Mystery"]
    book = result.books[0]
    assert book.product_url == "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"
    assert book.price == 51.77 and book.upc  # fixture product page


def test_limit_stops_early(fake_site):
    result = crawl(fake_site, ["Mystery"], limit=5)
    assert len(result.books) == 5
    assert fake_site.product_hits == 5
    page2 = "https://books.toscrape.com/catalogue/category/books/mystery_3/page-2.html"
    assert page2 not in fake_site.hits  # page 1 was enough


def test_limit_across_categories(fake_site):
    # FakeSite serves the same 32-book listing for every category; duplicates
    # across categories are skipped, so 3 categories still give 32 unique books.
    result = crawl(fake_site, ["travel", "mystery", "poetry"], limit=40)
    assert len(result.books) == 32


def test_transient_errors_are_retried(fake_site):
    url = "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"
    fake_site.fail_first[url] = 2
    result = crawl(fake_site, ["mystery"], limit=3, retries=3)
    assert len(result.books) == 3 and not result.errors
    assert fake_site.hits[url] == 3


def test_failed_pages_are_reported_not_fatal(fake_site):
    url = "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"
    fake_site.fail_first[url] = 99
    result = crawl(fake_site, ["mystery"], limit=4, retries=1)
    assert len(result.books) == 3
    assert len(result.errors) == 1 and "sharp-objects" in result.errors[0]


def test_select_categories_matching():
    cats = [
        Category("Travel", "https://x/catalogue/category/books/travel_2/index.html"),
        Category("Science Fiction", "https://x/catalogue/category/books/science-fiction_16/index.html"),
    ]
    assert select_categories(cats, None) == cats
    assert select_categories(cats, ["science fiction"]) == [cats[1]]
    assert select_categories(cats, ["science-fiction", "TRAVEL", "travel"]) == [cats[1], cats[0]]
    with pytest.raises(ValueError, match="unknown category: Cooking"):
        select_categories(cats, ["Cooking"])


def test_failed_listing_page_is_reported(fake_site):
    page2 = "https://books.toscrape.com/catalogue/category/books/mystery_3/page-2.html"
    fake_site.fail_first[page2] = 99
    result = crawl(fake_site, ["mystery"], retries=1)
    assert len(result.books) == 20  # page 1 still scraped
    assert len(result.errors) == 1 and "page-2.html" in result.errors[0]


def test_unexpected_error_on_one_page_does_not_stop_the_run(fake_site, monkeypatch):
    import bookscraper.crawler as crawler_mod

    real = crawler_mod.parse_product
    bad = "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"

    def flaky(html, url, **kw):
        if url == bad:
            raise KeyError("surprise")
        return real(html, url, **kw)

    monkeypatch.setattr(crawler_mod, "parse_product", flaky)
    result = crawl(fake_site, ["mystery"], limit=4)
    assert len(result.books) == 3
    assert len(result.errors) == 1 and "KeyError" in result.errors[0]
