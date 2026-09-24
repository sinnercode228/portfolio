"""Invoice + payroll workbook: lint, evaluation and comparison with the Python reference."""

from datetime import date, datetime

import pytest

from conftest import PERIOD, find_row
from xldash.formula_check import evaluate_workbook, find_errors, lint_workbook
from xldash.invoice import L10N, LOG, RATES
from xldash.worklog import billed_hours, invoice_reference


@pytest.mark.parametrize("hours, inc, expected", [
    (1.35, 0.25, 1.5), (1.25, 0.25, 1.25), (0.01, 0.25, 0.25), (2.0, 0.5, 2.0), (2.01, 0.5, 2.5),
    (0.3, 0.1, 0.3), (7.99, 1, 8),
])
def test_billed_hours_roundup(hours, inc, expected):
    assert billed_hours(hours, inc) == pytest.approx(expected)


def test_structure(invoice, worklog, lang):
    path, wb = invoice
    entries, rates, _ = worklog
    S = L10N[lang]["sheets"]
    assert wb.sheetnames == [S["invoice"], S["payroll"], S["summary"], S["log"], S["rates"], S["settings"]]
    assert wb.active.title == S["invoice"]
    log = wb[S["log"]]
    table = log.tables[LOG]
    assert table.ref == f"A1:K{len(entries) + 1}"
    calc = {c.name: c.calculatedColumnFormula for c in table.tableColumns}
    assert "ROUNDUP" in calc[L10N[lang]["log_cols"][6]].attr_text
    assert wb[S["rates"]].tables[RATES].ref == f"A1:D{len(rates) + 1}"
    inv = wb[S["invoice"]]
    assert inv.print_area and "$A$1:$H$" in inv.print_area
    assert str(inv.page_setup.paperSize) == str(inv.PAPERSIZE_A4)  # 9 = A4
    assert wb[S["payroll"]].print_area


def test_lint_is_clean(invoice):
    result = lint_workbook(invoice[0])
    assert result.ok, result.problems[:10]
    assert {"SUMIFS", "ROUNDUP", "INDEX", "MATCH"} <= set(result.functions)


def _settings_overrides(lang, **values):
    S = L10N[lang]["sheets"]
    rows = {name: 5 + i for i, (name, *_rest) in enumerate(L10N[lang]["set_rows"])}
    return {f"{S['settings']}!C{rows[k]}": v for k, v in values.items()}


@pytest.mark.parametrize("scenario", [
    {},
    {"perFrom": date(2026, 9, 1), "perTo": date(2026, 9, 15)},
    {"billInc": 0.5, "taxRate": 0.2},
    {"perFrom": date(2026, 8, 25), "perTo": date(2026, 10, 3), "billInc": 1},
])
def test_invoice_matches_reference(invoice, worklog, lang, scenario):
    path, wb = invoice
    entries, rates, _ = worklog
    T = L10N[lang]
    S = T["sheets"]
    d_from = scenario.get("perFrom", PERIOD[0])
    d_to = scenario.get("perTo", PERIOD[1])
    inc = scenario.get("billInc", 0.25)
    tax = scenario.get("taxRate", 0.0)
    overrides = _settings_overrides(lang, **{k: (datetime(v.year, v.month, v.day) if isinstance(v, date) else v)
                                             for k, v in scenario.items()})
    values = evaluate_workbook(path, overrides=overrides)
    assert find_errors(values) == {}
    ref = invoice_reference(entries, rates, d_from, d_to, inc, tax)

    inv = wb[S["invoice"]]
    i = S["invoice"]
    for rate in rates:
        r = find_row(inv, 3, rate.employee)
        emp = ref["per_employee"].get(rate.employee, {"billed_hours": 0})
        assert values[f"{i}!E{r}"] == pytest.approx(emp["billed_hours"])
        assert values[f"{i}!G{r}"] == pytest.approx(ref["lines"][rate.employee])
    sub = find_row(inv, 5, T["subtotal"])
    assert values[f"{i}!G{sub}"] == pytest.approx(ref["subtotal"])
    assert values[f"{i}!G{sub + 1}"] == pytest.approx(ref["tax"])
    assert values[f"{i}!G{sub + 2}"] == pytest.approx(ref["total"])
    for project, g in ref["per_project"].items():
        r = find_row(inv, 3, project, sub)
        assert values[f"{i}!E{r}"] == pytest.approx(g["billed_hours"])
        assert values[f"{i}!G{r}"] == pytest.approx(g["amount"])
    assert values[f"{i}!G{find_row(inv, 3, T['check_vs_lines'])}"] == T["check_ok"]

    # payroll
    pay = wb[S["payroll"]]
    p = S["payroll"]
    for rate in rates:
        r = find_row(pay, 2, rate.employee)
        emp = ref["per_employee"].get(rate.employee, {"worked": 0, "cost": 0, "amount": 0, "billable_actual": 0})
        assert values[f"{p}!D{r}"] == pytest.approx(emp["worked"])
        assert values[f"{p}!F{r}"] == pytest.approx(emp["cost"])
        assert values[f"{p}!J{r}"] == pytest.approx(emp["amount"])
        assert values[f"{p}!K{r}"] == pytest.approx(emp["amount"] - emp["cost"])
        if emp["worked"]:
            assert values[f"{p}!L{r}"] == pytest.approx(emp["billable_actual"] / emp["worked"])

    # weekly summary adds up to the invoice (when the period fits into 6 weeks)
    s = S["summary"]
    tot = find_row(wb[s], 2, T["total_row"])
    mondays = {d_from.toordinal() - d_from.weekday()} | {
        o - date.fromordinal(o).weekday() for o in range(d_from.toordinal(), d_to.toordinal() + 1)}
    if len(mondays) <= 6:
        assert values[f"{s}!G{tot}"] == pytest.approx(ref["subtotal"])
        assert values[f"{s}!G{tot + 1}"] == T["check_ok"]
        assert values[f"{s}!B{tot + 2}"] == ""
    else:
        assert values[f"{s}!B{tot + 2}"] == T["sum_trunc"]


def test_weeks_are_calendar_weeks(invoice, lang):
    path, wb = invoice
    S = L10N[lang]["sheets"]
    values = evaluate_workbook(path, sheets=[S["summary"]])
    s = S["summary"]
    serial = lambda d: (d - date(1899, 12, 30)).days  # noqa: E731
    # September 2026 starts on Tuesday: week 1 = Tue 1 .. Sun 6, week 5 = Mon 28 .. Wed 30
    assert (values[f"{s}!C5"], values[f"{s}!D5"]) == (serial(date(2026, 9, 1)), serial(date(2026, 9, 6)))
    assert (values[f"{s}!C6"], values[f"{s}!D6"]) == (serial(date(2026, 9, 7)), serial(date(2026, 9, 13)))
    assert (values[f"{s}!C9"], values[f"{s}!D9"]) == (serial(date(2026, 9, 28)), serial(date(2026, 9, 30)))
    assert values[f"{s}!C10"] == ""
