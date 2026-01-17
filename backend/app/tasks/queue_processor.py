"""
Queue processor Celery task.

Runs every 30 seconds to process pending queue entries for active campaigns.
Respects time windows, concurrency limits, and retry schedules.
"""

from celery import Task
from backend.app.celery_app import celery_app
from datetime import datetime, time
import logging
import asyncio

logger = logging.getLogger(__name__)


class QueueProcessorTask(Task):
    """Base task for queue processing with error handling"""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True
    max_retries = 3


def is_within_time_window(time_windows: list) -> bool:
    """
    Check if current UTC time is within any configured time window.

    Args:
        time_windows: List of TimeWindow dicts with start_time, end_time, days_of_week

    Returns:
        True if within window or no windows configured, False otherwise
    """
    if not time_windows:
        # No time windows = always allowed
        return True

    now_utc = datetime.utcnow()
    current_time = now_utc.time()
    current_day = now_utc.strftime("%A").lower()  # e.g., "monday"

    for window in time_windows:
        # Check if current day is in allowed days
        allowed_days = [d.lower() for d in window.get("days_of_week", [])]
        if current_day not in allowed_days:
            continue

        start_time = window["start_time"]
        end_time = window["end_time"]

        # Handle time parsing (could be time objects or strings)
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time, "%H:%M:%S").time()
        if isinstance(end_time, str):
            end_time = datetime.strptime(end_time, "%H:%M:%S").time()

        # Handle midnight crossing (e.g., 22:00 - 02:00)
        if start_time <= end_time:
            # Normal case: start < end
            if start_time <= current_time <= end_time:
                return True
        else:
            # Midnight crossing: start > end
            if current_time >= start_time or current_time <= end_time:
                return True

    return False


@celery_app.task(base=QueueProcessorTask, bind=True, name="process_campaign_queues")
def process_campaign_queues(self):
    """
    Process pending queue entries for all active campaigns.

    Runs every 30 seconds via Celery Beat.

    Logic:
    1. Find all campaigns with state=ACTIVE
    2. For each campaign:
       - Check time windows (skip if outside allowed times)
       - Count currently in-progress calls
       - Get ready-to-process entries (PENDING + ready RETRYING)
       - Respect max_concurrent_calls limit
       - Initiate calls via voice_call task
    3. Update campaign stats

    Returns:
        Dict with processing summary
    """
    logger.info("Queue processor started")

    try:
        from backend.app.models.campaign import Campaign, CampaignState
        from backend.app.models.queue_entry import QueueEntry, QueueState
        from backend.app.services.queue_service import QueueService
        from backend.app.tasks.voice_call import initiate_patient_call

        # Run async operations in event loop
        loop = asyncio.get_event_loop()

        # Find all active campaigns
        active_campaigns = loop.run_until_complete(
            Campaign.find(Campaign.state == CampaignState.ACTIVE).to_list()
        )

        if not active_campaigns:
            logger.info("No active campaigns found")
            return {"processed": 0, "campaigns": 0}

        logger.info(f"Found {len(active_campaigns)} active campaigns")

        total_processed = 0
        campaigns_processed = 0

        for campaign in active_campaigns:
            try:
                # Check time windows
                time_windows = []
                if campaign.config and campaign.config.time_windows:
                    time_windows = [
                        {
                            "start_time": tw.start_time,
                            "end_time": tw.end_time,
                            "days_of_week": [d.value for d in tw.days_of_week]
                        }
                        for tw in campaign.config.time_windows
                    ]

                if not is_within_time_window(time_windows):
                    logger.info(
                        f"Campaign {campaign.id} outside time window, skipping"
                    )
                    continue

                # Get max concurrent calls limit
                max_concurrent = (
                    campaign.config.max_concurrent_calls
                    if campaign.config else 10
                )

                # Count currently in-progress calls
                in_progress_count = loop.run_until_complete(
                    QueueEntry.find(
                        QueueEntry.campaign_id == str(campaign.id),
                        QueueEntry.state == QueueState.CALLING
                    ).count()
                )

                # Calculate available slots
                available_slots = max_concurrent - in_progress_count

                if available_slots <= 0:
                    logger.info(
                        f"Campaign {campaign.id} at max capacity "
                        f"({in_progress_count}/{max_concurrent}), skipping"
                    )
                    continue

                # Get ready-to-process entries
                ready_entries = loop.run_until_complete(
                    QueueService.get_ready_to_process_entries(
                        campaign_id=str(campaign.id),
                        max_concurrent=available_slots
                    )
                )

                if not ready_entries:
                    logger.info(f"No ready entries for campaign {campaign.id}")
                    continue

                logger.info(
                    f"Processing {len(ready_entries)} entries for campaign {campaign.id} "
                    f"(slots: {available_slots})"
                )

                # Initiate calls for each entry
                for entry in ready_entries:
                    try:
                        # Update entry state to CALLING
                        entry.state = QueueState.CALLING
                        entry.updated_at = datetime.utcnow()
                        loop.run_until_complete(entry.save())

                        # Initiate call via Celery task
                        initiate_patient_call.delay(
                            campaign_id=str(campaign.id),
                            patient_phone=entry.patient_phone,
                            language=entry.language
                        )

                        total_processed += 1
                        logger.info(
                            f"Initiated call for queue entry {entry.id} "
                            f"(patient: {entry.patient_phone})"
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to initiate call for entry {entry.id}: {e}",
                            exc_info=True
                        )
                        # Revert entry state on failure
                        entry.state = QueueState.PENDING
                        loop.run_until_complete(entry.save())

                campaigns_processed += 1

            except Exception as e:
                logger.error(
                    f"Error processing campaign {campaign.id}: {e}",
                    exc_info=True
                )
                continue

        logger.info(
            f"Queue processor completed: {total_processed} calls initiated "
            f"across {campaigns_processed} campaigns"
        )

        return {
            "processed": total_processed,
            "campaigns": campaigns_processed
        }

    except Exception as e:
        logger.error(f"Queue processor failed: {e}", exc_info=True)
        raise
