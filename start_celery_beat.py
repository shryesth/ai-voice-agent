#!/usr/bin/env python3
"""
Celery Beat Scheduler Launcher

Starts the Celery Beat scheduler for periodic tasks like processing managed queues.

Usage:
    python start_celery_beat.py

Requirements:
    - Redis must be running
    - QUEUE_ENABLED=true in .env
    - QUEUE_REDIS_URL set in .env

The beat scheduler runs periodic tasks defined in celery_app.py:
    - process_managed_queues: Runs every QUEUE_PROCESSOR_INTERVAL_SECONDS (default 30s)
"""
import os
import sys
import subprocess
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)


def main():
    """Start Celery Beat scheduler"""
    print("=" * 60)
    print("Starting Celery Beat Scheduler")
    print("=" * 60)

    # Check if queue is enabled
    queue_enabled = os.getenv("QUEUE_ENABLED", "false").lower() == "true"
    if not queue_enabled:
        print("WARNING: QUEUE_ENABLED is not set to 'true' in .env")
        print("The queue system may not function correctly.")
        print()

    redis_url = os.getenv("QUEUE_REDIS_URL", "redis://localhost:6379/0")
    print(f"Redis URL: {redis_url}")
    print()

    interval = os.getenv("QUEUE_PROCESSOR_INTERVAL_SECONDS", "30")
    print(f"Queue processor interval: {interval} seconds")
    print()

    print("Starting beat scheduler...")
    print("-" * 60)

    # Build celery command with RedBeat scheduler (stores schedule in Redis)
    cmd = [
        "celery",
        "-A", "backend.app.services.queue.celery_app",
        "beat",
        "--loglevel=info",
        "--scheduler=redbeat.RedBeatScheduler",
    ]

    # Run celery beat
    try:
        subprocess.run(cmd, cwd=str(project_root))
    except KeyboardInterrupt:
        print("\nBeat scheduler stopped.")


if __name__ == "__main__":
    main()
