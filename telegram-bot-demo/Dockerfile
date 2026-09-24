# Образ бота для сбора заявок (демо-проект «Ромашка Digital»)
# Базовый образ можно заменить, если Docker Hub недоступен (см. README, раздел про Docker).
ARG PYTHON_IMAGE=python:3.14-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    DB_PATH=/app/data/leads.db

WORKDIR /app

# Зависимости отдельным слоем — пересборка после правок кода занимает секунды
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bot ./bot

# Бот работает не от root; база лежит в томе /app/data
RUN useradd --create-home --uid 10001 botuser \
    && mkdir -p /app/data \
    && chown botuser:botuser /app/data
USER botuser
VOLUME ["/app/data"]

CMD ["python", "-m", "bot"]
