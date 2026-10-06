#!/bin/sh
# Container start: apply migrations (retrying while MySQL finishes starting), optionally seed, then serve.
set -e

attempt=1
until alembic upgrade head; do
    if [ "$attempt" -ge 10 ]; then
        echo "Database migrations failed after $attempt attempts" >&2
        exit 1
    fi
    echo "Database not ready yet, retrying in 3s ($attempt/10)..."
    attempt=$((attempt + 1))
    sleep 3
done

if [ "${SEED_DATA:-false}" = "true" ]; then
    python -m app.seed.dummy_data
fi

# Worker count comes from WEB_CONCURRENCY (uvicorn reads it); default 2.
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-2}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
