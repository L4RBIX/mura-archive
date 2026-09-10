#!/bin/sh
# API and worker in one container, deliberately.
#
# The API writes uploaded audio to a local directory and the worker reads it
# back. Split across two Railway services those are two different filesystems
# and the handoff simply fails, because a Railway volume mounts to exactly one
# service. Until audio lives in object storage, sharing a container is the only
# arrangement in which the pipeline actually runs.
#
# They remain separate processes. The API still never claims or executes a job:
# that rule is about which process does the work, not which host it runs on.
set -e

mkdir -p "${AUDIO_STORAGE_DIR:-/app/data/audio}"

# Alembic owns the schema, and only one process may migrate.
alembic upgrade head

# The worker holds jobs under a lease with a heartbeat, so an abrupt stop loses
# nothing: the lease expires and the work is reclaimed.
mura-worker &
WORKER_PID=$!

# Stopping the container must stop both, or Railway waits out the grace period
# on every deploy.
trap 'kill -TERM "$WORKER_PID" 2>/dev/null' TERM INT

exec uvicorn apps.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
