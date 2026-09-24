"""CLI tests: full `main()` run against the offline FakeSite."""

from __future__ import annotations

import functools
import json

import httpx
import pytest

from bookscraper import cli
from bookscraper.fetcher import Fetcher


@pytest.fixture
def offline(monkeypatch, fake_site):
    """Make the CLI use the fake site instead of the network."""
    monkeypatch.setattr(cli, "Fetcher", functools.partial(Fetcher, transport=httpx.MockTransport(fake_site)))
    return fake_site


def test_cli_writes_all_formats(tmp_path, offline):
    base = tmp_path / "books"
    code = cli.main(["-c", "mystery", "-n", "7", "-o", str(base), "--no-cache", "--rate", "0", "-q"])
    assert code == 0
    for ext in ("xlsx", "csv", "json"):
        assert (tmp_path / f"books.{ext}").is_file()
    assert len(json.loads((tmp_path / "books.json").read_text(encoding="utf-8"))) == 7


def test_cli_single_output_and_cache(tmp_path, offline):
    out = tmp_path / "one.csv"
    args = ["-c", "Mystery", "-n", "3", "-o", str(out), "--cache-dir", str(tmp_path / "c"), "--rate", "0", "-q"]
    assert cli.main(args) == 0
    first_hits = sum(offline.hits.values())
    assert cli.main(args) == 0
    # second run: everything except robots.txt (404, never cached) comes from the cache
    assert sum(offline.hits.values()) - first_hits == 1
    assert out.is_file() and not (tmp_path / "one.xlsx").exists()


def test_cli_unknown_category(tmp_path, offline):
    assert cli.main(["-c", "cooking", "-o", str(tmp_path / "x"), "--no-cache", "-q"]) == 2


def test_cli_list_categories(offline, capsys):
    assert cli.main(["--list-categories", "--no-cache", "-q"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 50 and out[0].split()[0] == "travel"


def test_cli_rejects_bad_limit():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--limit", "0"])


def test_cli_save_error_is_reported_and_other_formats_still_written(tmp_path, offline):
    (tmp_path / "blocked").write_text("a file, not a folder")
    good = tmp_path / "ok.json"
    code = cli.main(["-c", "mystery", "-n", "2", "-o", str(tmp_path / "blocked" / "x.xlsx"),
                     "-o", str(good), "--no-cache", "--rate", "0", "-q"])
    assert code == 5
    assert good.is_file()


def test_cli_csv_semicolon(tmp_path, offline):
    out = tmp_path / "ru.csv"
    assert cli.main(["-c", "mystery", "-n", "2", "-o", str(out), "--csv-sep", "semicolon",
                     "--no-cache", "--rate", "0", "-q"]) == 0
    assert out.read_text(encoding="utf-8-sig").startswith("Title;Category;")
