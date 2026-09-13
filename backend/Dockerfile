FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/src
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml README.md requirements.txt alembic.ini main.py start_api.py ./
COPY src ./src
COPY app ./app
COPY migrations ./migrations

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "start_api.py"]
