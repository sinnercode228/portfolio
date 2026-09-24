"""Shared test helpers: saved HTML fixtures + an offline copy of the site."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://books.toscrape.com/"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def index_html() -> str:
    return load("index.html")


@pytest.fixture
def category_html() -> str:
    return load("category_page.html")


@pytest.fixture
def category_last_html() -> str:
    return load("category_last_page.html")


@pytest.fixture
def product_html() -> str:
    return load("product.html")


class FakeSite:
    """httpx.MockTransport handler that serves the saved fixtures.

    * robots.txt                      -> 404 (like the real sandbox)
    * index.html                      -> home page with 50 categories
    * any category index / page-2     -> Mystery listing pages 1 and 2
    * any product page                -> "A Light in the Attic"
    `fail_first` lets a test make the first N hits of a URL return 503.
    """

    PRODUCT_RE = re.compile(r"/catalogue/(?!category/)[^/]+/index\.html$")

    def __init__(self) -> None:
        self.hits: dict[str, int] = {}
        self.fail_first: dict[str, int] = {}
        self.pages = {
            "index": load("index.html"),
            "cat1": load("category_page.html"),
            "cat2": load("category_last_page.html"),
            "product": load("product.html"),
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.hits[url] = self.hits.get(url, 0) + 1
        if self.fail_first.get(url, 0) >= self.hits[url]:
            return httpx.Response(503)
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(404)
        if path in ("/", "/index.html"):
            return self._html("index")
        if "/catalogue/category/" in path:
            return self._html("cat2" if path.endswith("page-2.html") else "cat1")
        if self.PRODUCT_RE.search(path):
            return self._html("product")
        return httpx.Response(404)

    def _html(self, key: str) -> httpx.Response:
        # like the real site: text/html without a charset
        return httpx.Response(200, content=self.pages[key].encode("utf-8"),
                              headers={"content-type": "text/html"})

    @property
    def product_hits(self) -> int:
        return sum(n for url, n in self.hits.items() if self.PRODUCT_RE.search(httpx.URL(url).path))


@pytest.fixture
def fake_site() -> FakeSite:
    return FakeSite()
