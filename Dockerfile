FROM node:22-slim AS assets

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tailwind.config.js ./
COPY static ./static
COPY templates ./templates
COPY accounts/templates ./accounts/templates
COPY candidates/templates ./candidates/templates
COPY candidates/static ./candidates/static

RUN npx tailwindcss -i static/css/input.css -o static/css/output.css --minify


FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependencies for PostgreSQL and resume document parsing.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    antiword \
    curl \
    libreoffice-core \
    libreoffice-writer && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system .

COPY . .
COPY --from=assets /app/static/css/output.css /app/static/css/output.css

RUN SECRET_KEY=build-only-secret \
    DATABASE_URL=sqlite:////tmp/build.db \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "main.wsgi:application", "--bind", "0.0.0.0:8000"]
