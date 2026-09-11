# Railway default: build context is the Git repo root (AIToolsPA).
# Do not set the service Root Directory to frontend/.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

COPY backend/pyproject.toml backend/README.md backend/requirements.txt backend/alembic.ini backend/main.py backend/start_api.py ./
COPY backend/src ./src
COPY backend/app ./app
COPY backend/migrations ./migrations

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "start_api.py"]
