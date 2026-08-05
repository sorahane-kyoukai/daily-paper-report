FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build-only
RUN rm -rf /build/frontend/dist/api

FROM ghcr.io/astral-sh/uv:0.8.15 AS uv

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev
COPY src ./src
COPY main.py ./main.py
COPY config ./config
COPY --from=frontend /build/frontend/dist /opt/frontend-dist
RUN chown -R app:app /app /opt/frontend-dist
USER app
ENTRYPOINT ["uv", "run", "python", "main.py"]
