#!/bin/bash
set -e

# Docker entrypoint script
# Supports multiple run modes:
#   - api: Run only the FastAPI application (default)
#   - worker: Run only the Celery worker
#   - beat: Run only the Celery beat scheduler
#   - all: Run API + worker + beat using supervisord (for single-container deployments)

MODE="${RUN_MODE:-api}"

echo "=========================================="
echo "Acme Supervisor Backend"
echo "Run mode: $MODE"
echo "Queue enabled: ${QUEUE_ENABLED:-false}"
echo "=========================================="

case "$MODE" in
    validate)
        echo "Running service validation..."
        python -m backend.app.core.health.startup
        exit $?
        ;;
    api)
        echo "Starting FastAPI application..."
        exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 3000
        ;;
    worker)
        echo "Starting Celery worker..."
        exec celery -A backend.app.services.queue.celery_app worker \
            --loglevel=info \
            --concurrency=${CELERY_CONCURRENCY:-4}
        ;;
    beat)
        echo "Starting Celery beat scheduler..."
        exec celery -A backend.app.services.queue.celery_app beat --loglevel=info
        ;;
    worker-beat)
        echo "Starting Celery worker with embedded beat..."
        exec celery -A backend.app.services.queue.celery_app worker \
            --beat \
            --loglevel=info \
            --concurrency=${CELERY_CONCURRENCY:-2}
        ;;
    all)
        echo "Starting all services with supervisord..."
        # Export QUEUE_ENABLED for supervisord config
        export QUEUE_ENABLED="${QUEUE_ENABLED:-false}"
        exec supervisord -c /app/supervisord.conf
        ;;
    init-db)
        echo "Initializing queue database..."
        exec python -m backend.init_queue_db
        ;;
    *)
        echo "Unknown mode: $MODE"
        echo "Valid modes: api, worker, beat, worker-beat, all, init-db, validate"
        exit 1
        ;;
esac
