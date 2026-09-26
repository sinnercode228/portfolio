# portfolio

Здесь четыре демо-проекта (вместе 380 тестов) и одностраничное портфолио [`index.html`](index.html), которое GitHub Pages отдаёт по адресу https://sinnercode228.github.io/portfolio/.

Проекты покрупнее лежат в отдельных репозиториях, у каждого есть живое демо: [flowdesk-crm](https://github.com/sinnercode228/flowdesk-crm), [docmind-rag](https://github.com/sinnercode228/docmind-rag), [tg-shop-miniapp](https://github.com/sinnercode228/tg-shop-miniapp), [integration-hub](https://github.com/sinnercode228/integration-hub), [pulse-analytics](https://github.com/sinnercode228/pulse-analytics). Остальное в профиле: [github.com/sinnercode228](https://github.com/sinnercode228).

## Четыре демо

Компании и цифры в лендинге, боте и Excel-демо придуманы.

- [`landing-calculator/`](landing-calculator/) · [живое демо](https://sinnercode228.github.io/portfolio/landing-calculator/). Лендинг строительной компании «Полдень» на HTML/CSS/JS без сборки, с калькулятором стоимости дома. Заявки с формы принимает [serverless-функция](landing-calculator/serverless/telegram-lead.mjs) и отправляет в Telegram, на почту или в оба канала сразу. 49 тестов на `node:test`.
- [`scraper-demo/`](scraper-demo/). Асинхронный парсер учебного сайта books.toscrape.com на httpx и selectolax: ограничение запросов в секунду, повторы с экспоненциальной паузой, дисковый кэш. Выгрузка в XLSX, CSV, JSON и по желанию в Google Sheets. 80 тестов работают без сети, парсер и обход сайта проверяются на страницах, сохранённых в фикстурах.
- [`telegram-bot-demo/`](telegram-bot-demo/). Бот для заявок на aiogram 3 и SQLite: анкета в четыре шага, карточка заявки админам с кнопками статусов, выгрузка в CSV и рассылка. 139 тестов; диалоги пользователя и админа среди них идут через настоящие хендлеры с фейковой сессией Telegram из [`tests/fakes.py`](telegram-bot-demo/tests/fakes.py).
- [`excel-dashboard-demo/`](excel-dashboard-demo/). Скрипты на openpyxl собирают из сырых CSV книги Excel, где все показатели и итоги считаются формулами: дашборд производства с фильтрами и разбором простоев и счёт с зарплатой и маржой. 112 тестов, часть из них вычисляет формулы готовых книг через pycel и сверяет с эталонной реализацией на Python.

На каждый push и pull request [`.github/workflows/ci.yml`](.github/workflows/ci.yml) запускает `npm test` в лендинге, `pytest` во всех трёх Python-демо и `ruff check` в парсере и боте. Там же [`check_workbook.py`](excel-dashboard-demo/check_workbook.py) проверяет четыре книги Excel, закоммиченные в `excel-dashboard-demo/output/`.

<p>
  <img src="landing-calculator/docs/screenshot-calculator.jpg" height="240" alt="Калькулятор стоимости дома в landing-calculator">
  <img src="excel-dashboard-demo/docs/dashboard_ru.png" height="240" alt="Дашборд производства из excel-dashboard-demo">
</p>

## Клонировать и запустить

Команды для каждого проекта запускаются из корня репозитория. Переменные окружения и другие способы запуска описаны в README папок.

```bash
git clone https://github.com/sinnercode228/portfolio.git && cd portfolio

# landing-calculator: Node.js 22+, зависимостей нет
cd landing-calculator && npm test
npm start      # http://localhost:8080, или просто открыть index.html

# scraper-demo: Python 3.10+
cd scraper-demo && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && python -m pytest
python -m bookscraper --limit 100 --out output/books   # парсинг идёт по сети

# telegram-bot-demo: Python 3.11+
cd telegram-bot-demo && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && python -m pytest
python scripts/demo_dialog.py   # диалог с ботом в терминале, без токена и сети

# excel-dashboard-demo: Python 3.10+. setup создаёт venv, all генерирует CSV,
# собирает четыре книги в output/, проверяет формулы и запускает тесты
cd excel-dashboard-demo && make setup all
```

На Windows venv активируется через `.venv\Scripts\activate`; Makefile в excel-dashboard-demo рассчитан на Unix (`.venv/bin/python`).

## Страница `index.html`

Стили и скрипты лежат в самом файле, шрифты системные, с других доменов ничего не грузится; из репозитория подтягиваются только обложки из [`assets/projects/`](assets/projects/). Оба языка есть в разметке, лишний прячет CSS, так что без JS видна русская версия. Язык (`?lang=en` или сохранённый) и тему (сохранённую или системную) скрипт в `<head>` ставит до первой отрисовки. Кнопки RU/EN и темы запоминают выбор, при переключении на EN в адрес дописывается `?lang=en`.

Связь: Telegram [@sinnercode](https://t.me/sinnercode).
