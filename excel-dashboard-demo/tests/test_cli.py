"""End-to-end: the three command-line scripts."""

import importlib

from openpyxl import load_workbook


def _main(module):
    return importlib.import_module(module).main


def test_generate_build_dashboard_and_invoice(tmp_path, capsys):
    assert _main("generate_sample_data")(["--out-dir", str(tmp_path), "--days", "14", "--seed", "3"]) == 0
    assert (tmp_path / "production_log_sample.csv").exists()
    assert (tmp_path / "production_log_sample_ru.csv").exists()

    out = tmp_path / "dash.xlsx"
    assert _main("build_dashboard")([str(tmp_path / "production_log_sample.csv"), "-o", str(out)]) == 0
    assert "Dashboard" in load_workbook(out).sheetnames

    out_ru = tmp_path / "dash_ru.xlsx"
    assert _main("build_dashboard")([str(tmp_path / "production_log_sample_ru.csv"), "--lang", "ru",
                                     "-o", str(out_ru)]) == 0
    assert "Дашборд" in load_workbook(out_ru).sheetnames

    inv = tmp_path / "inv.xlsx"
    assert _main("build_invoice")([str(tmp_path / "work_log_sample.csv"), str(tmp_path / "rates_sample.csv"),
                                   "-o", str(inv), "--tax", "0.1"]) == 0
    wb = load_workbook(inv)
    assert wb["Settings"]["C11"].value == 0.1
    printed = capsys.readouterr().out
    assert "Period 2026-09-01 .. 2026-09-30" in printed


def test_build_dashboard_reports_bad_input(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    assert _main("build_dashboard")([str(bad), "-o", str(tmp_path / "x.xlsx")]) == 2
    assert "missing required column" in capsys.readouterr().err


def test_check_workbook_script(tmp_path):
    assert _main("generate_sample_data")(["--out-dir", str(tmp_path), "--lang", "en"]) == 0
    out = tmp_path / "d.xlsx"
    _main("build_dashboard")([str(tmp_path / "production_log_sample.csv"), "-o", str(out)])
    assert _main("check_workbook")([str(out)]) == 0
