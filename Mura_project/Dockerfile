# Core API and the processing worker ship as one image: they share the same
# source tree and differ only in entrypoint, and building twice would let the
# two drift apart between deploys.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency layer first so application edits do not invalidate the install.
COPY pyproject.toml README.md ./
COPY src ./src
COPY apps ./apps
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir .

# Audio lives on a mounted volume in production; the directory must exist even
# when the volume is empty on first boot.
RUN mkdir -p /app/.mura/audio

EXPOSE 8000

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

CMD ["/app/docker-entrypoint.sh"]
