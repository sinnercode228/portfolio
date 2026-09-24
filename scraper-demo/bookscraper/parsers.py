"""Pure HTML parsers: HTML string + page URL in, plain data out.

No network, no I/O — so every function here is trivially unit-testable
against saved HTML fixtures (see tests/fixtures). When adapting the scraper
to another site, this is the main file to rewrite.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser, LexborNode

from bookscraper.models import Book, Category, ListingPage

RATING_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
CURRENCY_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR", "₽": "RUB"}

_PRICE_RE = re.compile(r"(?P<symbol>[£$€₽])?\s*(?P<amount>\d[\d\s,]*(?:\.\d+)?)")
_AVAILABLE_RE = re.compile(r"\((\d+)\s+available\)", re.IGNORECASE)
_PAGE_OF_RE = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)
_MORE_SUFFIX_RE = re.compile(r"\s*\.\.\.\s*more\s*$", re.IGNORECASE)
# "...in Indonesia.But interspersed" -> "...in Indonesia. But interspersed"
# (the sandbox glues paragraphs together without a space)
_GLUED_SENTENCE_RE = re.compile(r"(?<=[a-z0-9][.!?])(?=[A-Z][a-z])|(?<=[a-z0-9][.!?][”’)])(?=[A-Z])")
# soft hyphen, zero-width spaces/joiners, BOM — invisible but break comparisons
_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u200b\u200c\u200d\u2060\ufeff"), None)


class ParseError(ValueError):
    """Raised when a page does not look like what we expected."""


# --------------------------------------------------------------------------- #
# Small value parsers
# --------------------------------------------------------------------------- #
def parse_price(text: str | None) -> tuple[float | None, str]:
    """'£51.77' -> (51.77, 'GBP'). Returns (None, '') if no number found."""
    if not text:
        return None, ""
    match = _PRICE_RE.search(text)
    if not match:
        return None, ""
    amount = match.group("amount").replace(" ", "").replace(",", "")
    currency = CURRENCY_SYMBOLS.get(match.group("symbol") or "", "")
    return round(float(amount), 2), currency


def parse_availability(text: str | None) -> tuple[int, bool]:
    """'In stock (22 available)' -> (22, True); 'Out of stock' -> (0, False)."""
    if not text:
        return 0, False
    clean = " ".join(text.split())
    in_stock = "in stock" in clean.lower()
    match = _AVAILABLE_RE.search(clean)
    count = int(match.group(1)) if match else (1 if in_stock else 0)
    return count, in_stock


def parse_rating(class_attr: str | None) -> int | None:
    """'star-rating Three' -> 3."""
    if not class_attr:
        return None
    for token in class_attr.split():
        value = RATING_WORDS.get(token.lower())
        if value:
            return value
    return None


def clean_text(text: str | None) -> str:
    """Drop invisible characters and collapse all whitespace to single spaces."""
    return " ".join(text.translate(_INVISIBLE).split()) if text else ""


def clean_description(text: str | None) -> str:
    """Normalise a product description.

    The sandbox renders long descriptions as `<teaser cut mid-word> <full text> ...more`.
    Only when that "...more" marker is present, we strip it and drop the teaser
    if the text that follows starts with the same words (compared ignoring
    whitespace). Sentences glued together without a space are separated.
    """
    text = clean_text(text)
    stripped = _MORE_SUFFIX_RE.sub("", text)
    if stripped != text:
        text = stripped
        positions = [i for i, ch in enumerate(text) if not ch.isspace()]
        squashed = "".join(text[i] for i in positions)
        head = 20
        cut = squashed.find(squashed[:head], 1) if len(squashed) > 2 * head else -1
        while cut > 0:
            teaser, rest = squashed[:cut], squashed[cut:]
            # >= half of the teaser must match: tolerates the odd broken character
            if len(os.path.commonprefix([teaser, rest])) >= 0.5 * len(teaser):
                text = text[positions[cut]:]
                break
            # the opening words may also occur inside the teaser itself: try the next match
            cut = squashed.find(squashed[:head], cut + 1)
    return _GLUED_SENTENCE_RE.sub(" ", text)


def _text(node: LexborNode | None) -> str:
    return clean_text(node.text(deep=True)) if node is not None else ""


def _parse_tree(html: str) -> LexborHTMLParser:
    if not html or not html.strip():
        raise ParseError("empty HTML")
    return LexborHTMLParser(html)


# --------------------------------------------------------------------------- #
# Page parsers
# --------------------------------------------------------------------------- #
def parse_categories(html: str, page_url: str) -> list[Category]:
    """Category links from the sidebar of the home page."""
    tree = _parse_tree(html)
    links = tree.css(".side_categories ul.nav-list > li > ul > li > a")
    categories = [
        Category(name=_text(a), url=urljoin(page_url, a.attributes.get("href") or ""))
        for a in links
        if a.attributes.get("href")
    ]
    if not categories:
        raise ParseError(f"no categories found on {page_url}")
    return categories


def parse_listing(html: str, page_url: str) -> ListingPage:
    """Product links + pagination info from a category / catalogue page."""
    tree = _parse_tree(html)
    urls: list[str] = []
    seen: set[str] = set()
    for a in tree.css("article.product_pod h3 a"):
        href = a.attributes.get("href")
        if not href:
            continue
        absolute = urljoin(page_url, href)
        if absolute not in seen:
            seen.add(absolute)
            urls.append(absolute)

    next_link = tree.css_first("ul.pager li.next a")
    next_href = next_link.attributes.get("href") if next_link is not None else None
    next_url = urljoin(page_url, next_href) if next_href else None

    current, total = 1, 1
    match = _PAGE_OF_RE.search(_text(tree.css_first("ul.pager li.current")))
    if match:
        current, total = int(match.group(1)), int(match.group(2))

    return ListingPage(product_urls=urls, next_url=next_url, current_page=current, total_pages=total)


def parse_product(html: str, page_url: str, *, category: str | None = None) -> Book:
    """All fields of a single product page."""
    tree = _parse_tree(html)
    main = tree.css_first(".product_main")
    if main is None:
        raise ParseError(f"not a product page: {page_url}")

    title = _text(main.css_first("h1"))
    price, currency = parse_price(_text(main.css_first("p.price_color")))
    rating_node = main.css_first("p.star-rating")
    rating = parse_rating(rating_node.attributes.get("class") if rating_node is not None else None)

    # "Product information" table: <tr><th>UPC</th><td>...</td></tr>
    info: dict[str, str] = {}
    for row in tree.css("table.table-striped tr"):
        key, value = row.css_first("th"), row.css_first("td")
        if key is not None and value is not None:
            info[_text(key).lower()] = _text(value)

    availability_text = info.get("availability") or _text(main.css_first("p.availability"))
    availability, in_stock = parse_availability(availability_text)

    description = clean_description(_text(tree.css_first("#product_description + p")))

    img = tree.css_first("#product_gallery img") or tree.css_first(".product_page img")
    img_src = img.attributes.get("src") if img is not None else None
    image_url = urljoin(page_url, img_src) if img_src else ""

    # Breadcrumb: Home > Books > <Category> > <Title>
    crumbs = [_text(a) for a in tree.css("ul.breadcrumb li a")]
    crumb_category = crumbs[-1] if len(crumbs) >= 3 else ""

    reviews = info.get("number of reviews", "")
    return Book(
        title=title,
        price=price,
        currency=currency,
        availability=availability,
        in_stock=in_stock,
        rating=rating,
        upc=info.get("upc", ""),
        category=crumb_category or (category or ""),
        description=description,
        image_url=image_url,
        product_url=page_url,
        price_excl_tax=parse_price(info.get("price (excl. tax)"))[0],
        price_incl_tax=parse_price(info.get("price (incl. tax)"))[0],
        tax=parse_price(info.get("tax"))[0],
        num_reviews=int(reviews) if reviews.isdigit() else None,
        scraped_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
