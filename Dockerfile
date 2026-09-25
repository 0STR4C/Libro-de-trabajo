FROM node:22-alpine AS frontend-build

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tailwind.config.js postcss.config.js vite.config.js ./
COPY frontend ./frontend
COPY app/static ./app/static
RUN npm run build:frontend

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY CHANGELOG.md .
COPY app ./app
COPY --from=frontend-build /build/app/static/frontend ./app/static/frontend
COPY data/wfm ./data/wfm
COPY tools ./tools

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/cache/librodetrabajo/osm-tiles \
    && chown -R appuser:appuser /app /var/cache/librodetrabajo
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.postgres_server:app", "--host", "0.0.0.0", "--port", "8000"]
