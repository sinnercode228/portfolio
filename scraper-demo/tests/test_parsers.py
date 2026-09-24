"""Parser tests against real HTML saved from books.toscrape.com (tests/fixtures)."""

from __future__ import annotations

import pytest

from bookscraper.parsers import (
    ParseError,
    clean_description,
    parse_availability,
    parse_categories,
    parse_listing,
    parse_price,
    parse_product,
    parse_rating,
)

HOME = "https://books.toscrape.com/index.html"
MYSTERY = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"
PRODUCT = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"


# ------------------------------------------------------------------ categories
def test_parse_categories(index_html):
    cats = parse_categories(index_html, HOME)
    assert len(cats) == 50
    assert cats[0].name == "Travel"
    assert cats[0].url == "https://books.toscrape.com/catalogue/category/books/travel_2/index.html"
    assert cats[0].slug == "travel"
    names = {c.name for c in cats}
    assert {"Mystery", "Science Fiction", "Poetry"} <= names
    assert "Books" not in names  # the top-level root is not a category


def test_parse_categories_raises_on_wrong_page(product_html):
    with pytest.raises(ParseError):
        parse_categories(product_html, PRODUCT)


# --------------------------------------------------------------------- listing
def test_parse_listing_first_page(category_html):
    page = parse_listing(category_html, MYSTERY)
    assert len(page.product_urls) == 20
    assert page.product_urls[0] == "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"
    assert all(u.startswith("https://books.toscrape.com/catalogue/") for u in page.product_urls)
    assert len(set(page.product_urls)) == 20
    assert page.next_url == "https://books.toscrape.com/catalogue/category/books/mystery_3/page-2.html"
    assert (page.current_page, page.total_pages) == (1, 2)


def test_parse_listing_last_page(category_last_html):
    url = MYSTERY.replace("index.html", "page-2.html")
    page = parse_listing(category_last_html, url)
    assert len(page.product_urls) == 12  # 32 mystery books = 20 + 12
    assert page.next_url is None
    assert (page.current_page, page.total_pages) == (2, 2)


def test_parse_listing_without_pager():
    html = '<article class="product_pod"><h3><a href="../x_1/index.html">X</a></h3></article>'
    page = parse_listing(html, "https://example.test/catalogue/a/index.html")
    assert page.product_urls == ["https://example.test/catalogue/x_1/index.html"]
    assert page.next_url is None and page.total_pages == 1


# --------------------------------------------------------------------- product
def test_parse_product_all_fields(product_html):
    book = parse_product(product_html, PRODUCT, category="ignored-if-breadcrumb-found")
    assert book.title == "A Light in the Attic"
    assert book.price == 51.77
    assert book.currency == "GBP"
    assert book.availability == 22
    assert book.in_stock is True
    assert book.rating == 3
    assert book.upc == "a897fe39b1053632"
    assert book.category == "Poetry"
    assert book.image_url == (
        "https://books.toscrape.com/media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg"
    )
    assert book.product_url == PRODUCT
    assert book.price_excl_tax == 51.77 and book.price_incl_tax == 51.77 and book.tax == 0.0
    assert book.num_reviews == 0
    assert book.scraped_at.endswith("+00:00")


def test_parse_product_description_is_clean(product_html):
    desc = parse_product(product_html, PRODUCT).description
    assert desc.startswith("It's hard to imagine a world without A Light in the Attic.")
    assert desc.endswith("Shel, you never sounded so good.")
    assert "...more" not in desc
    assert desc.count("It's hard to imagine") == 1  # teaser duplicate removed


def test_parse_product_minimal_page_edge_cases():
    html = """
    <ul class="breadcrumb"><li><a href="/">Home</a></li><li class="active">X</li></ul>
    <article class="product_page">
      <div class="product_main">
        <h1>  Some   Book </h1>
        <p class="price_color">£1,234.50</p>
        <p class="instock availability">Out of stock</p>
      </div>
    </article>"""
    book = parse_product(html, "https://example.test/p/1", category="Fallback")
    assert book.title == "Some Book"
    assert book.price == 1234.5
    assert (book.availability, book.in_stock) == (0, False)
    assert book.rating is None
    assert book.upc == "" and book.description == "" and book.image_url == ""
    assert book.category == "Fallback"  # no category in breadcrumb -> listing category
    assert book.num_reviews is None


def test_parse_product_rejects_non_product(index_html):
    with pytest.raises(ParseError):
        parse_product(index_html, HOME)


def test_parse_empty_html():
    with pytest.raises(ParseError):
        parse_product("   ", PRODUCT)


# --------------------------------------------------------------- value parsers
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("£51.77", (51.77, "GBP")),
        ("  £ 10.00 ", (10.0, "GBP")),
        ("$1,299.99", (1299.99, "USD")),
        ("€5", (5.0, "EUR")),
        ("12.3", (12.3, "")),
        ("free", (None, "")),
        ("", (None, "")),
        (None, (None, "")),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("In stock (22 available)", (22, True)),
        ("\n   In stock (1 available)\n", (1, True)),
        ("In stock", (1, True)),
        ("Out of stock", (0, False)),
        ("", (0, False)),
    ],
)
def test_parse_availability(text, expected):
    assert parse_availability(text) == expected


@pytest.mark.parametrize(
    ("cls", "expected"),
    [("star-rating One", 1), ("star-rating Three", 3), ("star-rating five", 5),
     ("star-rating", None), ("", None), (None, None)],
)
def test_parse_rating(cls, expected):
    assert parse_rating(cls) == expected


def test_clean_description_keeps_normal_text():
    text = "A short description. Nothing repeated here at all."
    assert clean_description(text) == text


def test_clean_description_removes_teaser_and_invisible_chars():
    full = "Quaker midwife Rose Carroll hears secrets and keeps confidences as she works."
    teaser = "Quaker midwife Rose Carroll hears secrets and keeps con­fi­dences as sh"
    assert clean_description(f"{teaser} {full} ...more") == full


def test_clean_description_needs_more_marker_to_cut():
    # without the site's "...more" marker a repeated opening is legitimate text
    text = "Rise and shine, little one. Rise and shine, little one, the sun is up."
    assert clean_description(text) == text


def test_clean_description_opening_words_repeated_inside_teaser():
    # the first words re-appear inside the teaser: the real repeat must still be found
    full = ("#1 New York Times bestseller Jane Roe returns. After seven #1 New York Times "
            "bestsellers she outdoes herself with a story about a lighthouse and a storm.")
    teaser = full[:70]
    assert clean_description(f"{teaser} {full} ...more") == full


def test_clean_description_separates_glued_sentences():
    text = "She ran from lions in Zimbabwe.But in between she smiled. “Go!”Then she left.Version 2.0 stays."
    assert clean_description(text) == (
        "She ran from lions in Zimbabwe. But in between she smiled. “Go!” Then she left. Version 2.0 stays."
    )
