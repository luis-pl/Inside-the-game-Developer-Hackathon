# Imagen Linux para Azure Container Apps. Nunca copia configuraciones ni claves.
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libltdl7 libkrb5-3 libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY prompts/data_agent.md ./prompts/data_agent.md
RUN python -m pip install --no-cache-dir . \
    && useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "inside_game.cloud:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
