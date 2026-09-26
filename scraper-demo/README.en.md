# bookscraper

[Русский](README.md) · **English**

An async CLI scraper for [books.toscrape.com](https://books.toscrape.com), a sandbox for practicing web scraping. The HTML parsing is short; most of the code is the network layer and data cleanup: a requests-per-second limit, retries with `Retry-After` support, an on-disk cache, and cutting the duplicated teaser out of descriptions. The results go to XLSX, CSV and JSON. It's written in Python 3.10+ (asyncio, httpx, selectolax, openpyxl); gspread is installed separately and only imported with `--gsheet`.

```bash
git clone https://github.com/sinnercode228/portfolio.git
cd portfolio/scraper-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bookscraper --limit 100 --out output/books    # books.xlsx + books.csv + books.json
```

The `books_sample.*` files in [`output/`](output/) came from this command (timestamps and levels stripped from the log):

```
$ python -m bookscraper --limit 100 -o output/books_sample.xlsx -o output/books_sample.csv -o output/books_sample.json
...
  Travel                   11 product links
  Mystery                  32 product links
  Historical Fiction       26 product links
  Sequential Art           31 product links
...
scraped 100 books in 30.3s — 109 HTTP requests, 0 cache hits, 0 retries, 0 errors
```

![The Books sheet from output/books_sample.xlsx](docs/excel_preview.jpg)

Each product page yields 16 fields: JSON gets all of them, XLSX and CSV get 11. Besides the Books sheet, the XLSX file has Summary (per-category stats and a TOTAL row) and About (source, time, run parameters, error count). [`exporters/excel.py`](bookscraper/exporters/excel.py) keeps a value that starts with `=` as text, even if openpyxl took it for a formula. `test_xlsx_keeps_formula_like_text_as_text` exports a record titled `=HYPERLINK("http://evil.test")`, opens the xlsx with `load_workbook` and checks `data_type == "s"`.

## 109 requests in 30 seconds

The 109 requests are robots.txt, the home page, 7 listing pages and 100 product pages, and the run time is set by the limiter. `RateLimiter` in [`fetcher.py`](bookscraper/fetcher.py) keeps the time of the next allowed start: a task holding an `asyncio.Lock` sleeps until then and pushes it forward by `1/rate`. Unlike a token bucket, it keeps no reserve, so there's no burst at the start either. With `--rate 4`, starts come 0.25 s apart, and the 108 intervals between 109 starts add up to 27 s at any network speed.

The limiter's `wait()` is called inside the semaphore, right before `client.get`. If you call it before entering the semaphore, a task gets its start time, then waits in line for a connection, and several of those tasks hit the network at once. Before a retry, the task sleeps outside the semaphore, so a request that waits up to 30 s doesn't hold one of the five slots (`--concurrency 5`).

Retries are triggered by 408, 425, 429, 500, 502, 503 and 504 responses, as well as timeouts and network errors. By default there are up to three retries, and each one goes through the semaphore and the limiter again. A 404, 501 or any other code raises `FetchError` right away. The pause, `min(30, 0.5·2^(n-1))` with equal jitter, is 0.25–0.5 s before the first retry and 1–2 s before the third. A `Retry-After` in seconds or as an HTTP date can make it longer, but the cap stays at 30 s, so with `Retry-After: 120` the retry goes out early. An error on a single product page, even an unexpected one, goes into the list at the end of the log, and [`crawler.py`](bookscraper/crawler.py) carries on with the run.

## A cache that survives `kill -9`

[`cache.py`](bookscraper/cache.py) stores a response in `.cache/http/<first 2 chars of the hash>/<sha256 of the URL>.json`, along with the URL and the time it was written. Only 200 responses are cached, with a 24 h TTL (`--cache-ttl 0` means no expiry). On read, the stored URL is checked, and broken JSON counts as a miss. A hit is returned before the semaphore and the limiter, so cached pages don't wait out their 0.25 s.

Writes go to a temp file with the pid and thread id in its name and finish with `os.replace`, so there's never a half-written `<sha256>.json`, even after `kill -9`. After Ctrl-C, the XLSX, CSV and JSON files don't get written, but the cache is updated after every page, and a rerun doesn't re-download what's already there. If a cache write fails with `OSError` (say, the disk is full), a warning goes to the log and the page still goes on to the parser.

## The teaser at the start of a description

On the site, a long description comes as `<teaser cut mid-word> <full text> ...more`. `clean_description` in [`parsers.py`](bookscraper/parsers.py) cuts the teaser only if the text ends with `...more`. Without the marker, a repeat at the start is treated as ordinary text, and `test_clean_description_needs_more_marker_to_cut` checks that "Rise and shine, little one. Rise and shine, little one, the sun is up." stays as is.

The cut itself looks for the next occurrence of the first 20 non-whitespace characters and cuts there if the common prefix of the teaser and the rest is at least half as long as the teaser (the half threshold is there to tolerate the odd broken character). Those 20 characters can also turn up inside the teaser itself; then the search moves on to the next occurrence (`test_clean_description_opening_words_repeated_inside_teaser`).

## Tests

80 tests, all offline. Saved pages live in `tests/fixtures/`, and an `httpx.MockTransport` from [`tests/conftest.py`](tests/conftest.py) serves them as a copy of the site, down to the 404 on robots.txt and responses without a charset. A fake module stands in for gspread. There are 34 tests for the parsers, 18 for the network layer (retries, `Retry-After`, TTL, cache write failure, the limiter, the semaphore), 9 for export, 8 for crawling, 7 for `main()` as a whole and 4 for Google Sheets.

```bash
pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
```

## Flags and exit codes

`python -m bookscraper --help` prints all the flags; these are the ones you'll need most often:

| Flag | Default | What it does |
|---|---|---|
| `-c, --category NAME` | all | category by name or slug, case-insensitive; repeatable; `--list-categories` lists them |
| `-n, --limit N` | no limit | maximum number of books |
| `-o, --out PATH` | `output/books` | format from the extension; with no extension, all three are written; repeatable |
| `--csv-sep` | `comma` | CSV separator: `semicolon` for Excel with a Russian locale (prices then use a decimal comma) or `tab` |
| `--rate RPS` / `--concurrency N` | 4 / 5 | requests per second (`0` for no limit) / concurrent requests |
| `--gsheet KEY_OR_URL` | | also export to Google Sheets: `pip install -r requirements-gsheets.txt`, a service account key in `--gsheet-creds`, and the spreadsheet has to be shared with the account's e-mail |

Exit codes: `0` done (failed pages are only listed in the log), `1` nothing scraped, `2` bad arguments or unknown category, `3` the home page didn't download or is disallowed in robots.txt, `4` Google Sheets error, `5` couldn't write a file (for example, it's open in Excel on Windows), `130` Ctrl-C.

If robots.txt answers with a 5xx or doesn't answer at all, the scraper treats everything as allowed, as with a 404, although RFC 9309 says the whole site should be treated as disallowed in that case.

---

Built by Грешный Котик (sinnercode). I take freelance work like this: Telegram [@sinnercode](https://t.me/sinnercode). License: [MIT](LICENSE).
