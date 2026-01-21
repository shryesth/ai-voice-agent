"""
Celery tasks for patient feedback collection.

This module imports all task functions to ensure they are registered
with the Celery worker when autodiscover_tasks() runs.
"""

from backend.app.tasks.queue_processor import process_campaign_queues
from backend.app.tasks.voice_call import initiate_patient_call, update_call_from_webhook
from backend.app.tasks.retry_handler import handle_call_completion, update_queue_from_call
from backend.app.tasks.recording_download import download_twilio_recording
from backend.app.tasks.split_recording import split_recording_task
from backend.app.tasks.transcript_translation import translate_transcript

__all__ = [
    "process_campaign_queues",
    "initiate_patient_call",
    "update_call_from_webhook",
    "handle_call_completion",
    "update_queue_from_call",
    "download_twilio_recording",
    "split_recording_task",
    "translate_transcript",
]
