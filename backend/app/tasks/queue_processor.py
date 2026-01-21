"""
Queue processor Celery task.

Runs every 30 seconds to process:
- NEW: Active CallQueues (Supervisor model)
- LEGACY: Active Campaigns (for backward compatibility)

Respects time windows, concurrency limits, and retry schedules.
"""

from celery import Task
from backend.app.celery_app import celery_app, get_worker_event_loop
from datetime import datetime, time
import logging

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

    Supports both new TimeWindow format (days_of_week as integers 0-6)
    and legacy format (days_of_week as day names).

    Args:
        time_windows: List of TimeWindow dicts/objects with start_time, end_time, days_of_week

    Returns:
        True if within window or no windows configured, False otherwise
    """
    if not time_windows:
        # No time windows = always allowed
        return True

    now_utc = datetime.utcnow()
    current_time = now_utc.time()
    current_day_int = now_utc.weekday()  # 0=Monday, 6=Sunday
    current_day_name = now_utc.strftime("%A").lower()  # e.g., "monday"

    for window in time_windows:
        # Handle both dict and object-like access
        if hasattr(window, 'days_of_week'):
            days = window.days_of_week
            start = window.start_time_utc if hasattr(window, 'start_time_utc') else window.start_time
            end = window.end_time_utc if hasattr(window, 'end_time_utc') else window.end_time
        else:
            days = window.get("days_of_week", [])
            start = window.get("start_time_utc", window.get("start_time"))
            end = window.get("end_time_utc", window.get("end_time"))

        # Check if current day is in allowed days
        # Support both integer (0-6) and string ("monday") formats
        day_match = False
        for d in days:
            if isinstance(d, int):
                if d == current_day_int:
                    day_match = True
                    break
            else:
                if str(d).lower() == current_day_name:
                    day_match = True
                    break

        if not day_match:
            continue

        # Handle time parsing
        start_time = start
        end_time = end

        if isinstance(start_time, str):
            # Support HH:MM and HH:MM:SS formats
            try:
                start_time = datetime.strptime(start_time, "%H:%M").time()
            except ValueError:
                start_time = datetime.strptime(start_time, "%H:%M:%S").time()
        if isinstance(end_time, str):
            try:
                end_time = datetime.strptime(end_time, "%H:%M").time()
            except ValueError:
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
    Process pending queue entries for all active queues and campaigns.

    Runs every 30 seconds via Celery Beat.

    Logic:
    1. Process NEW CallQueues (Supervisor model):
       - Find all CallQueues with state=ACTIVE
       - For each queue, check time windows and process Recipients
    2. Process LEGACY Campaigns (backward compatibility):
       - Find all Campaigns with state=ACTIVE
       - Process QueueEntries

    Returns:
        Dict with processing summary
    """
    logger.info("Queue processor started")

    try:
        # Run async operations in event loop
        loop = get_worker_event_loop()

        # Track totals
        total_processed = 0
        queues_processed = 0

        # =====================================================================
        # NEW: Process CallQueues (Supervisor model)
        # =====================================================================
        try:
            from backend.app.models.call_queue import CallQueue
            from backend.app.models.recipient import Recipient
            from backend.app.models.call_record import CallRecord, CallTracking, ConversationState
            from backend.app.models.enums import QueueState, RecipientStatus
            from backend.app.services.recipient_service import recipient_service
            from backend.app.tasks.voice_call import initiate_patient_call
            from backend.app.core.config import get_settings

            settings = get_settings()

            # Find all active CallQueues
            active_queues = loop.run_until_complete(
                CallQueue.find(
                    CallQueue.state == QueueState.ACTIVE,
                    CallQueue.deleted_at == None,
                ).to_list()
            )

            logger.info(f"Found {len(active_queues)} active CallQueues")

            for queue in active_queues:
                try:
                    # Check time windows
                    if not is_within_time_window(queue.time_windows):
                        logger.debug(f"Queue {queue.id} outside time window, skipping")
                        continue

                    # Count currently in-progress calls
                    in_progress_count = loop.run_until_complete(
                        Recipient.find(
                            Recipient.queue_id.id == queue.id,
                            Recipient.status == RecipientStatus.CALLING,
                        ).count()
                    )

                    # Calculate available slots
                    available_slots = queue.max_concurrent_calls - in_progress_count

                    if available_slots <= 0:
                        logger.debug(
                            f"Queue {queue.id} at max capacity "
                            f"({in_progress_count}/{queue.max_concurrent_calls}), skipping"
                        )
                        continue

                    # Get ready-to-process recipients
                    ready_recipients = loop.run_until_complete(
                        recipient_service.get_ready_recipients(
                            queue_id=str(queue.id),
                            max_count=available_slots,
                        )
                    )

                    if not ready_recipients:
                        logger.debug(f"No ready recipients for queue {queue.id}")
                        continue

                    logger.info(
                        f"Processing {len(ready_recipients)} recipients for queue {queue.id} "
                        f"(slots: {available_slots})"
                    )

                    # Initiate calls for each recipient
                    for recipient in ready_recipients:
                        try:
                            # Convert event_info to dict if present
                            event_info_dict = None
                            if recipient.event_info:
                                event_info_dict = recipient.event_info.model_dump() if hasattr(recipient.event_info, 'model_dump') else recipient.event_info

                            # Create CallRecord
                            call_record = CallRecord(
                                geography_id=str(queue.geography_id.id),
                                queue_id=str(queue.id),
                                recipient_id=str(recipient.id),
                                call_type=queue.call_type,
                                contact_phone=recipient.contact_phone,
                                contact_name=recipient.contact_name,
                                contact_type=recipient.contact_type,
                                language=recipient.language,
                                patient_name=recipient.patient_name,
                                guardian_relation=recipient.patient_relation,
                                event_info=event_info_dict,
                                conversation_state=ConversationState(),
                                call_tracking=CallTracking(status="initiated"),
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow(),
                            )
                            loop.run_until_complete(call_record.insert())

                            # Mark recipient as calling
                            loop.run_until_complete(
                                recipient_service.mark_calling(
                                    str(recipient.id),
                                    str(call_record.id),
                                )
                            )

                            # Build callback URL
                            status_callback_url = f"{settings.public_url}/api/v1/webhooks/twilio/status"

                            # Initiate call via Celery task
                            initiate_patient_call.delay(
                                campaign_id=str(queue.id),  # Use queue_id
                                patient_phone=recipient.contact_phone,
                                language=recipient.language,
                                status_callback_url=status_callback_url,
                                call_record_id=str(call_record.id),
                            )

                            total_processed += 1
                            logger.info(
                                f"Initiated call for recipient {recipient.id} "
                                f"(phone: ...{recipient.contact_phone[-4:]})"
                            )

                        except Exception as e:
                            logger.error(
                                f"Failed to initiate call for recipient {recipient.id}: {e}",
                                exc_info=True
                            )
                            # Revert recipient status on failure
                            recipient.status = RecipientStatus.PENDING
                            loop.run_until_complete(recipient.save())

                    queues_processed += 1

                except Exception as e:
                    logger.error(
                        f"Error processing queue {queue.id}: {e}",
                        exc_info=True
                    )
                    continue

        except ImportError:
            logger.warning("CallQueue model not available, skipping new queue processing")

        # =====================================================================
        # LEGACY: Process Campaigns (backward compatibility)
        # =====================================================================
        campaigns_processed = 0

        try:
            from backend.app.models.campaign import Campaign, CampaignState
            from backend.app.models.queue_entry import QueueEntry, QueueState as LegacyQueueState
            from backend.app.services.queue_service import QueueService
            from backend.app.tasks.voice_call import initiate_patient_call

            # Find all active campaigns
            active_campaigns = loop.run_until_complete(
                Campaign.find(Campaign.state == CampaignState.ACTIVE).to_list()
            )

            if active_campaigns:
                logger.info(f"Found {len(active_campaigns)} active Campaigns (legacy)")

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
                        logger.debug(f"Campaign {campaign.id} outside time window, skipping")
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
                            QueueEntry.state == LegacyQueueState.CALLING
                        ).count()
                    )

                    # Calculate available slots
                    available_slots = max_concurrent - in_progress_count

                    if available_slots <= 0:
                        logger.debug(
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
                        logger.debug(f"No ready entries for campaign {campaign.id}")
                        continue

                    logger.info(
                        f"Processing {len(ready_entries)} entries for campaign {campaign.id} "
                        f"(slots: {available_slots})"
                    )

                    # Initiate calls for each entry
                    for entry in ready_entries:
                        try:
                            # Update entry state to CALLING
                            entry.state = LegacyQueueState.CALLING
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
                                f"(patient: ...{entry.patient_phone[-4:]})"
                            )

                        except Exception as e:
                            logger.error(
                                f"Failed to initiate call for entry {entry.id}: {e}",
                                exc_info=True
                            )
                            # Revert entry state on failure
                            entry.state = LegacyQueueState.PENDING
                            loop.run_until_complete(entry.save())

                    campaigns_processed += 1

                except Exception as e:
                    logger.error(
                        f"Error processing campaign {campaign.id}: {e}",
                        exc_info=True
                    )
                    continue

        except ImportError:
            logger.debug("Campaign model not available, skipping legacy processing")

        logger.info(
            f"Queue processor completed: {total_processed} calls initiated "
            f"across {queues_processed} queues and {campaigns_processed} campaigns"
        )

        return {
            "processed": total_processed,
            "queues": queues_processed,
            "campaigns": campaigns_processed,
        }

    except Exception as e:
        logger.error(f"Queue processor failed: {e}", exc_info=True)
        raise
