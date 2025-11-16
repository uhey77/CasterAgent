FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        libjpeg62-turbo-dev \
        libpng-dev \
        libsm6 \
        libwebp-dev \
        libxext6 \
        zlib1g-dev \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app

COPY src ./src
COPY main.py .
COPY README.md .

COPY pyproject.toml uv.lock /app/
RUN pip install uv && uv sync --frozen

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
