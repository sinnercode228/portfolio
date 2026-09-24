"""Build the production dashboard workbook.

Sheets
------
Dashboard   KPI tiles + summary tables (department / machine / employee) + charts
Halts       halt hours per machine, top reasons (live ranking), machine x reason heatmap
Settings    filters with dropdowns: Shift, Department, Date from / to, availability target
Data        the cleaned log as a real Excel Table (tblData)
Import log  what the loader fixed or rejected
Lists       (hidden) dropdown sources and the effective filter criteria

Every number on Dashboard/Halts is a SUMIFS/COUNTIFS formula over tblData that
reads the Settings filters, so the workbook keeps working in Excel without Python.
Only Excel 2007-2013 functions are used (no XLOOKUP / FILTER / dynamic arrays).
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule, Rule
from openpyxl.styles import Alignment, Font
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.styles.numbers import NumberFormat
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.workbook.properties import CalcProperties
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from . import DEMO_BRAND
from .csvio import LoadReport
from .formulas import date_text, quote_sheet
from .production import ProdRecord, dimension_values, machine_department
from .style import (BAD, BLUE, BOTTOM, GOOD, HEADER_FILL, INK_2, MUTED, ORANGE, PANEL,
                    TOP_DOUBLE, base_sheet, body_cell, col, fill, font, header_row, input_cell,
                    section_title, set_widths, style_bar_chart, text_props, title_bar)

TABLE = "tblData"
DATE_LIST_LEN = 400          # max distinct days offered in the date dropdowns
TOP_N = 5

FMT_H = '#,##0.0;-#,##0.0;"–"'
FMT_PCT = '0.0%;-0.0%;"–"'
FMT_INT = '#,##0;-#,##0;"–"'
FMT_MIN = '#,##0;-#,##0;"–"'

LABELS = {
    "en": {
        "sheets": {"dash": "Dashboard", "halts": "Halts", "settings": "Settings", "data": "Data",
                   "log": "Import log", "lists": "Lists"},
        "columns": ["Date", "Shift", "Department", "Machine", "Employee",
                    "RunHours", "HaltMinutes", "HaltReason"],
        "date_fmt": "yyyy-mm-dd",
        "all": "All",
        "title": f"Production dashboard — {DEMO_BRAND}",
        "demo": "Demo project · Демо-проект — company, people and figures are fictional",
        "caption": ("Shift: ", "   ·   Department: ", "   ·   Period: "),
        "caption_hint": "Change filters on the Settings sheet",
        "kpi": ["Run hours", "Halt hours", "Availability", "Shifts logged", "Halt events",
                "Top halt reason"],
        "kpi_notes": ["sum of RunHours", "HaltMinutes ÷ 60", "run ÷ (run + halt)",
                      "rows matching filters", "rows with a halt", "by halt hours"],
        "target": "target",
        "by_department": "By department", "by_machine": "By machine", "by_employee": "By employee",
        "table_note": "zero values are shown as “–”",
        "hdr": ["Run, h", "Halt, h", "Availability", "Shifts", "Share of halts"],
        "department": "Department", "machine": "Machine", "employee": "Employee",
        "total": "Total",
        "ch_dept": "Availability by department vs target", "ch_machine": "Run vs halt hours by machine",
        "target_series": "Target",
        "ch_emp": "Run vs halt hours by employee",
        # halts
        "halts_title": "Halts analysis",
        "h_by_machine": "Halt hours by machine",
        "h_hdr": ["Department", "Halt, h", "Halt events", "Avg per event, min", "Share of halts",
                  "Top reason"],
        "h_top": f"Top {TOP_N} halt reasons",
        "h_top_hdr": ["Rank", "Reason", "Halt, h", "Halt events", "Share of halts"],
        "h_all": "All reasons (source for the ranking)",
        "h_all_hdr": ["Reason", "Halt, h", "Halt events", "Share of halts", "Sort key"],
        "h_matrix": "Halt hours: machine × reason",
        "ch_h_machine": "Halt hours by machine", "ch_h_top": "Top halt reasons, h",
        # settings
        "settings_title": "Report settings",
        "set_hdr": ["Parameter", "Value", "How to use"],
        "set_rows": [("Shift", "Pick a shift or “All”"),
                     ("Department", "Pick a department or “All”"),
                     ("Date from", "Pick a day from the list (days present in Data)"),
                     ("Date to", "Inclusive; must not be earlier than “Date from”"),
                     ("Availability target", "Below target is flagged ▼ and red")],
        "status_bad": "⚠ “Date to” is earlier than “Date from” — every total will be 0",
        "status_ok": "✓ Filters are consistent",
        "overview": "Data overview",
        "overview_rows": ["Rows in the Data table", "First date", "Last date",
                          "Rows matching the filters"],
        "how": "How it works",
        "how_lines": [
            "Yellow cells are the only inputs. Everything else is a formula (SUMIFS / COUNTIFS).",
            "Type or paste new log rows directly under the table on the “Data” sheet: Excel extends "
            "the table, and every total, chart and the date dropdowns update — no Python needed.",
            "A brand-new machine / employee / reason needs one more row in the summary table "
            "(copy the row above) or a re-run of build_dashboard.py.",
            "Built for Excel 2013 or newer: no macros, no XLOOKUP / FILTER / dynamic arrays.",
        ],
        "legend_input": "input cell",
        "err_title": "Invalid value", "err_list": "Please pick a value from the list.",
        "err_pct": "Enter a percentage between 0% and 100%.",
        # import log
        "log_title": "Import log — what was cleaned",
        "log_hdr": ["Line in CSV", "Action", "Details"],
        "log_summary": "Summary",
        "log_empty": "No issues found: the file was clean.",
        "lists_note": "Helper sheet for dropdowns and filter criteria. Do not edit.",
    },
    "ru": {
        "sheets": {"dash": "Дашборд", "halts": "Простои", "settings": "Настройки", "data": "Данные",
                   "log": "Журнал загрузки", "lists": "Списки"},
        "columns": ["Дата", "Смена", "Цех", "Оборудование", "Сотрудник",
                    "ЧасыРаботы", "ПростойМин", "ПричинаПростоя"],
        "date_fmt": "dd.mm.yyyy",
        "all": "Все",
        "title": f"Производственный дашборд — {DEMO_BRAND}",
        "demo": "Демо-проект · Demo project — компания, люди и цифры вымышлены",
        "caption": ("Смена: ", "   ·   Цех: ", "   ·   Период: "),
        "caption_hint": "Фильтры меняются на листе «Настройки»",
        "kpi": ["Часы работы", "Часы простоя", "Доступность", "Смен в выборке", "Случаев простоя",
                "Главная причина"],
        "kpi_notes": ["сумма ЧасыРаботы", "ПростойМин ÷ 60", "работа ÷ (работа + простой)",
                      "строк по фильтрам", "строк с простоем", "по часам простоя"],
        "target": "цель",
        "by_department": "По цехам", "by_machine": "По оборудованию", "by_employee": "По сотрудникам",
        "table_note": "нулевые значения показаны как «–»",
        "hdr": ["Работа, ч", "Простой, ч", "Доступность", "Смен", "Доля простоев"],
        "department": "Цех", "machine": "Оборудование", "employee": "Сотрудник",
        "total": "Итого",
        "ch_dept": "Доступность по цехам и цель", "ch_machine": "Работа и простой по оборудованию, ч",
        "target_series": "Цель",
        "ch_emp": "Работа и простой по сотрудникам, ч",
        "halts_title": "Анализ простоев",
        "h_by_machine": "Часы простоя по оборудованию",
        "h_hdr": ["Цех", "Простой, ч", "Случаев", "Средний простой, мин", "Доля простоев",
                  "Главная причина"],
        "h_top": f"Топ-{TOP_N} причин простоя",
        "h_top_hdr": ["Место", "Причина", "Простой, ч", "Случаев", "Доля простоев"],
        "h_all": "Все причины (источник для рейтинга)",
        "h_all_hdr": ["Причина", "Простой, ч", "Случаев", "Доля простоев", "Ключ сортировки"],
        "h_matrix": "Часы простоя: оборудование × причина",
        "ch_h_machine": "Часы простоя по оборудованию", "ch_h_top": "Главные причины простоя, ч",
        "settings_title": "Настройки отчёта",
        "set_hdr": ["Параметр", "Значение", "Как пользоваться"],
        "set_rows": [("Смена", "Выберите смену или «Все»"),
                     ("Цех", "Выберите цех или «Все»"),
                     ("Дата с", "Выберите день из списка (дни, которые есть в данных)"),
                     ("Дата по", "Включительно; не раньше, чем «Дата с»"),
                     ("Целевая доступность", "Ниже цели — отметка ▼ и красный цвет")],
        "status_bad": "⚠ «Дата по» раньше, чем «Дата с» — все итоги будут равны 0",
        "status_ok": "✓ Фильтры заданы корректно",
        "overview": "Сводка по данным",
        "overview_rows": ["Строк в таблице «Данные»", "Первая дата", "Последняя дата",
                          "Строк по текущим фильтрам"],
        "how": "Как это работает",
        "how_lines": [
            "Жёлтые ячейки — единственные поля ввода. Всё остальное считается формулами "
            "(СУММЕСЛИМН / СЧЁТЕСЛИМН).",
            "Новые строки журнала вводите или вставляйте сразу под таблицей на листе «Данные»: Excel "
            "расширит таблицу, и все итоги, графики и списки дат пересчитаются — Python не нужен.",
            "Для нового станка / сотрудника / причины добавьте строку в сводную таблицу "
            "(скопируйте строку выше) или перезапустите build_dashboard.py.",
            "Работает в Excel 2013 и новее: без макросов, без XLOOKUP / FILTER / динамических "
            "массивов.",
        ],
        "legend_input": "поле ввода",
        "err_title": "Недопустимое значение", "err_list": "Выберите значение из списка.",
        "err_pct": "Введите процент от 0% до 100%.",
        "log_title": "Журнал загрузки — что было исправлено",
        "log_hdr": ["Строка CSV", "Действие", "Подробности"],
        "log_summary": "Итог",
        "log_empty": "Замечаний нет: файл был чистым.",
        "lists_note": "Служебный лист для выпадающих списков и критериев фильтра. Не редактировать.",
    },
}

ISSUE_TEXT = {
    "en": {
        "rejected_bad_date": "Rejected: unreadable date",
        "rejected_bad_number": "Rejected: unreadable number",
        "rejected_negative": "Rejected: negative value",
        "rejected_over_24h": "Rejected: more than 24 h in one row",
        "rejected_no_machine": "Rejected: no machine",
        "dropped_duplicate": "Removed: duplicate row",
        "filled_blank_reason": "Filled: halt without a reason",
        "normalised": "Normalised spelling",
        "filled": "Filled blank value",
    },
    "ru": {
        "rejected_bad_date": "Отклонено: дата не распознана",
        "rejected_bad_number": "Отклонено: число не распознано",
        "rejected_negative": "Отклонено: отрицательное значение",
        "rejected_over_24h": "Отклонено: больше 24 ч в одной строке",
        "rejected_no_machine": "Отклонено: не указано оборудование",
        "dropped_duplicate": "Удалено: дубликат строки",
        "filled_blank_reason": "Заполнено: простой без причины",
        "normalised": "Приведено написание",
        "filled": "Заполнено пустое значение",
    },
}


def _issue_text(kind: str, lang: str) -> str:
    texts = ISSUE_TEXT[lang]
    if kind in texts:
        return texts[kind]
    if kind.startswith("normalised_"):
        return f"{texts['normalised']} ({kind.split('_', 1)[1]})"
    if kind.startswith("filled_blank_"):
        return f"{texts['filled']} ({kind.split('_', 2)[2]})"
    return kind


class _Refs:
    """Structured references + the filter tail shared by every SUMIFS/COUNTIFS."""

    def __init__(self, columns: list[str]):
        (self.date, self.shift, self.dept, self.machine, self.employee,
         self.run, self.halt, self.reason) = (f"{TABLE}[{c}]" for c in columns)
        self.filters = (f'{self.shift},critShift,{self.dept},critDept,'
                        f'{self.date},">="&dFrom,{self.date},"<="&dTo')

    def run_sum(self, *crit: str) -> str:
        return f"SUMIFS({self.run},{self._crit(crit)})"

    def halt_hours(self, *crit: str) -> str:
        return f"SUMIFS({self.halt},{self._crit(crit)})/60"

    def count(self, *crit: str) -> str:
        return f"COUNTIFS({self._crit(crit)})"

    def _crit(self, crit: tuple[str, ...]) -> str:
        return ",".join((*crit, self.filters)) if crit else self.filters


def _chart_rows(height_cm: float) -> int:
    """Rows (15 pt each) covered by a chart of this height, minus one for the 30 pt header row."""
    return math.ceil(height_cm * 28.35 / 15) - 1


def build_dashboard(records: list[ProdRecord], out_path: str | Path, lang: str = "en",
                    report: LoadReport | None = None, target: float = 0.85) -> Path:
    if not records:
        raise ValueError("no records to build a dashboard from")
    L = LABELS[lang]
    S = L["sheets"]
    dims = dimension_values(records)
    m_dept = machine_department(records)
    refs = _Refs(L["columns"])

    wb = Workbook()
    ws_dash = wb.active
    ws_dash.title = S["dash"]
    ws_halts = wb.create_sheet(S["halts"])
    ws_set = wb.create_sheet(S["settings"])
    ws_data = wb.create_sheet(S["data"])
    ws_log = wb.create_sheet(S["log"])
    ws_lists = wb.create_sheet(S["lists"])

    _data_sheet(ws_data, records, L)
    _lists_sheet(wb, ws_lists, dims, L, lang, refs, S)
    _settings_sheet(wb, ws_set, records, L, refs, target, S)
    matrix_info = _halts_sheet(ws_halts, dims, m_dept, L, refs)
    _dashboard_sheet(ws_dash, dims, L, refs, S, matrix_info, ws_lists)
    _log_sheet(ws_log, report, L, lang)

    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    wb.properties.title = L["title"]
    wb.properties.creator = "xldash demo (github.com/sinnercode228)"
    wb.properties.description = L["demo"]
    wb.active = 0
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


# ---------------------------------------------------------------------------- Data

def _data_sheet(ws, records, L):
    base_sheet(ws, gridlines=True)
    ws.append(L["columns"])
    for r in records:
        ws.append([datetime(r.date.year, r.date.month, r.date.day), r.shift, r.department,
                   r.machine, r.employee, r.run_hours, r.halt_minutes, r.halt_reason or None])
    last = len(records) + 1
    table = Table(displayName=TABLE, ref=f"A1:H{last}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)
    for row in ws.iter_rows(min_row=2, max_row=last):
        row[0].number_format = L["date_fmt"]
        row[5].number_format = "0.00"
        row[6].number_format = "0"
        for c in row:
            c.font = font(10)
    for c in ws[1]:
        c.font = font(10, True, "FFFFFF")
    set_widths(ws, {"A": 12, "B": 12, "C": 16, "D": 15, "E": 22, "F": 12, "G": 13, "H": 24})
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------- Lists

def _lists_sheet(wb, ws, dims, L, lang, refs, S):
    ws.sheet_state = "hidden"
    ws["A1"], ws["B1"], ws["C1"] = L["set_rows"][0][0], L["set_rows"][1][0], L["columns"][0]
    shifts = [L["all"], *dims["shift"]]
    depts = [L["all"], *dims["department"]]
    for i, v in enumerate(shifts, start=2):
        ws.cell(row=i, column=1, value=v)
    for i, v in enumerate(depts, start=2):
        ws.cell(row=i, column=2, value=v)
    # live list of days: min(date) .. max(date), so new data extends the dropdown automatically
    ws["C2"] = f"=MIN({refs.date})"
    for r in range(3, DATE_LIST_LEN + 2):
        ws.cell(row=r, column=3,
                value=f'=IF(C{r-1}="","",IF(C{r-1}+1>MAX({refs.date}),"",C{r-1}+1))')
    for r in range(2, DATE_LIST_LEN + 2):
        ws.cell(row=r, column=3).number_format = "yyyy-mm-dd"  # ISO: parses in every locale

    helpers = [
        ("critShift", "Shift criterion", '=IF(OR(selShift="",selShift=$A$2),"*",selShift)'),
        ("critDept", "Department criterion", '=IF(OR(selDept="",selDept=$B$2),"*",selDept)'),
        ("dFrom", "Date from (effective)", f"=IF(ISNUMBER(selFrom),selFrom,MIN({refs.date}))"),
        ("dTo", "Date to (effective)", f"=IF(ISNUMBER(selTo),selTo,MAX({refs.date}))"),
        ("periodText", "Period text", f'={date_text("dFrom", lang)}&" – "&{date_text("dTo", lang)}'),
        ("filterCaption", "Caption",
         f'="{L["caption"][0]}"&IF(critShift="*",$A$2,selShift)&"{L["caption"][1]}"'
         f'&IF(critDept="*",$B$2,selDept)&"{L["caption"][2]}"&periodText'),
    ]
    for i, (name, label, formula) in enumerate(helpers, start=2):
        ws.cell(row=i, column=5, value=label)
        ws.cell(row=i, column=6, value=formula)
        wb.defined_names[name] = DefinedName(name, attr_text=f"{quote_sheet(S['lists'])}!$F${i}")
    ws["F4"].number_format = ws["F5"].number_format = "yyyy-mm-dd"
    ws["E10"] = L["lists_note"]
    lq = quote_sheet(S["lists"])
    wb.defined_names["lstShift"] = DefinedName("lstShift", attr_text=f"{lq}!$A$2:$A${len(shifts) + 1}")
    wb.defined_names["lstDept"] = DefinedName("lstDept", attr_text=f"{lq}!$B$2:$B${len(depts) + 1}")
    wb.defined_names["lstDates"] = DefinedName(
        "lstDates",
        attr_text=f"OFFSET({lq}!$C$2,0,0,MAX(1,COUNT({lq}!$C$2:$C${DATE_LIST_LEN + 1})),1)")
    set_widths(ws, {"A": 14, "B": 18, "C": 12, "E": 24, "F": 50})


# ---------------------------------------------------------------------------- Settings

def _settings_sheet(wb, ws, records, L, refs, target, S):
    base_sheet(ws)
    set_widths(ws, {"A": 2, "B": 26, "C": 18, "D": 62})
    title_bar(ws, L["settings_title"], 2, 4, subtitle=L["demo"])
    header_row(ws, 4, 2, L["set_hdr"])
    first = min(r.date for r in records)
    last = max(r.date for r in records)
    values = [L["all"], L["all"], datetime(first.year, first.month, first.day),
              datetime(last.year, last.month, last.day), target]
    names = ["selShift", "selDept", "selFrom", "selTo", "tgtAvail"]
    sq = quote_sheet(S["settings"])
    for i, ((label, hint), value, name) in enumerate(zip(L["set_rows"], values, names)):
        r = 5 + i
        body_cell(ws.cell(row=r, column=2, value=label), align="left", bold=True)
        cell = ws.cell(row=r, column=3, value=value)
        input_cell(cell, fmt="yyyy-mm-dd" if i in (2, 3) else ("0%" if i == 4 else None))
        body_cell(ws.cell(row=r, column=4, value=hint), align="left", color=INK_2)
        ws.row_dimensions[r].height = 22
        wb.defined_names[name] = DefinedName(name, attr_text=f"{sq}!$C${r}")

    def list_dv(source: str, cell: str):
        dv = DataValidation(type="list", formula1=source, allow_blank=True,
                            showErrorMessage=True, errorTitle=L["err_title"], error=L["err_list"])
        ws.add_data_validation(dv)
        dv.add(cell)

    list_dv("lstShift", "C5")
    list_dv("lstDept", "C6")
    list_dv("lstDates", "C7")
    list_dv("lstDates", "C8")
    pct = DataValidation(type="decimal", operator="between", formula1="0", formula2="1",
                         showErrorMessage=True, errorTitle=L["err_title"], error=L["err_pct"])
    ws.add_data_validation(pct)
    pct.add("C9")

    ws["B11"] = f'=IF(AND(ISNUMBER(selFrom),ISNUMBER(selTo),selTo<selFrom),"{L["status_bad"]}","{L["status_ok"]}")'
    ws["B11"].font = font(10, True)
    ws.conditional_formatting.add("B11", FormulaRule(
        formula=["AND(ISNUMBER(selFrom),ISNUMBER(selTo),selTo<selFrom)"], font=Font(color=BAD, bold=True)))
    ws.conditional_formatting.add("B11", FormulaRule(
        formula=["NOT(AND(ISNUMBER(selFrom),ISNUMBER(selTo),selTo<selFrom))"], font=Font(color=GOOD, bold=True)))

    section_title(ws, 13, 2, L["overview"])
    overview = [f"=COUNT({refs.date})", f"=MIN({refs.date})", f"=MAX({refs.date})",
                f"={refs.count()}"]
    for i, (label, formula) in enumerate(zip(L["overview_rows"], overview)):
        r = 14 + i
        body_cell(ws.cell(row=r, column=2, value=label), align="left")
        body_cell(ws.cell(row=r, column=3, value=formula),
                  fmt="yyyy-mm-dd" if i in (1, 2) else FMT_INT, align="center")

    section_title(ws, 19, 2, L["how"])
    for i, line in enumerate(L["how_lines"]):
        c = ws.cell(row=20 + i, column=2, value=f"{i + 1}. {line}")
        c.font = font(10, color=INK_2)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=20 + i, start_column=2, end_row=20 + i, end_column=4)
        ws.row_dimensions[20 + i].height = 30
    legend = ws.cell(row=25, column=2, value=L["legend_input"])
    input_cell(legend, align="left")
    legend.font = font(9, color="0000FF")
    ws.freeze_panes = "A4"


# ---------------------------------------------------------------------------- Halts

def _halts_sheet(ws, dims, m_dept, L, refs) -> dict:
    base_sheet(ws)
    set_widths(ws, {"A": 2, "B": 24, "C": 22, "D": 12, "E": 12, "F": 14, "G": 13, "H": 24, "I": 3})
    machines, reasons = dims["machine"], dims["halt_reason"]
    last_col = max(8 + 1 + 9, 3 + len(reasons) + 1)
    title_bar(ws, L["halts_title"], 2, last_col, subtitle=L["demo"])
    ws["B3"] = "=filterCaption"
    ws["B3"].font = font(10, True, INK_2)

    # --- matrix position is needed first (top-reason column points at it)
    n_m, n_r = len(machines), len(reasons)
    sec1 = 5
    sec1_end = sec1 + 2 + n_m                      # total row
    sec2 = max(sec1_end, sec1 + _chart_rows(7.5)) + 2
    sec2_end = sec2 + 1 + TOP_N
    sec3 = max(sec2_end, sec2 + _chart_rows(7)) + 2
    sec3_end = sec3 + 1 + n_r + 1
    sec4 = sec3_end + 2
    mx_hdr = sec4 + 1
    mx_first = mx_hdr + 1
    mx_last = mx_first + n_m - 1
    mx_c1, mx_cN = 3, 3 + n_r - 1                  # reason columns C..

    # --- 1. halt hours by machine
    section_title(ws, sec1, 2, L["h_by_machine"], L["table_note"])
    header_row(ws, sec1 + 1, 2, [L["machine"], *L["h_hdr"]])
    first = sec1 + 2
    tot = first + n_m
    for i, m in enumerate(machines):
        r = first + i
        body_cell(ws.cell(row=r, column=2, value=m), align="left")
        body_cell(ws.cell(row=r, column=3, value=m_dept.get(m, "")), align="left", color=INK_2)
        body_cell(ws.cell(row=r, column=4, value=f"={refs.halt_hours(refs.machine, f'$B{r}')}"), FMT_H)
        body_cell(ws.cell(row=r, column=5,
                          value=f'={refs.count(refs.machine, f"$B{r}", refs.halt, chr(34) + ">0" + chr(34))}'), FMT_INT)
        body_cell(ws.cell(row=r, column=6, value=f'=IF(E{r}=0,"",D{r}*60/E{r})'), FMT_MIN)
        body_cell(ws.cell(row=r, column=7, value=f"=IF($D${tot}=0,0,D{r}/$D${tot})"), FMT_PCT)
        mr = mx_first + i
        row_rng = f"${col(mx_c1)}${mr}:${col(mx_cN)}${mr}"
        hdr_rng = f"${col(mx_c1)}${mx_hdr}:${col(mx_cN)}${mx_hdr}"
        body_cell(ws.cell(row=r, column=8,
                          value=f'=IF(MAX({row_rng})<=0,"–",INDEX({hdr_rng},1,MATCH(MAX({row_rng}),{row_rng},0)))'),
                  align="left")
    _total_row(ws, tot, 2, 8, L["total"], {
        4: (f"=SUM(D{first}:D{tot - 1})", FMT_H),
        5: (f"=SUM(E{first}:E{tot - 1})", FMT_INT),
        6: (f'=IF(E{tot}=0,"",D{tot}*60/E{tot})', FMT_MIN),
        7: (f"=IF(D{tot}=0,0,1)", FMT_PCT),
    })
    ch = BarChart()
    ch.add_data(Reference(ws, min_col=4, min_row=sec1 + 1, max_row=tot - 1), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=2, min_row=first, max_row=tot - 1))
    style_bar_chart(ch, L["ch_h_machine"], horizontal=True, colors=(ORANGE,), legend=False,
                    number_format="#,##0", height=7.5, width=16)
    ws.add_chart(ch, f"J{sec1}")

    # --- 3. all reasons (computed first in formulas' logic, placed lower on the sheet)
    a_first = sec3 + 2
    a_last = a_first + n_r - 1
    a_tot = a_last + 1
    hours_rng = f"$C${a_first}:$C${a_last}"
    key_rng = f"$F${a_first}:$F${a_last}"
    name_rng = f"$B${a_first}:$B${a_last}"
    ev_rng = f"$D${a_first}:$D${a_last}"
    share_rng = f"$E${a_first}:$E${a_last}"
    section_title(ws, sec3, 2, L["h_all"])
    header_row(ws, sec3 + 1, 2, L["h_all_hdr"])
    for i, reason in enumerate(reasons):
        r = a_first + i
        body_cell(ws.cell(row=r, column=2, value=reason), align="left")
        body_cell(ws.cell(row=r, column=3, value=f"={refs.halt_hours(refs.reason, f'$B{r}')}"), FMT_H)
        body_cell(ws.cell(row=r, column=4,
                          value=f'={refs.count(refs.reason, f"$B{r}", refs.halt, chr(34) + ">0" + chr(34))}'), FMT_INT)
        body_cell(ws.cell(row=r, column=5, value=f"=IF($C${a_tot}=0,0,C{r}/$C${a_tot})"), FMT_PCT)
        # unique key for LARGE(): hours + a tiny row-based tie-breaker (earlier row wins)
        body_cell(ws.cell(row=r, column=6, value=f"=C{r}+(10000-ROW())/100000000"), "0.000000",
                  color=MUTED)
    _total_row(ws, a_tot, 2, 6, L["total"], {
        3: (f"=SUM(C{a_first}:C{a_last})", FMT_H),
        4: (f"=SUM(D{a_first}:D{a_last})", FMT_INT),
        5: (f"=IF(C{a_tot}=0,0,1)", FMT_PCT),
    })

    # --- 2. top N reasons (live ranking with LARGE + INDEX/MATCH)
    section_title(ws, sec2, 2, L["h_top"])
    header_row(ws, sec2 + 1, 2, L["h_top_hdr"])
    t_first = sec2 + 2
    n_top = min(TOP_N, n_r)
    for k in range(n_top):
        r = t_first + k
        pos = f"MATCH(LARGE({key_rng},$B{r}),{key_rng},0)"
        body_cell(ws.cell(row=r, column=2, value=k + 1), "0", align="center")
        body_cell(ws.cell(row=r, column=3,
                          value=f'=IF(INDEX({hours_rng},{pos})<=0,"",INDEX({name_rng},{pos}))'), align="left")
        body_cell(ws.cell(row=r, column=4, value=f'=IF(C{r}="","",INDEX({hours_rng},{pos}))'), FMT_H)
        body_cell(ws.cell(row=r, column=5, value=f'=IF(C{r}="","",INDEX({ev_rng},{pos}))'), FMT_INT)
        body_cell(ws.cell(row=r, column=6, value=f'=IF(C{r}="","",INDEX({share_rng},{pos}))'), FMT_PCT)
    ch = BarChart()
    ch.add_data(Reference(ws, min_col=4, min_row=sec2 + 1, max_row=t_first + n_top - 1), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=3, min_row=t_first, max_row=t_first + n_top - 1))
    style_bar_chart(ch, L["ch_h_top"], horizontal=True, colors=(ORANGE,), legend=False, height=7, width=16)
    ws.add_chart(ch, f"J{sec2}")

    # --- 4. machine x reason heat map
    section_title(ws, sec4, 2, L["h_matrix"])
    header_row(ws, mx_hdr, 2, [L["machine"], *reasons, L["total"]])
    for j in range(len(reasons) + 1):
        ws.column_dimensions[col(3 + j)].width = max(ws.column_dimensions[col(3 + j)].width or 0, 14)
    for i, m in enumerate(machines):
        r = mx_first + i
        body_cell(ws.cell(row=r, column=2, value=m), align="left")
        for j in range(n_r):
            c = mx_c1 + j
            body_cell(ws.cell(row=r, column=c,
                              value=f"={refs.halt_hours(refs.machine, f'$B{r}', refs.reason, f'{col(c)}${mx_hdr}')}"),
                      FMT_H, align="center")
        body_cell(ws.cell(row=r, column=mx_cN + 1, value=f"=SUM({col(mx_c1)}{r}:{col(mx_cN)}{r})"),
                  FMT_H, bold=True, align="center")
    tr = mx_last + 1
    _total_row(ws, tr, 2, mx_cN + 1, L["total"],
               {c: (f"=SUM({col(c)}{mx_first}:{col(c)}{mx_last})", FMT_H) for c in range(mx_c1, mx_cN + 2)})
    ws.conditional_formatting.add(
        f"{col(mx_c1)}{mx_first}:{col(mx_cN)}{mx_last}",
        ColorScaleRule(start_type="num", start_value=0, start_color="FFFFFF",
                       end_type="max", end_color="F2A07E"))
    ws.freeze_panes = "A4"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return {"top1": f"{quote_sheet(ws.title)}!$C${t_first}", "matrix_first": mx_first}


# ---------------------------------------------------------------------------- Dashboard

def _total_row(ws, r, c_first, c_last, label, cells: dict[int, tuple[str, str]]):
    for c in range(c_first, c_last + 1):
        cell = ws.cell(row=r, column=c)
        cell.border = TOP_DOUBLE
        cell.font = font(10, True)
        cell.fill = fill(PANEL)
    lab = ws.cell(row=r, column=c_first, value=label)
    lab.alignment = Alignment(horizontal="left", indent=1)
    for c, (formula, fmt) in cells.items():
        cell = ws.cell(row=r, column=c, value=formula)
        cell.number_format = fmt
        cell.alignment = Alignment(horizontal="right" if c_last - c_first < 7 else "center")


def _kpi_tile(ws, first_col, last_col, top, label, formula, fmt, note):
    for r in range(top, top + 4):
        for c in range(first_col, last_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = fill(PANEL)
    for c in range(first_col, last_col + 1):
        ws.cell(row=top, column=c).border = BOTTOM
    lab = ws.cell(row=top, column=first_col, value=label.upper())
    lab.font = font(8, True, INK_2)
    lab.alignment = Alignment(indent=1, vertical="center")
    ws.merge_cells(start_row=top + 1, start_column=first_col, end_row=top + 2, end_column=last_col)
    val = ws.cell(row=top + 1, column=first_col, value=formula)
    val.font = font(20, True, HEADER_FILL)
    val.alignment = Alignment(horizontal="left", vertical="center", indent=1, shrink_to_fit=True)
    if fmt:
        val.number_format = fmt
    n = ws.cell(row=top + 3, column=first_col, value=note)
    n.font = font(8, color=MUTED, italic=not str(note).startswith("="))
    n.alignment = Alignment(indent=1, vertical="center")
    return val


def _dashboard_sheet(ws, dims, L, refs, S, matrix_info, ws_lists):
    base_sheet(ws)
    set_widths(ws, {"A": 2, "B": 24, "C": 12, "D": 12, "E": 13, "F": 11, "G": 13, "H": 3,
                    "I": 3, **{col(c): 10.5 for c in range(10, 19)}})
    title_bar(ws, L["title"], 2, 18, subtitle=L["demo"])
    ws["B3"] = "=filterCaption"
    ws["B3"].font = font(10, True, INK_2)
    ws["J3"] = L["caption_hint"]
    ws["J3"].font = font(8, color=MUTED, italic=True)

    top = 5
    run, halt = refs.run_sum(), refs.halt_hours()
    tiles = [
        (2, 3, f"={run}", FMT_H),
        (4, 5, f"={halt}", FMT_H),
        (6, 7, '=IF(B6+D6=0,"",B6/(B6+D6))', FMT_PCT),
        (10, 12, f"={refs.count()}", FMT_INT),
        (13, 15, f'={refs.count(refs.halt, chr(34) + ">0" + chr(34))}', FMT_INT),
        (16, 18, f'=IF({matrix_info["top1"]}="","–",{matrix_info["top1"]})', None),
    ]
    for (c1, c2, formula, fmt), label, note in zip(tiles, L["kpi"], L["kpi_notes"]):
        _kpi_tile(ws, c1, c2, top, label, formula, fmt, note)
    # availability tile: arrow + target, colour paired with the ▲/▼ icon
    ws["F8"] = f'=IF(F6="","",IF(F6>=tgtAvail,"▲ ","▼ ")&"{L["target"]} "&ROUND(tgtAvail*100,1)&"%")'
    ws["F8"].font = font(9, True, INK_2)
    ws.conditional_formatting.add("F6:F8", FormulaRule(formula=['AND(ISNUMBER($F$6),$F$6>=tgtAvail)'],
                                                       font=Font(color=GOOD, bold=True)))
    ws.conditional_formatting.add("F6:F8", FormulaRule(formula=['AND(ISNUMBER($F$6),$F$6<tgtAvail)'],
                                                       font=Font(color=BAD, bold=True)))
    ws["P6"].font = font(14, True, HEADER_FILL)

    # chart helper on the hidden Lists sheet: the target as a flat line series
    ws_lists["H1"] = L["target_series"]
    for i in range(len(dims["department"])):
        ws_lists.cell(row=2 + i, column=8, value="=tgtAvail").number_format = "0%"

    r = 10
    sections = [
        ("by_department", "department", refs.dept, dims["department"], "dept"),
        ("by_machine", "machine", refs.machine, dims["machine"], "machine"),
        ("by_employee", "employee", refs.employee, dims["employee"], "emp"),
    ]
    for key, name_key, ref_col, values, kind in sections:
        r = _summary_section(ws, r, L, refs, key, name_key, ref_col, values, kind, ws_lists) + 2

    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_area = f"A1:R{r}"


def _below_target_rule(ws, cells: str, first: str) -> None:
    """Below target: red, bold and a ▼ in front of the number (never colour alone)."""
    dxf = DifferentialStyle(font=Font(color=BAD, bold=True),
                            numFmt=NumberFormat(numFmtId=300, formatCode='"▼ "0.0%'))
    rule = Rule(type="expression", dxf=dxf, formula=[f"AND(ISNUMBER({first}),{first}<tgtAvail)"])
    ws.conditional_formatting.add(cells, rule)


def _summary_section(ws, top, L, refs, key, name_key, ref_col, values, kind, ws_lists) -> int:
    """Table in B..G, chart to the right. Returns the last used row."""
    section_title(ws, top, 2, L[key], L["table_note"])
    header_row(ws, top + 1, 2, [L[name_key], *L["hdr"]])
    first = top + 2
    tot = first + len(values)
    for i, v in enumerate(values):
        r = first + i
        body_cell(ws.cell(row=r, column=2, value=v), align="left")
        body_cell(ws.cell(row=r, column=3, value=f"={refs.run_sum(ref_col, f'$B{r}')}"), FMT_H)
        body_cell(ws.cell(row=r, column=4, value=f"={refs.halt_hours(ref_col, f'$B{r}')}"), FMT_H)
        body_cell(ws.cell(row=r, column=5, value=f'=IF(C{r}+D{r}=0,"",C{r}/(C{r}+D{r}))'), FMT_PCT)
        body_cell(ws.cell(row=r, column=6, value=f"={refs.count(ref_col, f'$B{r}')}"), FMT_INT)
        body_cell(ws.cell(row=r, column=7, value=f"=IF($D${tot}=0,0,D{r}/$D${tot})"), FMT_PCT)
    _total_row(ws, tot, 2, 7, L["total"], {
        3: (f"=SUM(C{first}:C{tot - 1})", FMT_H),
        4: (f"=SUM(D{first}:D{tot - 1})", FMT_H),
        5: (f'=IF(C{tot}+D{tot}=0,"",C{tot}/(C{tot}+D{tot}))', FMT_PCT),
        6: (f"=SUM(F{first}:F{tot - 1})", FMT_INT),
        7: (f"=IF(D{tot}=0,0,1)", FMT_PCT),
    })
    _below_target_rule(ws, f"E{first}:E{tot - 1}", f"E{first}")

    ch = BarChart()
    if kind == "dept":
        ch.add_data(Reference(ws, min_col=5, min_row=top + 1, max_row=tot - 1), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=2, min_row=first, max_row=tot - 1))
        height = 7.5
        style_bar_chart(ch, L["ch_dept"], horizontal=False, colors=(BLUE,), legend=True,
                        number_format="0%", height=height, width=17, pct_axis=True)
        ch.dataLabels = DataLabelList(showVal=True, showSerName=False, showCatName=False,
                                      showLegendKey=False, showPercent=False)
        ch.dataLabels.numFmt = "0.0%"
        ch.dataLabels.position = "outEnd"
        ch.dataLabels.txPr = text_props(9, INK_2, bold=True)
        target = LineChart()
        target.add_data(Reference(ws_lists, min_col=8, min_row=1, max_row=1 + len(values)),
                        titles_from_data=True)
        line = target.series[0]
        line.graphicalProperties.line.solidFill = INK_2
        line.graphicalProperties.line.dashStyle = "dash"
        line.graphicalProperties.line.width = 19050      # 1.5 pt
        line.marker.symbol = "none"
        line.smooth = False
        ch += target
    else:
        ch.add_data(Reference(ws, min_col=3, max_col=4, min_row=top + 1, max_row=tot - 1),
                    titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=2, min_row=first, max_row=tot - 1))
        height = max(7.5, 0.55 * len(values) + 2.5)
        style_bar_chart(ch, L["ch_machine" if kind == "machine" else "ch_emp"], horizontal=True,
                        stacked=True, colors=(BLUE, ORANGE), height=height, width=17)
    ws.add_chart(ch, f"J{top}")
    return max(tot, top + _chart_rows(height))


# ---------------------------------------------------------------------------- Import log

def _log_sheet(ws, report: LoadReport | None, L, lang):
    base_sheet(ws)
    set_widths(ws, {"A": 2, "B": 13, "C": 40, "D": 60})
    title_bar(ws, L["log_title"], 2, 4, subtitle=L["demo"])
    if report is None:
        ws["B4"] = L["log_empty"]
        return
    ws["B4"] = L["log_summary"]
    ws["B4"].font = font(10, True)
    ws["C4"] = report.summary()
    ws["C4"].font = font(10, color=INK_2)
    if not report.issues:
        ws["B6"] = L["log_empty"]
        return
    header_row(ws, 6, 2, L["log_hdr"])
    for i, issue in enumerate(sorted(report.issues, key=lambda x: (x.line, x.kind)), start=7):
        body_cell(ws.cell(row=i, column=2, value=issue.line), "0", align="center")
        color = BAD if issue.kind.startswith("rejected") else INK_2
        body_cell(ws.cell(row=i, column=3, value=_issue_text(issue.kind, lang)), align="left", color=color)
        body_cell(ws.cell(row=i, column=4, value=issue.detail), align="left", color=INK_2)
    ws.freeze_panes = "A7"
