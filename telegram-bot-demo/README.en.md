# Telegram lead-capture bot on aiogram 3

[Русский](README.md) · **English**

The bot collects leads through a four-step form, saves them to SQLite and sends a card to the admin chats. Admins get `/leads`, `/export` to CSV, `/stats` and `/broadcast`. The code is Python 3.11+ and aiogram 3 (long polling, FSM, CallbackData), and it talks to the database through aiosqlite. The Romashka Digital studio exists only in [`texts.py`](bot/texts.py), along with its services and prices.

Here's part of the output of [`scripts/demo_dialog.py`](scripts/demo_dialog.py). The script runs the real handlers on the same fake Telegram the tests use, with no token and no internet. The bot's texts are in Russian. Some messages and lines are left out, and emoji are removed or replaced with words:

```text
Анна: 8 900 12
бот → Анна:
   Не получилось распознать номер
   Введите его в формате +7 900 123-45-67 или нажмите «Отправить мой номер».
Анна: 8 (900) 123-45-67
бот → Анна:
   Номер сохранён: +7 (900) 123-45-67
...
Анна нажимает [Отправить]
бот → Анна:
   Спасибо, Анна! Заявка №1 принята.
бот → Админ:
   Заявка №1 · 26.09.2026 16:38
   Анна
   +7 (900) 123-45-67
   Лендинг
   Статус: Новая
   [В работе]  [Закрыта]  [Отклонена]
```

Phone numbers are normalized to E.164 by `normalize_phone`, a pure function in [`validators.py`](bot/validators.py). Without a "+", a leading 8 in an 11-digit number becomes 7, and a 10-digit number starting with 3, 4, 7, 8 or 9 gets a 7 in front, so `(495) 123-45-67` becomes `+74951234567`. A shared contact goes through the same function, and the bot rejects a contact with someone else's `user_id`.

If you fix one field on the confirmation screen, the bot goes straight back to confirmation. The field's handler sees `editing=True` in the form data and skips the remaining steps, whose order is set by the `NEXT_STEP` dict in [`handlers/form.py`](bot/handlers/form.py).

## Double Submit and button presses after downtime

Two quick presses of Submit ("Отправить") produce one lead. The dispatcher is built with `SimpleEventIsolation` ([`app.py`](bot/app.py)), so updates from one user are handled one at a time. `confirm_submit` clears the form state before writing to the database, so the second press doesn't pass the `LeadForm.confirm` filter and gets "Эта кнопка устарела" ("this button is outdated"). If the write fails, the state is restored and the same form can be submitted again.

The card goes to admins only after the lead is saved, to each chat separately ([`notify.py`](bot/services/notify.py)). If the bot was removed from an admin group, the client still gets the confirmation and the card still reaches the other admin chats. If the reply to the client doesn't get through, the card goes to admins as usual. Both cases are tested in [`test_user_flow.py`](tests/test_user_flow.py).

While the bot is down, button presses pile up on Telegram's side and arrive stale after startup, and `answerCallbackQuery` answers them with "query is too old". `ack()` in [`handlers/utils.py`](bot/handlers/utils.py) writes that error to the debug log and doesn't stop the handler, so the menu buttons and lead status buttons still work. `test_expired_callback_query_still_works` injects this error when Submit is pressed in a form that's still in memory and checks that the lead was saved.

## Admin commands

A broadcast copies the message (`copy_message`) to active users one at a time with a 0.05 s pause, at most 20 messages per second ([`broadcast.py`](bot/services/broadcast.py)). On `TelegramRetryAfter` the bot waits as long as Telegram says and retries once. Users who blocked the bot or deleted their account (`TelegramForbiddenError`, `TelegramNotFound`) get the `is_blocked` flag and drop out of broadcasts until they come back via `/start`, a new lead or unblocking the bot. The broadcast itself runs as a background task, and [`tasks.py`](bot/services/tasks.py) keeps references to tasks in a `set` so the garbage collector can't kill it halfway.

`/export` returns a CSV for Excel with a Russian locale: UTF-8 with BOM, `;` as the delimiter, CRLF line endings. `sanitize_cell` in [`export.py`](bot/export.py) puts an apostrophe in front of any value that starts with `=`, `+`, `-`, `@`, a tab or `\r`, so `=HYPERLINK(...)` in a comment stays text. For the same reason, usernames are written without the "@".

## From terminal to Telegram

```bash
git clone https://github.com/sinnercode228/portfolio.git
cd portfolio/telegram-bot-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/demo_dialog.py   # the dialog from the example above
cp .env.example .env            # add your BOT_TOKEN from @BotFather
python -m bot
```

The variables, with comments, are in [`.env.example`](.env.example); only `BOT_TOKEN` is required. `ADMIN_IDS` sets who can use the admin commands and status buttons (send `/id` and the bot shows your ID). Cards go to `ADMIN_CHAT_IDS`; if it's empty, they go to the same `ADMIN_IDS` as private messages.

## Deploying to a VPS

With `.env` filled in, `docker compose up -d --build` builds the image from the [`Dockerfile`](Dockerfile) and runs the bot as `botuser` with uid 10001; the database lives in the `bot-data` volume. If Docker Hub isn't reachable, the `PYTHON_IMAGE` variable switches the base image (there's an example with a mirror in [`docker-compose.yml`](docker-compose.yml)).

Without Docker, the bot runs from the unit [`deploy/romashka-bot.service`](deploy/romashka-bot.service). It expects the contents of this folder in `/opt/romashka-bot`, along with `.venv` and `.env`, runs as the system user `botuser`, and is enabled with `systemctl enable --now romashka-bot` once it's copied to `/etc/systemd/system/`. `RestartPreventExitStatus=2` keeps systemd from restarting the bot in a loop when the config fails its startup check and `python -m bot` exits with code 2. The sandbox comes from `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome` and `PrivateTmp`, and the only persistent path the service can write to is `/opt/romashka-bot/data` (`ReadWritePaths`).

A restart loses any half-filled form (the FSM lives in `MemoryStorage`), and broadcast progress isn't saved anywhere, so if you rerun an interrupted `/broadcast`, it goes out to all active users again.

## Tests on FakeSession

```bash
pip install -r requirements-dev.txt
pytest && ruff check . && ruff format --check .
```

There are 139 tests. The dialog scenarios in [`test_user_flow.py`](tests/test_user_flow.py) and [`test_admin.py`](tests/test_admin.py) run through the real aiogram dispatcher on top of [`FakeSession`](tests/fakes.py). It records every Bot API call and answers locally, and the test checks which messages and buttons went out and what ended up in the database. The other files test the validators, config, database, formatting, CSV export, background tasks and starting the bot with `python -m bot`, each on its own.

---

Built by Грешный Котик (sinnercode). I take freelance work like this: Telegram [@sinnercode](https://t.me/sinnercode). License: [MIT](LICENSE).
