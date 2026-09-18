FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.154.0
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv ca-certificates curl git jq unzip zip \
    ripgrep poppler-utils tesseract-ocr sqlite3 procps bash \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/bench-requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/bench-requirements.txt
RUN npm install -g @openai/codex@${CODEX_VERSION}
RUN mkdir -p /work && chmod 777 /work
WORKDIR /work
