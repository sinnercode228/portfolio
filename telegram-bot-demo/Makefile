PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin

.PHONY: help install test lint format check run docker-build docker-up docker-logs docker-down clean

help:  ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: $(BIN)/python  ## Создать .venv и установить зависимости (включая dev)
	$(BIN)/pip install -r requirements-dev.txt

test:  ## Запустить тесты
	$(BIN)/python -m pytest

lint:  ## Проверить код линтером
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format:  ## Отформатировать код
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

check: lint test  ## Линтер + тесты

run:  ## Запустить бота локально (нужен .env)
	$(BIN)/python -m bot

docker-build:  ## Собрать Docker-образ
	docker compose build

docker-up:  ## Запустить в Docker (в фоне)
	docker compose up -d --build

docker-logs:  ## Логи контейнера
	docker compose logs -f bot

docker-down:  ## Остановить контейнер
	docker compose down

clean:  ## Удалить кэши
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
