"""Generators of fictional sample data.

* ``generate_production_rows`` - one row per machine per shift per day
  (date, shift, department, machine, employee, run hours, halt minutes, halt reason).
* ``generate_worklog_rows`` - a freelancer/agency time log for the invoice demo.

Everything is deterministic for a given ``seed``. With ``messy=True`` the
production log gets the kind of noise real exports have (extra spaces,
mixed case, decimal commas, other date formats, duplicates, a couple of
invalid rows) so the loader's cleaning step has something to do.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

SHIFT_HOURS = 8.0

DEPARTMENTS = {
    "machining": {"en": "Machining", "ru": "Мехобработка"},
    "assembly": {"en": "Assembly", "ru": "Сборка"},
    "welding": {"en": "Welding", "ru": "Сварка"},
    "painting": {"en": "Painting", "ru": "Покраска"},
}

SHIFTS = {
    "day": {"en": "Day", "ru": "Дневная"},
    "evening": {"en": "Evening", "ru": "Вечерняя"},
    "night": {"en": "Night", "ru": "Ночная"},
}

# code, department, shifts it runs, breakdown factor (1.0 = average machine)
MACHINES = [
    ("CNC-01", "machining", ("day", "evening", "night"), 1.0),
    ("CNC-02", "machining", ("day", "evening", "night"), 1.8),
    ("CNC-03", "machining", ("day", "evening", "night"), 0.7),
    ("ASM-01", "assembly", ("day", "evening"), 0.8),
    ("ASM-02", "assembly", ("day", "evening"), 1.1),
    ("WLD-01", "welding", ("day", "evening"), 1.0),
    ("WLD-02", "welding", ("day", "evening"), 1.4),
    ("PNT-01", "painting", ("day",), 1.2),
]

# key: (en, ru, weight, (min_minutes, max_minutes))
HALT_REASONS = {
    "setup": ("Setup / changeover", "Переналадка", 0.30, (30, 110)),
    "material": ("No material", "Нет материала", 0.20, (40, 200)),
    "breakdown": ("Breakdown", "Поломка", 0.14, (60, 360)),
    "quality": ("Quality check", "Контроль качества", 0.16, (15, 60)),
    "tooling": ("Tool change", "Замена инструмента", 0.12, (15, 45)),
    "maintenance": ("Planned maintenance", "Плановое ТО", 0.08, (90, 180)),
}

_FIRST_EN = ["Alex", "Jordan", "Casey", "Morgan", "Riley", "Taylor", "Jamie", "Avery",
             "Quinn", "Drew", "Robin", "Sam", "Charlie", "Emerson", "Hayden", "Parker",
             "Reese", "Rowan", "Skyler", "Blake"]
_LAST_EN = ["Hart", "Ellison", "Brooks", "Mercer", "Lang", "Fenwick", "Doyle", "Harlow",
            "Pryce", "Vance", "Keller", "Marsh", "Tate", "Wilder", "Crane", "Ashby",
            "Holt", "Sutter", "Rhodes", "Quill"]
_LAST_RU = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов",
            "Михайлов", "Новиков", "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев",
            "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев"]
_INITIALS_RU = ["А.", "Б.", "В.", "Г.", "Д.", "Е.", "И.", "К.", "Л.", "М.", "Н.", "О.",
                "П.", "Р.", "С.", "Т."]

PRODUCTION_HEADERS = {
    "en": ["date", "shift", "department", "machine", "employee",
           "run_hours", "halt_minutes", "halt_reason"],
    "ru": ["Дата", "Смена", "Цех", "Оборудование", "Сотрудник",
           "Часы работы", "Простой, мин", "Причина простоя"],
}


@dataclass
class _Slot:
    machine: str
    department: str
    shift: str
    employee: str
    skill: float  # multiplies setup / quality durations (lower = faster)


def _employee_names(rng: random.Random, count: int, lang: str) -> list[str]:
    names: set[str] = set()
    while len(names) < count:
        if lang == "ru":
            names.add(f"{rng.choice(_LAST_RU)} {rng.choice(_INITIALS_RU)}{rng.choice(_INITIALS_RU)}")
        else:
            names.add(f"{rng.choice(_FIRST_EN)} {rng.choice(_LAST_EN)}")
    return sorted(names)


def _staffing(rng: random.Random, lang: str) -> list[_Slot]:
    """One operator per machine per shift (fixed crews, like a real rota)."""
    slots = [(m, d, s) for m, d, shifts, _ in MACHINES for s in shifts]
    names = _employee_names(rng, len(slots), lang)
    rng.shuffle(names)
    return [
        _Slot(m, d, s, names[i], round(rng.uniform(0.75, 1.3), 2))
        for i, (m, d, s) in enumerate(slots)
    ]


def _pick_reason(rng: random.Random, breakdown_factor: float) -> str:
    keys = list(HALT_REASONS)
    weights = [HALT_REASONS[k][2] * (breakdown_factor if k == "breakdown" else 1.0) for k in keys]
    return rng.choices(keys, weights=weights, k=1)[0]


def generate_production_rows(
    start: date = date(2026, 9, 1),
    days: int = 30,
    seed: int = 42,
    lang: str = "en",
) -> list[dict]:
    """Clean production rows with canonical keys and python types."""
    if lang not in ("en", "ru"):
        raise ValueError("lang must be 'en' or 'ru'")
    if days < 1:
        raise ValueError("days must be >= 1")
    rng = random.Random(seed)
    crew = _staffing(rng, lang)
    factor = {m: f for m, _, _, f in MACHINES}
    rows: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        weekday = day.weekday()  # 0 = Monday
        if weekday == 6:  # Sunday: plant closed
            continue
        for slot in crew:
            if weekday == 5 and slot.shift != "day":  # Saturday: day shift only
                continue
            if rng.random() < 0.05:  # operator absent -> machine not staffed, no row
                continue
            halt = 0
            reason = ""
            p_halt = min(0.92, 0.62 * (0.55 + 0.45 * factor[slot.machine]))
            if rng.random() < p_halt:
                reason = _pick_reason(rng, factor[slot.machine])
                lo, hi = HALT_REASONS[reason][3]
                minutes = rng.uniform(lo, hi)
                if reason in ("setup", "quality", "tooling"):
                    minutes *= slot.skill
                halt = int(min(SHIFT_HOURS * 60 - 30, max(5, round(minutes / 5) * 5)))
            run = round(SHIFT_HOURS - halt / 60, 2)
            rows.append({
                "date": day,
                "shift": SHIFTS[slot.shift][lang],
                "department": DEPARTMENTS[slot.department][lang],
                "machine": slot.machine,
                "employee": slot.employee,
                "run_hours": run,
                "halt_minutes": halt,
                "halt_reason": HALT_REASONS[reason][0 if lang == "en" else 1] if reason else "",
            })
    return rows


def _fmt_number(value: float, lang: str) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if lang == "ru" else text


def _fmt_date(value: date, lang: str) -> str:
    return value.strftime("%d.%m.%Y") if lang == "ru" else value.isoformat()


def production_rows_to_text(rows: Iterable[dict], lang: str) -> list[list[str]]:
    """Render rows the way the plant's system would export them."""
    out = []
    for r in rows:
        out.append([
            _fmt_date(r["date"], lang), r["shift"], r["department"], r["machine"], r["employee"],
            _fmt_number(r["run_hours"], lang), str(int(r["halt_minutes"])), r["halt_reason"],
        ])
    return out


