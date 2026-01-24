#!/usr/bin/env python3
"""
Queue Processor Launcher

Starts both the Celery worker and Celery Beat scheduler for the managed queue system.

Usage:
    python start_queue_processor.py              # Start worker only
    python start_queue_processor.py --with-beat  # Start worker + beat scheduler

Requirements:
    - Redis must be running
    - QUEUE_ENABLED=true in .env
    - QUEUE_REDIS_URL set in .env

For production, run worker and beat in separate processes:
    Terminal 1: celery -A backend.app.services.queue.celery_app worker --loglevel=info
    Terminal 2: celery -A backend.app.services.queue.celery_app beat --loglevel=info
"""
import os
import sys
import subprocess
import argparse
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
    """Start Celery worker (optionally with beat)"""
    parser = argparse.ArgumentParser(description="Start Celery queue processor")
    parser.add_argument(
        "--with-beat", "-b",
        action="store_true",
        help="Also run beat scheduler in the same process (dev only)"
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=4,
        help="Number of worker processes (default: 4)"
    )
    parser.add_argument(
        "--queues", "-Q",
        type=str,
        default="calls.high,calls.normal,calls.low",
        help="Comma-separated list of queues to process"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Starting Queue Processor")
    print("=" * 60)

    # Check if queue is enabled
    queue_enabled = os.getenv("QUEUE_ENABLED", "false").lower() == "true"
    if not queue_enabled:
        print("WARNING: QUEUE_ENABLED is not set to 'true' in .env")
        print("The queue system may not function correctly.")
        print()

    redis_url = os.getenv("QUEUE_REDIS_URL", "redis://localhost:6379/0")
    print(f"Redis URL: {redis_url}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Queues: {args.queues}")
    print(f"With Beat: {args.with_beat}")
    print()

    print("Starting worker...")
    print("-" * 60)

    # Build celery command
    cmd = [
        "celery",
        "-A", "backend.app.services.queue.celery_app",
        "worker",
        f"--concurrency={args.concurrency}",
        f"--queues={args.queues}",
        "--loglevel=info",
    ]

    # Add beat if requested (for development/testing)
    if args.with_beat:
        cmd.append("--beat")
        print("NOTE: Running beat in worker process (development mode)")
        print("      For production, run beat in a separate process.")
        print()

    # Run celery worker
    try:
        subprocess.run(cmd, cwd=str(project_root))
    except KeyboardInterrupt:
        print("\nQueue processor stopped.")


if __name__ == "__main__":
    main()
