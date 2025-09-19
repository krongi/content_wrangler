# ---------- Build stage ----------
FROM python:3.12-slim AS builder

# System deps for lxml/readability builds + CA certs for HTTPS during pip install
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential libxml2-dev libxslt1-dev python3-dev rustc cargo \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps into a virtualenv to copy later
ENV VENV=/opt/venv PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN python -m venv $VENV
ENV PATH="$VENV/bin:$PATH"

# Copy only files needed to resolve deps first (better caching)
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Runtime stage ----------
FROM python:3.12-slim

# Minimal runtime libs for lxml + CA certs for HTTPS to GitHub
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 ca-certificates \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
ENV VENV=/opt/venv
COPY --from=builder $VENV $VENV
ENV PATH="$VENV/bin:$PATH"

# Create non-root user
RUN useradd -ms /bin/bash appuser
WORKDIR /app

# Copy project files
COPY . /app
RUN mkdir -p /app/data && mkdir -p /app/article_docs && chown -R appuser:appuser /app

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
 && ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime \
 && dpkg-reconfigure -f noninteractive tzdata \
 && rm -rf /var/lib/apt/lists/*
ENV TZ=America/New_York

USER appuser

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
