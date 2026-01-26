"""
Celery tasks for patient feedback collection.

This module imports all task functions to ensure they are registered
with the Celery worker when autodiscover_tasks() runs.
"""

from backend.app.tasks.queue_processor import process_campaign_queues
from backend.app.tasks.voice_call import initiate_patient_call, update_call_from_webhook
from backend.app.tasks.recording_download import download_twilio_recording
from backend.app.tasks.split_recording import split_recording_task
from backend.app.tasks.transcript_translation import translate_transcript
from backend.app.tasks.clarity_sync import (
    sync_clarity_subjects,
    sync_results_to_clarity,
    sync_all_queues_from_clarity,
)
from backend.app.tasks.recipient_sync import sync_recipient_from_call

__all__ = [
    "process_campaign_queues",
    "initiate_patient_call",
    "update_call_from_webhook",
    "download_twilio_recording",
    "split_recording_task",
    "translate_transcript",
    "sync_clarity_subjects",
    "sync_results_to_clarity",
    "sync_all_queues_from_clarity",
    "sync_recipient_from_call",
]
