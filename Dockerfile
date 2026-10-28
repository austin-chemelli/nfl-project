# nfl-project: one image, every job is `nfl <command>` (docs/hosting.md, ADR 0008).
# Cloud Run Jobs run this with different args; the data root is a mounted bucket.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:3.14-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 nfl
WORKDIR /app
COPY --from=build --chown=nfl:nfl /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    NFL_DATA_ROOT=/mnt/data \
    PYTHONUNBUFFERED=1
USER nfl
ENTRYPOINT ["nfl"]
CMD ["--help"]
