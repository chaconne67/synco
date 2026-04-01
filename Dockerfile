FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies + Node.js (for claude CLI) + doc parsing tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl \
    antiword libreoffice-core libreoffice-writer && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Python dependencies
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e ".[dev]"

COPY . .

# Build Tailwind CSS
RUN npx tailwindcss@3 -i static/css/input.css -o static/css/output.css --minify

RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
