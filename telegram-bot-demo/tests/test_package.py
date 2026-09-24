"""Пакет импортируется без токена и без сети; запуск без .env даёт понятную ошибку."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_python(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BOT_", "ADMIN_"))}
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)


def test_package_imports_cleanly(tmp_path: Path) -> None:
    result = run_python(
        "-W",
        "error",
        "-c",
        "import bot, bot.main, bot.app, bot.handlers; print(bot.__version__)",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1.0.0"


def test_run_without_token_exits_with_hint(tmp_path: Path) -> None:
    # tmp_path: рядом нет .env, поэтому токен взять неоткуда
    result = run_python("-m", "bot", cwd=tmp_path)
    assert result.returncode == 2
    assert "BOT_TOKEN не задан" in result.stderr
    assert "Traceback" not in result.stderr


def test_every_router_is_fresh() -> None:
    """Фабрики роутеров позволяют собрать несколько диспетчеров (важно для тестов и воркеров)."""
    from bot.handlers import create_routers

    first, second = create_routers(), create_routers()
    assert all(a is not b for a, b in zip(first, second, strict=True))


def test_demo_dialog_script_runs() -> None:
    result = run_python(str(ROOT / "scripts" / "demo_dialog.py"), cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert "Заявка №1 принята" in result.stdout
    assert "🔔 Заявка №1" in result.stdout  # уведомление администратору
    assert "leads_" in result.stdout and ".csv" in result.stdout


def test_unwritable_db_path_exits_with_hint(tmp_path: Path) -> None:
    (tmp_path / "not_a_dir").write_text("")
    (tmp_path / ".env").write_text(
        "BOT_TOKEN=123456789:AAFakeTokenForTestsOnly_abcdefghijk\nDB_PATH=not_a_dir/leads.db\n", encoding="utf-8"
    )
    result = run_python("-m", "bot", cwd=tmp_path)
    assert result.returncode == 2
    assert "DB_PATH" in result.stderr
    assert "Traceback" not in result.stderr


def test_unwritable_log_file_exits_with_hint(tmp_path: Path) -> None:
    (tmp_path / "not_a_dir").write_text("")
    (tmp_path / ".env").write_text(
        "BOT_TOKEN=123456789:AAFakeTokenForTestsOnly_abcdefghijk\nLOG_FILE=not_a_dir/bot.log\n", encoding="utf-8"
    )
    result = run_python("-m", "bot", cwd=tmp_path)
    assert result.returncode == 2
    assert "LOG_FILE" in result.stderr
    assert "Traceback" not in result.stderr