# Number of intentionally broken rows added by messy mode (tests rely on these).
MESSY_INVALID_ROWS = 2
MESSY_DUPLICATES = 3


def make_messy(text_rows: list[list[str]], seed: int, lang: str) -> list[list[str]]:
    """Add realistic export noise. Values stay recoverable except the invalid rows."""
    rng = random.Random(seed + 1)
    rows = [list(r) for r in text_rows]
    for r in rows:
        roll = rng.random()
        if roll < 0.03:
            r[4] = f"  {r[4]} "                      # stray spaces in the name
        elif roll < 0.05:
            r[1] = r[1].lower()                       # "day" instead of "Day"
        elif roll < 0.07:
            r[3] = r[3].lower() + " "                 # "cnc-02 "
        elif roll < 0.09 and lang == "en":
            r[5] = r[5].replace(".", ",")             # decimal comma in an EN file
        elif roll < 0.11:
            d = r[0]                                  # other date notation
            if lang == "en":
                y, m, dd = d.split("-")
                r[0] = f"{dd}.{m}.{y}"
            else:
                dd, m, y = d.split(".")
                r[0] = f"{y}-{m}-{dd}"
        elif roll < 0.13 and r[6] != "0":
            r[7] = ""                                 # halt without a reason
    # exact duplicates (double export)
    for _ in range(MESSY_DUPLICATES):
        rows.insert(rng.randrange(len(rows)), list(rng.choice(rows)))
    # invalid rows that must be rejected
    bad_date = list(rng.choice(rows))
    bad_date[0] = "2026-13-45" if lang == "en" else "45.13.2026"
    bad_number = list(rng.choice(rows))
    bad_number[6] = "-15"
    rows.insert(rng.randrange(len(rows)), bad_date)
    rows.insert(rng.randrange(len(rows)), bad_number)
    return rows


def write_production_csv(
    path: str | Path,
    start: date = date(2026, 9, 1),
    days: int = 30,
    seed: int = 42,
    lang: str = "en",
    messy: bool = False,
) -> int:
    """Write the sample log. EN: comma + ISO dates; RU: semicolon + dd.mm.yyyy + decimal comma
    (what Russian-locale Excel/1C exports look like). Returns the number of data lines."""
    rows = generate_production_rows(start, days, seed, lang)
    text_rows = production_rows_to_text(rows, lang)
    if messy:
        text_rows = make_messy(text_rows, seed, lang)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";" if lang == "ru" else ",")
        writer.writerow(PRODUCTION_HEADERS[lang])
        writer.writerows(text_rows)
    return len(text_rows)


# --------------------------------------------------------------------------- work log

