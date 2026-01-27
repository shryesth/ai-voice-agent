Call End Flow - Chronological Timeline

  Phase 1: Voice Pipeline Completion

  When EndFrame is queued (via end_call function or timeout), the pipeline terminates and returns the FlowManager state containing all conversation data.

  Phase 2: Immediate CallRecord Update (Synchronous)

  Location: backend/app/services/call_service.py:161-300

  CallRecord fields updated:
  ┌──────────────────────────────────────────┬─────────────────────────────┐
  │                  Field                   │           Source            │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_state.completed_stages      │ FlowManager                 │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_state.current_stage         │ FlowManager                 │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_state.stage_retry_counts    │ FlowManager                 │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_data.is_visit_confirmed     │ Pipeline state              │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_data.is_service_confirmed   │ Pipeline state              │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_data.verification_responses │ Pipeline state              │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_data.satisfaction_rating    │ Pipeline state (1-10)       │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_data.has_side_effects       │ Pipeline state              │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_data.side_effects_reported  │ Pipeline state              │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ conversation_data.extracted_data         │ Pipeline state              │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ urgency_flagged                          │ True if severe side effects │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ urgency_keywords_detected                │ From pipeline               │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ call_tracking.outcome                    │ CallOutcome.COMPLETED_FULL  │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ error_message                            │ If abnormal completion      │
  ├──────────────────────────────────────────┼─────────────────────────────┤
  │ updated_at                               │ Current timestamp           │
  └──────────────────────────────────────────┴─────────────────────────────┘
  Phase 3: Twilio Status Webhook (Async)

  Endpoint: POST /api/v1/webhooks/twilio/status
  Task: update_call_from_webhook in backend/app/tasks/voice_call.py:149-217

  CallRecord fields updated:
  - call_tracking.status = "completed"
  - call_tracking.ended_at = timestamp
  - call_tracking.duration_seconds = from Twilio
  - call_tracking.outcome = only if not already set by pipeline

  Triggers: sync_recipient_from_call task

  Phase 4: Recording Download (Async, delayed 5-30s)

  Endpoint: POST /api/v1/webhooks/twilio/recording
  Task: download_twilio_recording in backend/app/tasks/recording_download.py

  CallRecord.recording fields updated:
  - s3_object_key, recording_url, duration_seconds
  - file_size_bytes, sample_rate, num_channels
  - uploaded_at, upload_status

  Phase 5: Recipient Sync (Async)

  Task: sync_recipient_from_call in backend/app/tasks/recipient_sync.py:77-195

  Recipient fields updated:
  ┌─────────────────────┬───────────────────────────────────────────────┐
  │        Field        │                     Value                     │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ call_attempts[]     │ New CallAttempt appended                      │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ conversation_result │ Deep copy of CallRecord.conversation_data     │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ status              │ COMPLETED, FAILED, NOT_REACHABLE, or RETRYING │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ completed_at        │ Timestamp (if terminal status)                │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ retry_count         │ Incremented if retrying                       │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ next_retry_at       │ Calculated if retrying                        │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ last_failure_reason │ If failed                                     │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ recording_url       │ Presigned S3 URL (24h expiry)                 │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ sync_status         │ SyncStatus.PENDING                            │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ urgency_flagged     │ From CallRecord                               │
  ├─────────────────────┼───────────────────────────────────────────────┤
  │ updated_at          │ Current timestamp                             │
  └─────────────────────┴───────────────────────────────────────────────┘
  Phase 6: Translation (Non-English calls)

  Task: translate_transcript in backend/app/tasks/transcript_translation.py

  CallRecord.english_translation fields updated:
  - status, source_language, messages[], completed_at, attempts

  Phase 7: Clarity Sync (Scheduled every 60s)

  Task: sync_results_to_clarity in backend/app/tasks/clarity_sync.py:111-274

  Recipient fields updated:
  - sync_status = SYNCED (or FAILED with sync_error)
  - last_synced_at = timestamp

  Phase 8: Queue Stats (Scheduled every 30s)

  Task: process-campaign-queues

  CallQueue.stats fields recalculated:
  - completed_count, failed_count, not_reachable_count
  - total_calls_made, successful_verifications, urgent_flagged_count
  - avg_call_duration_seconds, last_call_at

  ---
  Task Chain Diagram

  Call Ends
      │
      ├─► [Sync] update_call_from_pipeline_state() → CallRecord
      │       └─► [Async] translate_transcript (if non-English)
      │       └─► [Async] sync_recipient_from_call
      │
      ├─► [Async] Twilio status webhook
      │       └─► update_call_from_webhook task → CallRecord
      │               └─► sync_recipient_from_call → Recipient
      │                       └─► sync_results_to_clarity (if auto-push)
      │
      ├─► [Async] Twilio recording webhook (delayed)
      │       └─► download_twilio_recording task → CallRecord.recording
      │
      └─► [Scheduled] Periodic tasks
              ├─► sync-clarity-results (60s) → Recipient.sync_status
              └─► process-campaign-queues (30s) → CallQueue.stats