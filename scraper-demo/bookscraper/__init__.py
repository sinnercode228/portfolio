"""bookscraper — async scraper demo for the https://books.toscrape.com sandbox.

Демо-проект / Demo project. The target site is a public sandbox built
specifically for scraping practice.
"""

import sys

if sys.version_info < (3, 10):  # noqa: UP036 - clear message instead of a cryptic TypeError on 3.9
    raise SystemExit(
        f"bookscraper needs Python 3.10 or newer, this is {sys.version.split()[0]}. "
        "Create the venv with a newer interpreter, e.g. `python3.12 -m venv .venv`."
    )

__version__ = "1.0.0"

USER_AGENT = f"bookscraper-demo/{__version__} (+portfolio demo; polite crawler)"
