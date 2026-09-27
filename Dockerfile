FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# cpu - легкий образ, cu126 - образ с поддержкой NVIDIA GPU
ARG TORCH_BACKEND=cpu

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/home/sss/storage/huggingface \
    DATABASE_URL=sqlite+aiosqlite:////home/sss/storage/data.db \
    LOG_FILE=/home/sss/storage/app.log

WORKDIR /home/sss

# Сначала только зависимости, чтобы слой кешировался между сборками
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --extra ${TORCH_BACKEND}

COPY app ./app
COPY data/data.json ./data/data.json
RUN uv sync --frozen --no-dev --extra ${TORCH_BACKEND}

VOLUME /home/sss/storage
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5m \
    CMD ["/home/sss/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]

ENTRYPOINT [ "/home/sss/.venv/bin/python", "-m", "app.main" ]
CMD [ "--host", "0.0.0.0", "--port", "8000" ]
