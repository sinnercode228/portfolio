"""Command-line interface.

    python -m bookscraper --category Mystery --limit 50 --out output/mystery.xlsx
    python -m bookscraper --limit 100 --out output/books          # xlsx + csv + json
    python -m bookscraper --list-categories
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

from bookscraper import __version__
from bookscraper.cache import DiskCache
from bookscraper.crawler import DEFAULT_BASE_URL, BookCrawler, CrawlResult
from bookscraper.exporters import export, resolve_outputs
from bookscraper.fetcher import Fetcher, FetchError

log = logging.getLogger("bookscraper")

CSV_SEPARATORS = {"comma": ",", "semicolon": ";", "tab": "\t"}


def positive_int(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return n


class _HelpFormatter(
    argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter
):
    """Show "(default: X)" only when there is a meaningful default."""

    def _get_help_string(self, action: argparse.Action) -> str | None:
        if action.default in (None, False) or "default" in (action.help or ""):
            return action.help
        return super()._get_help_string(action)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bookscraper",
        description="Async scraper for the books.toscrape.com sandbox "
                    "(Демо-проект / Demo project). Exports to Excel, CSV and JSON.",
        formatter_class=_HelpFormatter,
        epilog="examples:\n"
               "  python -m bookscraper --limit 100 --out output/books\n"
               "  python -m bookscraper -c mystery -c poetry --out output/books.xlsx\n"
               "  python -m bookscraper --list-categories\n"
               "(after `pip install -e .` the same works as plain `bookscraper ...`)",
    )
    what = p.add_argument_group("what to scrape")
    what.add_argument("-c", "--category", action="append", metavar="NAME",
                      help="category name or slug; repeat for several (default: all)")
    what.add_argument("-n", "--limit", type=positive_int, metavar="N",
                      help="max number of books (default: no limit)")
    what.add_argument("--list-categories", action="store_true",
                      help="print available categories and exit")
    what.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)

    out = p.add_argument_group("output")
    out.add_argument("-o", "--out", action="append", metavar="PATH",
                     help="output file; format by extension (.xlsx/.csv/.json). "
                          "Without extension all three are written. Repeatable. "
                          "(default: output/books)")
    out.add_argument("--csv-sep", choices=sorted(CSV_SEPARATORS), default="comma",
                     help="CSV delimiter; 'semicolon' (+ decimal comma) opens in columns "
                          "in Excel with a Russian/European locale")
    out.add_argument("--gsheet", metavar="KEY_OR_URL",
                     help="also upload to a Google Sheet (needs gspread, see README)")
    out.add_argument("--gsheet-creds", default="service_account.json", metavar="FILE",
                     help="Google service-account JSON for --gsheet")

    net = p.add_argument_group("politeness & reliability")
    net.add_argument("--concurrency", type=positive_int, default=5, metavar="N", help="parallel requests")
    net.add_argument("--rate", type=float, default=4.0, metavar="RPS", help="max requests per second (0 = unlimited)")
    net.add_argument("--retries", type=int, default=3, metavar="N",
                     help="retries per request on 5xx/429/network errors")
    net.add_argument("--timeout", type=float, default=20.0, metavar="SEC", help="request timeout, seconds")
    net.add_argument("--cache-dir", default=".cache/http", metavar="DIR", help="HTTP cache directory")
    net.add_argument("--cache-ttl", type=float, default=24.0, metavar="HOURS",
                     help="cache lifetime, hours (0 = never expires)")
    net.add_argument("--no-cache", action="store_true", help="disable the HTTP cache")
    net.add_argument("--ignore-robots", action="store_true", help="do not check robots.txt")

    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    p.add_argument("-q", "--quiet", action="store_true", help="only warnings and errors")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def setup_logging(verbose: bool, quiet: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)


async def run(args: argparse.Namespace) -> tuple[CrawlResult, Fetcher]:
    cache = None if args.no_cache else DiskCache(args.cache_dir, ttl_seconds=args.cache_ttl * 3600)
    async with Fetcher(
        concurrency=args.concurrency,
        rate=args.rate,
        retries=args.retries,
        timeout=args.timeout,
        cache=cache,
    ) as fetcher:
        crawler = BookCrawler(fetcher, base_url=args.base_url, respect_robots=not args.ignore_robots)
        if args.list_categories:
            result = CrawlResult(categories=await crawler.fetch_categories())
        else:
            result = await crawler.crawl(args.category, args.limit)
        return result, fetcher


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose, args.quiet)

    started = time.perf_counter()
    try:
        result, fetcher = asyncio.run(run(args))
    except ValueError as exc:  # e.g. unknown category
        log.error("%s", exc)
        if args.category:
            log.error("tip: `python -m bookscraper --list-categories` prints the exact names")
        return 2
    except FetchError as exc:
        log.error("cannot reach the site: %s", exc)
        return 3
    except KeyboardInterrupt:
        log.warning("interrupted")
        return 130

    if args.list_categories:
        for cat in result.categories:
            print(f"{cat.slug:<22} {cat.name}")
        return 0

    elapsed = time.perf_counter() - started
    books = result.books
    s = fetcher.stats
    log.info("scraped %d books in %.1fs — %d HTTP requests, %d cache hits, %d retries, %d errors",
             len(books), elapsed, s.requests, s.cache_hits, s.retries, len(result.errors))

    if not books:
        log.error("nothing scraped")
        return 1

    meta = {
        "source": args.base_url,
        "categories": ", ".join(args.category) if args.category else "all",
        "limit": args.limit or "none",
        "concurrency / rate": f"{args.concurrency} / {args.rate} req/s",
        "errors": len(result.errors),
    }
    exit_code = 0
    for path in resolve_outputs(args.out or ["output/books"]):
        try:
            export(books, path, meta, csv_delimiter=CSV_SEPARATORS[args.csv_sep])
        except OSError as exc:  # e.g. the file is open in Excel (Windows), read-only folder
            log.error("could not save %s: %s (close the file if it is open and run again; "
                      "pages are cached, so a re-run is fast)", path, exc)
            exit_code = 5
            continue
        log.info("saved %s", path)

    if args.gsheet:
        from bookscraper.exporters.gsheets import GSheetsUnavailable, write_gsheet

        try:
            url = write_gsheet(books, args.gsheet, credentials_file=args.gsheet_creds)
            log.info("uploaded to Google Sheets: %s", url)
        except GSheetsUnavailable as exc:
            log.error("%s", exc)
            exit_code = exit_code or 4

    if result.errors:
        log.warning("%d pages failed:", len(result.errors))
        for err in result.errors[:20]:
            log.warning("  %s", err)
        if len(result.errors) > 20:
            log.warning("  ... and %d more", len(result.errors) - 20)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
