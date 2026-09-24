"""Check generated workbooks without Excel.

1. ``lint_workbook``   static checks of every formula: allowed functions only
   (Excel 2013-safe list, no XLOOKUP/FILTER/dynamic arrays), balanced brackets
   and quotes, existing sheets / tables / table columns / defined names,
   locale traps (TEXT with a format code).
2. ``evaluate_workbook`` really computes the formulas with pycel. pycel does not
   understand Excel Tables or defined names, so a temporary copy is made where
   ``tblData[Col]`` and names like ``critShift`` are rewritten to plain A1
   ranges (the meaning is identical). Input cells can be overridden to simulate
   a user changing the filters on the Settings sheet.

If LibreOffice is installed, ``recalc_with_libreoffice`` is an extra check.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.utils.datetime import to_excel

# Excel 2007-2013 functions this project is allowed to use.
ALLOWED_FUNCTIONS = {
    "ABS", "AND", "AVERAGE", "AVERAGEIFS", "CEILING", "CHOOSE", "COUNT", "COUNTA", "COUNTIF",
    "COUNTIFS", "DATE", "DAY", "IF", "IFERROR", "INDEX", "INT", "ISBLANK", "ISNA", "ISNUMBER",
    "LARGE", "LEFT", "LEN", "MATCH", "MAX", "MIN", "MONTH", "NOT", "OFFSET", "OR", "RANK",
    "RIGHT", "ROUND", "ROUNDDOWN", "ROUNDUP", "ROW", "ROWS", "SMALL", "SUM", "SUMIF", "SUMIFS",
    "SUMPRODUCT", "WEEKDAY", "YEAR", "MOD", "MEDIAN",
}
# Newer than Excel 2013 or spilling dynamic-array functions: must never appear.
FORBIDDEN_FUNCTIONS = {
    "XLOOKUP", "XMATCH", "FILTER", "SORT", "SORTBY", "UNIQUE", "SEQUENCE", "RANDARRAY", "LET",
    "LAMBDA", "IFS", "SWITCH", "MAXIFS", "MINIFS", "TEXTJOIN", "CONCAT", "TEXTSPLIT", "VSTACK",
    "HSTACK", "TAKE", "DROP", "CHOOSECOLS", "CHOOSEROWS", "TOCOL", "TOROW", "WRAPROWS",
    "WRAPCOLS", "EXPAND", "MAP", "REDUCE", "SCAN", "BYROW", "BYCOL", "MAKEARRAY",
}
ERROR_VALUES = ("#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A")

_FUNC_RE = re.compile(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_.]*)\s*\(")
_STRUCT_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\[([^\[\]]+)\]")
_THISROW_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\[\[#This Row\],\[([^\[\]]+)\]\]")
_NAME_RE = re.compile(r"(?<![\w.$!'\]#])([A-Za-z_][A-Za-z0-9_]*)(?![\w(!\[$])")
_SHEET_RE = re.compile(r"(?:'((?:[^']|'')+)'|([A-Za-z_Ѐ-ӿ][\w.Ѐ-ӿ]*))!")


@dataclass
class LintResult:
    formulas: int = 0
    functions: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _outside_strings(formula: str) -> list[tuple[bool, str]]:
    """Split a formula into (is_code, text) chunks so string literals are left alone."""
    parts = formula.split('"')
    return [(i % 2 == 0, p) for i, p in enumerate(parts)]


def _code_only(formula: str) -> str:
    return " ".join(p for is_code, p in _outside_strings(formula) if is_code)


def _tables(wb) -> dict[str, dict]:
    out = {}
    for ws in wb.worksheets:
        for tbl in ws.tables.values():
            min_col, min_row, max_col, max_row = range_boundaries(tbl.ref)
            headers = [ws.cell(row=min_row, column=c).value for c in range(min_col, max_col + 1)]
            out[tbl.displayName.lower()] = {
                "sheet": ws.title, "headers": {str(h).lower(): min_col + i for i, h in enumerate(headers)},
                "first": min_row + 1, "last": max_row,
            }
    return out


def _names(wb) -> dict[str, str]:
    return {n.lower(): dn.attr_text for n, dn in wb.defined_names.items()}


def iter_formulas(wb):
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    yield ws.title, c.coordinate, c.value


def lint_workbook(path: str | Path) -> LintResult:
    wb = load_workbook(path)
    res = LintResult()
    tables = _tables(wb)
    names = _names(wb)
    sheets = {ws.title for ws in wb.worksheets}

    def check(where: str, formula: str):
        code = _code_only(formula)
        if formula.count('"') % 2:
            res.problems.append(f"{where}: unbalanced quotes: {formula}")
        depth = 0
        for ch in code:
            depth += (ch == "(") - (ch == ")")
            if depth < 0:
                break
        if depth != 0:
            res.problems.append(f"{where}: unbalanced parentheses: {formula}")
        for fn in _FUNC_RE.findall(code):
            name = fn.upper().removeprefix("_XLFN.")
            res.functions[name] = res.functions.get(name, 0) + 1
            if name in FORBIDDEN_FUNCTIONS:
                res.problems.append(f"{where}: {name} is not available in Excel 2013")
            elif name not in ALLOWED_FUNCTIONS:
                res.problems.append(f"{where}: function {name} is not on the allowed list")
            if name == "TEXT":
                res.warnings.append(f"{where}: TEXT() format codes depend on Excel's language")
        for tbl, column in _THISROW_RE.findall(code) + _STRUCT_RE.findall(_THISROW_RE.sub(" ", code)):
            t = tables.get(tbl.lower())
            if t is None:
                res.problems.append(f"{where}: unknown table {tbl}")
            elif column.lower() not in t["headers"]:
                res.problems.append(f"{where}: table {tbl} has no column {column!r}")
        for quoted, bare in _SHEET_RE.findall(code):
            sheet = (quoted or bare).replace("''", "'")
            if sheet not in sheets:
                res.problems.append(f"{where}: unknown sheet {sheet!r}")
        stripped = _STRUCT_RE.sub(" ", _THISROW_RE.sub(" ", code))
        stripped = re.sub(r"'(?:[^']|'')+'!", " ", stripped)
        for token in _NAME_RE.findall(stripped):
            if re.fullmatch(r"[A-Za-z]{1,3}\d+", token) or token.upper() in ("TRUE", "FALSE"):
                continue
            if token.lower() not in names:
                res.problems.append(f"{where}: unknown name {token!r}")

    for ws in wb.worksheets:                  # table XML column names must equal the header cells
        for tbl in ws.tables.values():
            min_col, min_row, max_col, _ = range_boundaries(tbl.ref)
            headers = [str(ws.cell(row=min_row, column=c).value) for c in range(min_col, max_col + 1)]
            names_xml = [tc.name for tc in tbl.tableColumns]
            if names_xml and names_xml != headers:
                res.problems.append(f"table {tbl.displayName}: column names {names_xml} != headers {headers}")
    for sheet, coord, formula in iter_formulas(wb):
        res.formulas += 1
        check(f"{sheet}!{coord}", formula)
    for name, target in names.items():
        check(f"name {name}", "=" + target)
    for ws in wb.worksheets:
        for dv in ws.data_validations.dataValidation:
            if dv.type == "list" and dv.formula1 and not dv.formula1.startswith('"'):
                check(f"{ws.title} validation {dv.sqref}", "=" + dv.formula1)
    return res


# ------------------------------------------------------------------ evaluation (pycel)

def _rewrite(formula: str, tables: dict, names: dict[str, str], row: int) -> str:
    def this_row(m: re.Match) -> str:
        t = tables[m.group(1).lower()]
        c = get_column_letter(t["headers"][m.group(2).lower()])
        return f"'{t['sheet'].replace(chr(39), chr(39) * 2)}'!${c}${row}"

    def struct(m: re.Match) -> str:
        t = tables[m.group(1).lower()]
        c = get_column_letter(t["headers"][m.group(2).lower()])
        sheet = t["sheet"].replace("'", "''")
        return f"'{sheet}'!${c}${t['first']}:${c}${t['last']}"

    def name(m: re.Match) -> str:
        target = names.get(m.group(1).lower())
        return target if target and "(" not in target else m.group(1)

    out = []
    for is_code, chunk in _outside_strings(formula):
        if is_code:
            parts = re.split(r"('(?:[^']|'')+'!)", chunk)       # keep quoted sheet names intact
            chunk = "".join(p if p.startswith("'") else _NAME_RE.sub(name, p) for p in parts)
            chunk = _THISROW_RE.sub(this_row, chunk)
            chunk = _STRUCT_RE.sub(struct, chunk)
        out.append(chunk)
    return '"'.join(out)


def prepare_for_pycel(src: str | Path, dst: str | Path, overrides: dict[str, object] | None = None) -> None:
    """Copy of the workbook that pycel can evaluate (tables/names expanded, dates as serials)."""
    wb = load_workbook(src)
    tables = _tables(wb)
    names = _names(wb)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("="):
                    c.value = _rewrite(v, tables, names, c.row)
                elif isinstance(v, (datetime, date)):
                    c.value = float(to_excel(v))
    for key, value in (overrides or {}).items():
        sheet, coord = key.rsplit("!", 1)
        if isinstance(value, (datetime, date)):
            value = float(to_excel(value))
        wb[sheet.strip("'")][coord] = value
    for tbl_ws in wb.worksheets:              # pycel reads plain ranges; drop table/name metadata
        for tname in list(tbl_ws.tables):
            del tbl_ws.tables[tname]
    for n in list(wb.defined_names):
        del wb.defined_names[n]
    wb.save(dst)


def _pycel_compat() -> None:
    """Two small gaps in pycel 1.0b30:

    * it still builds ``ast.Str`` nodes, which Python 3.12+ removed
      (``ast.Constant`` is the drop-in replacement);
    * its WEEKDAY() ignores the ``return_type`` argument (Excel's WEEKDAY(x, 2)
      = Monday 1 ... Sunday 7). Patched with the Excel definition.
    """
    import ast
    import math

    if not hasattr(ast, "Str"):
        def _str(s=None, **_kw):
            return ast.Constant(value=s)
        ast.Str = _str  # type: ignore[attr-defined]

    import pycel.lib.date_time as dt
    from pycel.excelutil import NUM_ERROR
    from pycel.lib.function_helpers import excel_helper

    if getattr(dt.weekday, "_xldash", False):
        return

    @excel_helper(number_params=(0, 1))
    def weekday(serial_number, return_type=1):
        if serial_number < 0:
            return NUM_ERROR
        sunday0 = (math.floor(serial_number) - 1) % 7        # 0 = Sunday
        if return_type == 1:
            return sunday0 + 1
        if return_type == 2:
            return (sunday0 + 6) % 7 + 1
        if return_type == 3:
            return (sunday0 + 6) % 7
        return NUM_ERROR

    weekday._xldash = True
    dt.weekday = weekday


def evaluate_workbook(path: str | Path, overrides: dict[str, object] | None = None,
                      sheets: list[str] | None = None) -> dict[str, object]:
    """Evaluate every formula (optionally only on some sheets). Returns {'Sheet!A1': value}."""
    _pycel_compat()
    from pycel import ExcelCompiler

    src_wb = load_workbook(path)
    wanted = [(s, c) for s, c, _ in iter_formulas(src_wb) if sheets is None or s in sheets]
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "eval.xlsx"
        prepare_for_pycel(path, dst, overrides)
        xl = ExcelCompiler(filename=str(dst), cycles=False)
        results = {}
        for sheet, coord in wanted:
            addr = f"{sheet}!{coord}"
            value = xl.evaluate(f"'{sheet}'!{coord}")
            if hasattr(value, "tolist"):
                value = value.tolist()
            results[addr] = value
    return results


def find_errors(values: dict[str, object]) -> dict[str, str]:
    return {k: v for k, v in values.items() if isinstance(v, str) and v in ERROR_VALUES}


def recalc_with_libreoffice(path: str | Path, timeout: int = 120) -> Path | None:
    """Headless LibreOffice round-trip (only if soffice is installed). Returns the recalculated copy."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    out_dir = Path(tempfile.mkdtemp())
    subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx", "--outdir",
                    str(out_dir), str(path)], check=True, timeout=timeout,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_dir / Path(path).name
