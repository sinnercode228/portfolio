# Портфолио sinnercode228 · Python / JavaScript

> **Демо-проект / Demo project.** Все проекты в этом репозитории демонстрационные: компании, люди и цифры в них вымышлены. Код рабочий, тесты проходят.

[Русский](#русский) · [English](#english)

**Страница портфолио:** https://sinnercode228.github.io/portfolio/ (английская версия: [`?lang=en`](https://sinnercode228.github.io/portfolio/?lang=en))

---

## Русский

Беру задачи на Python и JavaScript с понятным результатом: парсеры и сбор данных, Telegram-боты, автоматизация и интеграции по API, лендинги, Excel и Google Sheets, исправление багов. Ниже четыре демо-проекта, каждый с подробным README, инструкцией по запуску и автотестами.

### Проекты

| Проект | Что это | Стек | Тесты |
|---|---|---|---|
| [**landing-calculator**](landing-calculator/) · [живое демо](https://sinnercode228.github.io/portfolio/landing-calculator/) | Лендинг строительной компании «Полдень» с калькулятором стоимости дома: итог, срок и смета по статьям, ссылка на расчёт, форма заявки в Telegram или на почту через serverless-функцию | HTML, CSS, JavaScript без сборки | 49 |
| [**scraper-demo**](scraper-demo/) | Асинхронный парсер учебного сайта books.toscrape.com: 50 категорий, 1000 книг за один запуск без ошибок, лимиты скорости, повторы, кэш, robots.txt, выгрузка в Excel, CSV, JSON и Google Sheets | Python, httpx, asyncio, selectolax, openpyxl | 80 |
| [**telegram-bot-demo**](telegram-bot-demo/) | Бот для сбора заявок: анкета в 4 шага, карточка заявки менеджеру с кнопками статусов, выгрузка в CSV, статистика, рассылка, Docker и systemd | Python, aiogram 3, SQLite, Docker | 139 |
| [**excel-dashboard-demo**](excel-dashboard-demo/) | Из сырых CSV получается живая книга Excel: дашборд с KPI, фильтрами, графиками и анализом простоев, а также счёт с зарплатой и маржой. Все цифры считаются формулами | Python, openpyxl, pycel | 112 |

Всего 380 автотестов, все проходят (проверено на macOS, Python 3.14, Node.js 25).

### Как запустить

Подробные инструкции есть в README каждого проекта. Коротко:

```bash
git clone https://github.com/sinnercode228/portfolio.git
cd portfolio

# Лендинг: сборка не нужна
cd landing-calculator
open index.html          # Windows: start index.html · Linux: xdg-open index.html
npm test                 # нужен Node.js 22+
cd ..

# Парсер: нужен Python 3.10+
cd scraper-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m bookscraper --limit 100 --out output/books   # → output/books.xlsx, .csv, .json
python -m pytest
deactivate && cd ..

# Telegram-бот: нужен Python 3.11+ и токен от @BotFather (для тестов токен не нужен)
cd telegram-bot-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/demo_dialog.py   # сценарий диалога без токена и интернета
python -m pytest
deactivate && cd ..

# Excel-дашборд: нужен Python 3.10+
cd excel-dashboard-demo
make setup all           # или команды из README проекта
```

На Windows вместо `source .venv/bin/activate` используйте `.venv\Scripts\activate`.

### Страница портфолио (`index.html`)

- Один файл без сборки и внешних зависимостей: без шрифтов со сторонних серверов, аналитики и cookies. Светлая и тёмная тема по настройкам системы, адаптивная вёрстка от 320 px.
- Русский язык по умолчанию, переключатель RU / EN в шапке. Выбор запоминается в браузере. На английскую версию можно дать прямую ссылку: `?lang=en`.
- Посмотреть локально: откройте `index.html` двойным кликом или запустите сервер в корне репозитория: `python3 -m http.server 8000` → http://localhost:8000.
- **Публикация на GitHub Pages:** Settings → Pages → Build and deployment → Deploy from a branch → `main` / `(root)`. Желательно добавить в корень пустой файл `.nojekyll`, чтобы GitHub Pages отдавал файлы как есть, без обработки Jekyll.

### Структура

```
portfolio/
├── index.html              страница портфолио (GitHub Pages)
├── README.md
├── .gitignore
├── landing-calculator/     лендинг с калькулятором (HTML/CSS/JS)
├── scraper-demo/           парсер → Excel / CSV / JSON / Google Sheets
├── telegram-bot-demo/      Telegram-бот для заявок
└── excel-dashboard-demo/   Excel-дашборд и счёт из CSV
```

### Контакты

- Telegram: [@sinnercode](https://t.me/sinnercode)
- GitHub: [sinnercode228](https://github.com/sinnercode228)

---

## English

I take on Python and JavaScript work with a clear outcome: web scrapers and data collection, Telegram bots, automation and API integrations, landing pages, Excel and Google Sheets, and bug fixing. Below are four demo projects, each with a detailed README, run instructions and automated tests.

### Projects

| Project | What it is | Stack | Tests |
|---|---|---|---|
| [**landing-calculator**](landing-calculator/) · [live demo](https://sinnercode228.github.io/portfolio/landing-calculator/) | A landing page for Polden, a fictional house builder, with a cost calculator: total, build time and itemised estimate, a shareable link to the calculation, and a lead form that goes to Telegram or email through a serverless function. The interface is in Russian | Plain HTML, CSS and JavaScript, no build step | 49 |
| [**scraper-demo**](scraper-demo/) | An async scraper for the books.toscrape.com practice site: 50 categories and 1,000 books in one run with zero errors, rate limiting, retries, cache and robots.txt checks, export to Excel, CSV, JSON and Google Sheets | Python, httpx, asyncio, selectolax, openpyxl | 80 |
| [**telegram-bot-demo**](telegram-bot-demo/) | A lead-capture bot: a 4-step form, a lead card for managers with status buttons, CSV export, stats, broadcasts, Docker and systemd deployment. The bot speaks Russian; all texts live in one file | Python, aiogram 3, SQLite, Docker | 139 |
| [**excel-dashboard-demo**](excel-dashboard-demo/) | Turns raw CSV exports into live Excel workbooks: a KPI dashboard with filters, charts and downtime analysis, plus an invoice with payroll and margin. Every number is an Excel formula | Python, openpyxl, pycel | 112 |

380 automated tests in total, all passing (checked on macOS with Python 3.14 and Node.js 25).

### How to run

Each project's README has full instructions; the short version is in the Russian section above. On Windows, use `.venv\Scripts\activate` instead of `source .venv/bin/activate`. Requirements: Node.js 22+ for the landing page tests, Python 3.10+ for the scraper and the Excel project, Python 3.11+ for the bot.

### Portfolio page (`index.html`)

- A single file with no build step and no external requests: no third-party fonts, analytics or cookies. Light and dark themes follow the system setting; the layout works from 320 px wide.
- Russian by default with an RU / EN switch in the header. The choice is remembered in the browser, and `?lang=en` links straight to the English version.
- To preview locally, open `index.html` or run `python3 -m http.server 8000` in the repository root and visit http://localhost:8000.
- **GitHub Pages:** Settings → Pages → Build and deployment → Deploy from a branch → `main` / `(root)`. Adding an empty `.nojekyll` file to the root is recommended, so Pages serves the files as they are, without Jekyll.

### Contact

- Telegram: [@sinnercode](https://t.me/sinnercode)
- GitHub: [sinnercode228](https://github.com/sinnercode228)
