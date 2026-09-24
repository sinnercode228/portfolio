"""Data models shared by parsers, crawler and exporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields


@dataclass(frozen=True, slots=True)
class Category:
    name: str
    url: str

    @property
    def slug(self) -> str:
        """`catalogue/category/books/mystery_3/index.html` -> `mystery`."""
        part = self.url.rstrip("/").split("/")[-2]
        return part.rsplit("_", 1)[0]


@dataclass(slots=True)
class ListingPage:
    """One page of a category listing."""

    product_urls: list[str]
    next_url: str | None
    current_page: int = 1
    total_pages: int = 1


@dataclass(slots=True)
class Book:
    title: str
    price: float | None
    currency: str
    availability: int
    in_stock: bool
    rating: int | None
    upc: str
    category: str
    description: str
    image_url: str
    product_url: str
    price_excl_tax: float | None = None
    price_incl_tax: float | None = None
    tax: float | None = None
    num_reviews: int | None = None
    scraped_at: str = field(default="")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]
