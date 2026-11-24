# syntax=docker/dockerfile:1
# Stage 1: dump the OpenAPI schema from the real app, so the TS types are always regenerated.
FROM python:3.12-slim AS spec
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
WORKDIR /srv/app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY scripts/gen-openapi.py ./scripts/
RUN PYTHONPATH=. AIORG_SESSION_SECRET=build-only .venv/bin/python scripts/gen-openapi.py /openapi.json

FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
COPY --from=spec /openapi.json /openapi.json
RUN npx openapi-typescript /openapi.json -o src/lib/api-types.ts && npm run build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
WORKDIR /srv/app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY roles ./roles
COPY --from=web /web/dist ./web/dist
RUN useradd --system --uid 10001 aiorg && chown -R aiorg /srv/app
USER aiorg
ENV PATH="/srv/app/.venv/bin:$PATH" AIORG_STATIC_DIR=/srv/app/web/dist AIORG_ROLES_DIR=/srv/app/roles
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli ensure-founder && exec uvicorn app.api.main:app --host 0.0.0.0 --port 8000"]
