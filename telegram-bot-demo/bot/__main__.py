import sys

if sys.version_info < (3, 11):  # noqa: UP036 — понятная ошибка вместо ImportError на старом Python
    sys.exit(f"Нужен Python 3.11 или новее, сейчас {sys.version.split()[0]}. См. README.md.")

from bot.main import main

raise SystemExit(main())
