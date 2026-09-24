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

import math
import numbers
import re
import shutil
import subprocess
import tempfile
import zipfile
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
NOT_EVALUATED = "#NOT-EVALUATED"   # pycel could not compute the formula (reported as an error)

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
    """Three small gaps in pycel 1.0b30 (patched in memory, the package is not modified):

    * it still builds ``ast.Str`` nodes, which Python 3.12+ removed
      (``ast.Constant`` is the drop-in replacement);
    * its WEEKDAY() ignores the ``return_type`` argument (Excel's WEEKDAY(x, 2)
      = Monday 1 ... Sunday 7). Patched with the Excel definition;
    * MATCH() / INDEX() over a one-cell range such as ``$C$9:$C$9`` receive a
      scalar and crash (Excel treats it as a 1x1 range). Wrapped accordingly.
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

    import pycel.lib.lookup as lk
    from pycel.excelutil import ERROR_CODES, list_like

    orig_match, orig_index = lk.match, lk.index

    @excel_helper(cse_params=0, number_params=2, err_str_params=(0, 2))
    def match(lookup_value, lookup_array, match_type=1):
        if not list_like(lookup_array) and lookup_array not in ERROR_CODES:
            lookup_array = ((lookup_array,),)
        return orig_match(lookup_value, lookup_array, match_type)

    @excel_helper(err_str_params=(1, 2), number_params=(1, 2))
    def index(array, row_num, col_num=None):
        if not list_like(array) and array not in ERROR_CODES:
            array = ((array,),)
        return orig_index(array, row_num, col_num)

    lk.match, lk.index = match, index


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
            try:
                value = xl.evaluate(f"'{sheet}'!{coord}")
            except Exception:                  # a pycel limitation must not hide the other results
                value = NOT_EVALUATED
            if hasattr(value, "tolist"):
                value = value.tolist()
            results[addr] = value
    return results


def find_errors(values: dict[str, object]) -> dict[str, str]:
    return {k: v for k, v in values.items()
            if isinstance(v, str) and (v in ERROR_VALUES or v == NOT_EVALUATED)}


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


# ------------------------------------------------------------------ cached values for previews

_CELL_RE = re.compile(r'<c r="([A-Z]+[0-9]+)"([^>]*)><f>(.*?)</f><v\s*/>', re.S)


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _sheet_files(zf: zipfile.ZipFile) -> dict[str, str]:
    """{'Sheet name': 'xl/worksheets/sheetN.xml'} from workbook.xml + its relationships."""
    wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
    rels_xml = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    targets = {}
    for rel in re.findall(r"<Relationship\b[^>]*>", rels_xml):
        rid, target = re.search(r'Id="([^"]+)"', rel), re.search(r'Target="([^"]+)"', rel)
        if rid and target:
            t = target.group(1)
            targets[rid.group(1)] = t.lstrip("/") if t.startswith("/") else "xl/" + t
    out = {}
    for sheet in re.findall(r"<sheet\b[^>]*>", wb_xml):
        name = re.search(r'name="([^"]*)"', sheet).group(1)
        rid = re.search(r'r:id="([^"]+)"', sheet).group(1)
        name = (name.replace("&quot;", '"').replace("&apos;", "'").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&amp;", "&"))
        out[name] = targets[rid]
    return out


def store_cached_values(path: str | Path, values: dict[str, object] | None = None) -> int:
    """Write the computed result next to every formula (<v> in the sheet XML).

    openpyxl saves formulas without results, so file previews that do not
    calculate (Quick Look, phone / mail / messenger previews) show 0 everywhere.
    Excel still recalculates on open (fullCalcOnLoad), so the cached values only
    affect such previews. Cells pycel could not evaluate are left empty.
    Returns the number of cells filled.
    """
    path = Path(path)
    values = evaluate_workbook(path) if values is None else values
    by_sheet: dict[str, dict[str, object]] = {}
    for addr, value in values.items():
        sheet, coord = addr.rsplit("!", 1)
        by_sheet.setdefault(sheet, {})[coord] = value

    filled = 0

    def cell(m: re.Match, cached: dict[str, object]) -> str:
        nonlocal filled
        ref, attrs, formula = m.group(1), m.group(2), m.group(3)
        v = cached.get(ref)
        if isinstance(v, list):                              # 1x1 array result
            v = v[0][0] if v and isinstance(v[0], list) else (v[0] if v else None)
        if v is None or v == NOT_EVALUATED or 't="' in attrs:
            return m.group(0)
        if isinstance(v, bool):
            t, text = "b", "1" if v else "0"
        elif isinstance(v, numbers.Real):
            f = float(v)
            if not math.isfinite(f):
                return m.group(0)
            t, text = None, str(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)
        elif isinstance(v, str) and v in ERROR_VALUES:
            t, text = "e", v
        else:
            t, text = "str", _xml_escape(str(v))
        filled += 1
        t_attr = f' t="{t}"' if t else ""
        return f'<c r="{ref}"{attrs}{t_attr}><f>{formula}</f><v>{text}</v>'

    tmp = path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        files = {v: k for k, v in _sheet_files(src).items()}
        for item in src.infolist():
            data = src.read(item.filename)
            sheet = files.get(item.filename)
            if sheet in by_sheet:
                xml = data.decode("utf-8")
                xml = _CELL_RE.sub(lambda m: cell(m, by_sheet[sheet]), xml)
                data = xml.encode("utf-8")
            dst.writestr(item, data)
    tmp.replace(path)
    return filled


def add_preview_values(path: str | Path) -> str:
    """store_cached_values() if pycel is installed; returns a one-line status for the CLI."""
    try:
        import pycel  # noqa: F401
    except ImportError:
        return ("note: pycel is not installed (pip install -r requirements-dev.txt), so file previews "
                "(Quick Look, phone) will show 0 until the workbook is opened in Excel")
    try:
        n = store_cached_values(path)
    except Exception as exc:                  # the workbook itself is already saved and valid
        return f"note: computed values were not stored for previews ({exc})"
    return f"Stored computed values of {n} formulas (for previews; Excel recalculates on open)"
