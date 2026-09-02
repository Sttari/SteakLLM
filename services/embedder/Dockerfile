# syntax=docker/dockerfile:1
# Build context is services/ (so contracts/ and common/ are visible):
#   docker build -f services/embedder/Dockerfile -t steakllm/embedder services/
# Stage 1 installs the locked dependencies with uv; stage 2 is a slim runtime that runs as an unprivileged user.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY contracts/ contracts/
COPY common/ common/
COPY embedder/pyproject.toml embedder/uv.lock embedder/.python-version embedder/README.md embedder/
COPY embedder/src embedder/src
# --no-editable: path dependencies are installed as real packages into the venv, not links to /app
RUN cd embedder && uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm
RUN useradd --uid 10001 --create-home app
WORKDIR /app/embedder
COPY --from=build --chown=app:app /app/embedder/.venv /app/embedder/.venv
ENV PATH="/app/embedder/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HOME=/home/app
USER app
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200 else 1)"
CMD ["steakllm-embedder"]
