"""
Celery Tasks for Clarity Integration

Periodic tasks for syncing with Clarity API.
"""

import asyncio
import logging
from typing import Dict, Any

from backend.app.services.queue.celery_app import celery_app, QUEUE_NORMAL
from backend.app.models.queue_models import QueueState

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="sync_clarity_queues",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minutes
    max_retries=3,
)
def sync_clarity_queues(self) -> Dict[str, Any]:
    """
    Sync all Clarity-type queues with their respective Clarity APIs.

    This task:
    1. Finds all active queues with queue_type="clarity"
    2. For each queue, fetches pending verifications from Clarity
    3. Creates CallEntry records for new verifications

    Run periodically via Celery Beat (default: every 5 minutes).

    Returns:
        Dict with sync statistics
    """
    logger.info("Starting Clarity queue sync...")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(_sync_clarity_queues_async())
        finally:
            loop.close()

        logger.info(f"Clarity sync completed: {result}")
        return result

    except Exception as e:
        logger.error(f"Failed to sync Clarity queues: {e}")
        raise  # Re-raise to trigger retry


async def _sync_clarity_queues_async() -> Dict[str, Any]:
    """Async implementation of Clarity sync."""
    from backend.app.infrastructure.database.queue_repository import (
        get_queue_repository,
        get_call_entry_repository,
    )
    from backend.app.integrations.clarity.sync_service import ClaritySyncService

    queue_repo = get_queue_repository()
    call_entry_repo = get_call_entry_repository()
    sync_service = ClaritySyncService(queue_repo, call_entry_repo)

    results: Dict[str, Any] = {
        "queues_processed": 0,
        "total_created": 0,
        "total_updated": 0,
        "total_skipped": 0,
        "total_errors": 0,
        "queue_results": {},
    }

    # Get all active queues
    queues = await queue_repo.list_queues(state=QueueState.ACTIVE)

    # Filter to Clarity queues
    clarity_queues = [
        q for q in queues if q.metadata.get("queue_type") == "clarity"
    ]

    logger.info(f"Found {len(clarity_queues)} Clarity queues to sync")

    for queue in clarity_queues:
        try:
            logger.info(f"Syncing Clarity queue: {queue.queue_id}")
            stats = await sync_service.sync_queue_from_clarity(queue)

            results["queues_processed"] += 1
            results["total_created"] += stats["created"]
            results["total_updated"] += stats["updated"]
            results["total_skipped"] += stats["skipped"]
            results["total_errors"] += stats["errors"]
            results["queue_results"][queue.queue_id] = stats

            logger.info(f"Synced queue {queue.queue_id}: {stats}")

        except Exception as e:
            logger.error(f"Failed to sync queue {queue.queue_id}: {e}")
            results["total_errors"] += 1
            results["queue_results"][queue.queue_id] = {"error": str(e)}

    return results


@celery_app.task(
    bind=True,
    name="sync_clarity_result",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,  # Max 5 minutes
    max_retries=5,
)
def sync_clarity_result(self, entry_id: str) -> Dict[str, Any]:
    """
    Sync a completed call result back to Clarity.

    Called after a call is marked SUCCESS or DEAD_LETTER.

    Args:
        entry_id: The CallEntry ID to sync

    Returns:
        Sync result
    """
    logger.info(f"Syncing call result to Clarity: {entry_id}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(_sync_result_async(entry_id))
        finally:
            loop.close()

        return {"success": result, "entry_id": entry_id}

    except Exception as e:
        logger.error(f"Failed to sync result for {entry_id}: {e}")
        raise  # Re-raise to trigger retry


async def _sync_result_async(entry_id: str) -> bool:
    """Async implementation of result sync."""
    from backend.app.infrastructure.database.queue_repository import (
        get_queue_repository,
        get_call_entry_repository,
    )
    from backend.app.integrations.clarity.sync_service import ClaritySyncService

    queue_repo = get_queue_repository()
    call_entry_repo = get_call_entry_repository()
    sync_service = ClaritySyncService(queue_repo, call_entry_repo)

    entry = await call_entry_repo.get_entry(entry_id)
    if not entry:
        logger.error(f"Entry {entry_id} not found")
        return False

    return await sync_service.sync_result_to_clarity(entry)


@celery_app.task(
    bind=True,
    name="sync_single_clarity_queue",
)
def sync_single_clarity_queue(self, queue_id: str) -> Dict[str, Any]:
    """
    Manually sync a single Clarity queue.

    Used for on-demand sync via API.

    Args:
        queue_id: The queue ID to sync

    Returns:
        Sync statistics
    """
    logger.info(f"Manual sync triggered for queue: {queue_id}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                _sync_single_queue_async(queue_id)
            )
        finally:
            loop.close()

        return result

    except Exception as e:
        logger.error(f"Failed to sync queue {queue_id}: {e}")
        return {"error": str(e), "queue_id": queue_id}


async def _sync_single_queue_async(queue_id: str) -> Dict[str, Any]:
    """Async implementation of single queue sync."""
    from backend.app.infrastructure.database.queue_repository import (
        get_queue_repository,
        get_call_entry_repository,
    )
    from backend.app.integrations.clarity.sync_service import ClaritySyncService

    queue_repo = get_queue_repository()
    call_entry_repo = get_call_entry_repository()
    sync_service = ClaritySyncService(queue_repo, call_entry_repo)

    queue = await queue_repo.get_queue(queue_id)
    if not queue:
        return {"error": f"Queue {queue_id} not found", "queue_id": queue_id}

    if queue.metadata.get("queue_type") != "clarity":
        return {
            "error": f"Queue {queue_id} is not a Clarity queue",
            "queue_id": queue_id,
        }

    stats = await sync_service.sync_queue_from_clarity(queue)
    return {
        "queue_id": queue_id,
        "success": True,
        **stats,
    }