TEAM = [
    # employee, role(en), role(ru), bill rate USD, pay rate USD, bill rate RUB, pay rate RUB
    ("Mira Solberg", "Lead developer", "Ведущий разработчик", 55, 38, 3500, 2400),
    ("Theo Varga", "Developer", "Разработчик", 40, 27, 2600, 1700),
    ("Ines Okafor", "QA engineer", "Тестировщик", 30, 19, 1900, 1200),
    ("Luca Brenner", "UI designer", "UI-дизайнер", 35, 24, 2300, 1500),
]
TEAM_RU_NAMES = {
    "Mira Solberg": "Сольберг Мира",
    "Theo Varga": "Варга Тео",
    "Ines Okafor": "Окафор Инес",
    "Luca Brenner": "Бреннер Лука",
}

PROJECTS = {
    "portal": ("Customer portal", "Клиентский портал"),
    "mobile": ("Shop-floor mobile app", "Мобильное приложение для цеха"),
    "support": ("Support & maintenance", "Поддержка"),
}

TASKS = {
    "portal": [("Order status page", "Страница статуса заказа"),
               ("Login and roles", "Авторизация и роли"),
               ("Reports export", "Выгрузка отчётов"),
               ("Code review", "Код-ревью")],
    "mobile": [("Barcode scanning", "Сканирование штрихкодов"),
               ("Offline sync", "Офлайн-синхронизация"),
               ("Push notifications", "Push-уведомления")],
    "support": [("Bug fixes", "Исправление ошибок"),
                ("Server updates", "Обновление сервера"),
                ("Client call", "Созвон с клиентом")],
}

ROLE_WORK = {  # which projects each role touches (weights)
    "Lead developer": {"portal": 0.45, "mobile": 0.35, "support": 0.20},
    "Developer": {"portal": 0.55, "mobile": 0.35, "support": 0.10},
    "QA engineer": {"portal": 0.50, "mobile": 0.40, "support": 0.10},
    "UI designer": {"portal": 0.60, "mobile": 0.40, "support": 0.00},
}

WORKLOG_HEADERS = {
    "en": ["date", "employee", "project", "task", "hours", "billable"],
    "ru": ["Дата", "Сотрудник", "Проект", "Задача", "Часы", "Оплачиваемо"],
}
RATES_HEADERS = {
    "en": ["employee", "role", "bill_rate", "pay_rate"],
    "ru": ["Сотрудник", "Роль", "Ставка клиенту", "Ставка сотруднику"],
}


def team_name(name: str, lang: str) -> str:
    return TEAM_RU_NAMES[name] if lang == "ru" else name


def generate_worklog_rows(
    start: date = date(2026, 8, 25),
    end: date = date(2026, 10, 3),
    seed: int = 7,
    lang: str = "en",
) -> list[dict]:
    """Time entries on weekdays. The range deliberately spills past the invoice
    month so the date filter has something to exclude."""
    rng = random.Random(seed)
    yes, no = ("Да", "Нет") if lang == "ru" else ("Yes", "No")
    li = 1 if lang == "ru" else 0
    rows = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            for name, role, *_ in TEAM:
                if rng.random() < 0.08:  # day off
                    continue
                remaining = rng.choice([6.0, 7.0, 7.5, 8.0, 8.0, 8.5])
                weights = ROLE_WORK[role]
                while remaining > 0.2:
                    project = rng.choices(list(weights), weights=list(weights.values()))[0]
                    task = rng.choice(TASKS[project])[li]
                    # odd durations on purpose: billing rounds each entry UP to the increment
                    hours = min(remaining, round(rng.uniform(0.3, 4.2), 2))
                    remaining = round(remaining - hours, 2)
                    billable = no if (project == "support" and rng.random() < 0.3) or rng.random() < 0.04 else yes
                    rows.append({
                        "date": day,
                        "employee": team_name(name, lang),
                        "project": PROJECTS[project][li],
                        "task": task,
                        "hours": hours,
                        "billable": billable,
                    })
        day += timedelta(days=1)
    return rows


def write_worklog_csv(path: str | Path, seed: int = 7, lang: str = "en",
                      start: date = date(2026, 8, 25), end: date = date(2026, 10, 3)) -> int:
    rows = generate_worklog_rows(start, end, seed, lang)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";" if lang == "ru" else ",")
        writer.writerow(WORKLOG_HEADERS[lang])
        for r in rows:
            writer.writerow([_fmt_date(r["date"], lang), r["employee"], r["project"], r["task"],
                             _fmt_number(r["hours"], lang), r["billable"]])
    return len(rows)


def write_rates_csv(path: str | Path, lang: str = "en") -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";" if lang == "ru" else ",")
        writer.writerow(RATES_HEADERS[lang])
        for name, role_en, role_ru, bill_usd, pay_usd, bill_rub, pay_rub in TEAM:
            if lang == "ru":
                writer.writerow([team_name(name, lang), role_ru, bill_rub, pay_rub])
            else:
                writer.writerow([name, role_en, bill_usd, pay_usd])
    return len(TEAM)
