# One image for the API and the Celery worker.
FROM python:3.14-slim

# LibreOffice converts legacy .doc uploads to .docx (services/documents/office.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer-nogui \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
# The lock pins CUDA PyTorch (~5 GB of nvidia-* wheels) for development
# machines. Servers run embeddings on the CPU: skip those and install the
# CPU build of the same torch version, last (a later sync would remove it).
RUN uv sync --frozen --no-dev --no-install-project --inexact \
        --no-install-package torch --no-install-package triton \
        $(grep -oE '^name = "nvidia-[a-z0-9-]+"' uv.lock | cut -d'"' -f2 | sed 's/^/--no-install-package /')

COPY alembic.ini ./
COPY src ./src
RUN uv sync --frozen --no-dev --inexact \
        --no-install-package torch --no-install-package triton \
        $(grep -oE '^name = "nvidia-[a-z0-9-]+"' uv.lock | cut -d'"' -f2 | sed 's/^/--no-install-package /') \
    && uv pip install --python /app/.venv/bin/python \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==$(grep -A1 '^name = "torch"' uv.lock | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"

# Models come from the volume filled by the `models` job; at runtime nothing
# may reach Hugging Face (the internal network has no internet anyway).
ENV PATH=/app/.venv/bin:$PATH \
    HF_HOME=/models/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1

# /data/documents: owned here, so a new documents_data volume mounted on it
# starts owned by archfold too (STORAGE=disk).
RUN useradd --create-home --uid 10001 archfold \
    && mkdir -p /models/hf /data/documents \
    && chown -R archfold /models /app /data \
    && chmod 700 /data/documents
USER archfold
WORKDIR /app/src

EXPOSE 8000
# Reachable only through the proxy on the internal network, so its forwarded
# client IP (audit log, login throttling) can be trusted.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
