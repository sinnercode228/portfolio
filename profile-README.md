Full-stack разработчик: Python и TypeScript.
В проектах ниже много кода на случай, если вебхук или платёж доставлен дважды, два refresh-запроса пришли одновременно, воркер упал посреди задачи или оборвалось соединение.

Связываю amoCRM, Bitrix24, Tilda и МойСклад через вебхуки и API, пишу Telegram-ботов и Mini App. С LLM сделал RAG по документам и воркфлоу для n8n на Claude и локальной Ollama.

<p>
  <a href="https://sinnercode228.github.io/pulse-analytics/"><img src="https://raw.githubusercontent.com/sinnercode228/portfolio/main/assets/projects/pulse-analytics/cover.webp" width="32%" alt="Pulse, дашборд аналитики"></a>
  <a href="https://sinnercode228.github.io/tg-shop-miniapp/"><img src="https://raw.githubusercontent.com/sinnercode228/portfolio/main/assets/projects/tg-shop-miniapp/cover.webp" width="32%" alt="Zernolist, магазин в Telegram"></a>
  <a href="https://sinnercode228.github.io/flowdesk-crm/"><img src="https://raw.githubusercontent.com/sinnercode228/portfolio/main/assets/projects/flowdesk-crm/cover.webp" width="32%" alt="FlowDesk, канбан сделок"></a>
</p>

- **[Pulse](https://github.com/sinnercode228/pulse-analytics)** · [демо](https://sinnercode228.github.io/pulse-analytics/)\
  Аналитика сайтов без cookies с трекером на 843 байта (560 в gzip) и аптайм-мониторингом. Посетителей в каждой строке роллапа считает [HyperLogLog-скетч](https://github.com/sinnercode228/pulse-analytics/blob/main/packages/core/src/hll.ts), который до 512 хэшей хранит их точным множеством, а дальше переходит на 2048 регистров со стандартной ошибкой около 2,3%.\
  TypeScript, Fastify, node:sqlite, WebSocket, React, uPlot

- **[Relay](https://github.com/sinnercode228/integration-hub)** · [демо](https://sinnercode228.github.io/integration-hub/)\
  Принимает вебхуки Tilda, amoCRM и Bitrix24 и разносит их в Telegram, Google Sheets, amoCRM и на почту. Очередь своя, [на sorted sets в Redis](https://github.com/sinnercode228/integration-hub/blob/main/backend/src/relay/queue/redis.py): взятая задача переезжает в отдельный ZSET с дедлайном через 120 секунд, и если воркер упадёт, после дедлайна она вернётся в очередь.\
  Python, FastAPI, Redis, SQLite, React

- **[DocMind](https://github.com/sinnercode228/docmind-rag)** · [демо](https://sinnercode228.github.io/docmind-rag/)\
  RAG-ассистент по PDF, DOCX и веб-страницам. Источники приходят по SSE [раньше первого токена ответа](https://github.com/sinnercode228/docmind-rag/blob/main/backend/src/docmind/rag/service.py#L110-L111), и когда в тексте появляется сноска `[n]`, её карточка уже на экране.\
  Python, FastAPI, pgvector, Claude или OpenAI-совместимый API, React, бот на aiogram

- **[Zernolist](https://github.com/sinnercode228/tg-shop-miniapp)** · [демо](https://sinnercode228.github.io/tg-shop-miniapp/)\
  Магазин кофе и чая внутри Telegram с оплатой в Stars. Сервер [пересчитывает каждый заказ по каталогу](https://github.com/sinnercode228/tg-shop-miniapp/blob/main/bot/tgshop/services/orders.py#L76-L97), поэтому тест шлёт `price: 1` и всё равно получает подытог 1290 ₽.\
  Mini App на React и Tailwind, бот и API на aiogram 3 + FastAPI, SQLAlchemy

- **[FlowDesk](https://github.com/sinnercode228/flowdesk-crm)** · [демо](https://sinnercode228.github.io/flowdesk-crm/)\
  CRM с канбаном сделок. Refresh-токены ротируются, повторно использованный токен отзывает всю сессию, а гонку двух одновременных refresh закрывает [условный `updateMany` в транзакции](https://github.com/sinnercode228/flowdesk-crm/blob/main/server/src/modules/auth/auth.service.ts#L44-L51).\
  Next.js, Fastify, Prisma, PostgreSQL, TanStack Query, dnd-kit

Демо лежат на GitHub Pages статикой, бэкенд в них заменён кодом в браузере; у Relay события и сбои генерирует отдельная симуляция. У DocMind в демо нет LLM: поиск идёт по BM25, ответ собирается из найденных предложений.

[n8n-home-ai-workflows](https://github.com/sinnercode228/n8n-home-ai-workflows) — четыре воркфлоу для n8n: заметки со встреч в Notion через Claude, дайджест семейных календарей, вопросы по домашним документам на локальных Ollama и Qdrant, обработчик ошибок. С живыми аккаунтами Anthropic, Notion и Google их не запускал; мок-прогоны исполняют настоящий `jsCode` из JSON воркфлоу в `vm`.

В [portfolio](https://github.com/sinnercode228/portfolio) ещё четыре демо поменьше: лендинг с калькулятором стоимости дома ([демо](https://sinnercode228.github.io/portfolio/landing-calculator/)), асинхронный парсер books.toscrape.com с выгрузкой в XLSX, CSV и JSON, Telegram-бот для заявок и Excel-дашборд из CSV, где каждая цифра считается формулой.
Все демо собраны на [sinnercode228.github.io/portfolio](https://sinnercode228.github.io/portfolio/), есть [английская версия](https://sinnercode228.github.io/portfolio/?lang=en).

### Стек

Python: FastAPI, aiogram 3, SQLAlchemy 2, Pydantic, httpx, openpyxl\
TypeScript: Fastify, Prisma, zod, React 19, Next.js, Vite, TanStack Query, Zustand, Tailwind\
Данные: PostgreSQL, pgvector, SQLite, Redis\
LLM: Claude API, OpenAI-совместимые API, Ollama, Qdrant, n8n\
Проверки и инфраструктура: pytest, Vitest, mypy (strict), ruff, GitHub Actions, Docker Compose, nginx

Все проекты на этой странице — пет-проекты на выдуманных данных. Тестов в них 1047, и в каждом репозитории их гоняет GitHub Actions.

Telegram: [@sinnercode](https://t.me/sinnercode)
