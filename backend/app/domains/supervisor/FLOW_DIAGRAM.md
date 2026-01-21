# Supervisor Conversation Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CALL INITIATED                                  │
│                     FlowManager.initialize()                            │
│                   Load comprehensive.txt as system prompt               │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: GREETING                                                      │
│  ────────────────────────────────────────────────────────────────────  │
│  Task: "Greet warmly and confirm speaking with correct person"         │
│  Function: confirm_person(person_confirmed: bool)                       │
│                                                                         │
│  Handler Logic:                                                         │
│    if person_confirmed:                                                 │
│      → Store state["person_confirmed"] = True                          │
│      → Return (GreetingResult, create_introduction_node())             │
│    else:                                                                │
│      → Store state["wrong_person"] = True                              │
│      → Queue EndFrame                                                   │
│      → Return (GreetingResult, None)  # END CALL                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                         person_confirmed = True
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: INTRODUCTION                                                  │
│  ────────────────────────────────────────────────────────────────────  │
│  Task: "Explain calling from Ministry of Health, ask for time"         │
│  Function: confirm_availability(time_given: bool)                       │
│                                                                         │
│  Handler Logic:                                                         │
│    if time_given:                                                       │
│      → Store state["time_given"] = True                                │
│      → Return (IntroductionResult, create_confirm_visit_node())        │
│    else:                                                                │
│      → Store state["declined_call"] = True                             │
│      → Queue EndFrame                                                   │
│      → Return (IntroductionResult, None)  # END CALL                   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                          time_given = True
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: CONFIRM VISIT                                                 │
│  ────────────────────────────────────────────────────────────────────  │
│  Task: "Ask if visited specific facility on date"                      │
│  Function: record_visit_response(visit_confirmed, discrepancy_noted)    │
│                                                                         │
│  Handler Logic:                                                         │
│    Store state["visit_confirmed"] = visit_confirmed                    │
│    Store state["visit_discrepancy"] = discrepancy_noted                │
│    if discrepancy_noted:                                                │
│      → Flag state["human_callback_requested"] = True                   │
│    → Return (VisitConfirmationResult, create_confirm_service_node())   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 4: CONFIRM SERVICE                                               │
│  ────────────────────────────────────────────────────────────────────  │
│  Task: "Ask event-specific confirmation question"                      │
│  Function: record_service_response(service_confirmed: bool)             │
│                                                                         │
│  Handler Logic:                                                         │
│    Store state["service_confirmed"] = service_confirmed                │
│    if not service_confirmed:                                            │
│      → Flag state["service_not_confirmed_followup"] = True             │
│                                                                         │
│    Check state["requires_side_effects"]:                               │
│      if True  → Return (ServiceResult, create_side_effects_node())     │
│      if False → Return (ServiceResult, create_satisfaction_node())     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
         requires_side_effects?               │
                    │                         │
              YES   │                    NO   │
                    ▼                         │
┌──────────────────────────────────┐          │
│  STAGE 5: SIDE EFFECTS           │          │
│  (OPTIONAL - Vaccination only)   │          │
│  ────────────────────────────    │          │
│  Task: "Ask about side effects"  │          │
│  Function: record_side_effects() │          │
│    (has_side_effects, details,   │          │
│     severe)                      │          │
│                                  │          │
│  Handler Logic:                  │          │
│    Store all side effects data   │          │
│    if severe:                    │          │
│      → Flag urgency_flagged=True │          │
│    → Return (SideEffectsResult,  │          │
│       create_satisfaction_node())│          │
└──────────────────┬───────────────┘          │
                   │                          │
                   └──────────┬───────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 6: SATISFACTION RATING                                           │
│  ────────────────────────────────────────────────────────────────────  │
│  Task: "Ask for 1-10 rating and any feedback"                          │
│  Function: record_satisfaction(rating: int, feedback: str)              │
│                                                                         │
│  Handler Logic:                                                         │
│    Store state["satisfaction_rating"] = rating                         │
│    Store state["satisfaction_feedback"] = feedback                     │
│    if rating < 5:                                                       │
│      → Flag state["low_satisfaction_followup"] = True                  │
│    → Return (SatisfactionResult, create_closing_node())                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 7: CLOSING                                                       │
│  ────────────────────────────────────────────────────────────────────  │
│  Task: "Thank caller, wish good health, end professionally"            │
│  Function: end_call(reason: str)                                        │
│                                                                         │
│  Handler Logic:                                                         │
│    Store state["completed"] = True                                     │
│    Store state["completion_reason"] = reason                           │
│                                                                         │
│    Build personalized goodbye:                                          │
│      - Base: "Thank you for your time and feedback"                    │
│      - If human_callback_requested: Add follow-up message              │
│      - If severe_side_effects: Add healthcare provider advice          │
│      - If low_satisfaction_followup: Add improvement message           │
│      - End: "Wishing you good health. Have a wonderful day!"           │
│                                                                         │
│    Queue TTSSpeakFrame(goodbye_message)                                │
│    Queue EndFrame()                                                     │
│    → Return (ClosingResult, None)  # END CALL                          │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  CALL ENDED    │
                        │  Save state to │
                        │  CallRecord    │
                        └────────────────┘
```

## State Flags and Their Effects

```
┌──────────────────────────────┬──────────────────────────────────────────┐
│ Flag                         │ Effect                                    │
├──────────────────────────────┼──────────────────────────────────────────┤
│ wrong_person = True          │ • End call immediately                    │
│                              │ • completion_reason = "wrong_person"      │
├──────────────────────────────┼──────────────────────────────────────────┤
│ declined_call = True         │ • End call politely                       │
│                              │ • completion_reason = "declined"          │
├──────────────────────────────┼──────────────────────────────────────────┤
│ visit_discrepancy = True     │ • Flag for human callback                 │
│                              │ • Continue with remaining questions       │
├──────────────────────────────┼──────────────────────────────────────────┤
│ service_not_confirmed = True │ • Flag for follow-up                      │
│                              │ • Continue flow                           │
├──────────────────────────────┼──────────────────────────────────────────┤
│ severe_side_effects = True   │ • Flag urgency_flagged = True             │
│                              │ • Add medical advice to goodbye           │
│                              │ • Requires immediate follow-up            │
├──────────────────────────────┼──────────────────────────────────────────┤
│ low_satisfaction (< 5) = True│ • Flag for follow-up                      │
│                              │ • Add improvement message to goodbye      │
├──────────────────────────────┼──────────────────────────────────────────┤
│ requires_side_effects = True │ • Include Stage 5 (Side Effects)          │
│ (from event config)          │ • Usually for vaccination events          │
└──────────────────────────────┴──────────────────────────────────────────┘
```

## Data Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│  OpenAI Realtime API (LLM)                                           │
│  ──────────────────────────────────────────────────────────────────  │
│  System Instructions: comprehensive.txt (personality & rules)        │
│  Available Tools: Current node's functions only                      │
│                                                                      │
│  Example at Stage 1 (Greeting):                                     │
│    Tools = [confirm_person]                                         │
│                                                                      │
│  When confirm_person(person_confirmed=True) called:                 │
│    1. Handler executes                                              │
│    2. Updates flow_manager.state                                    │
│    3. Returns (GreetingResult, create_introduction_node())          │
│    4. Voice pipeline switches to introduction_node                  │
│    5. LLM tools updated to [confirm_availability]                   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FlowManager.state (Persistent Storage)                             │
│  ──────────────────────────────────────────────────────────────────  │
│  {                                                                   │
│    "current_stage": "introduction",                                 │
│    "completed_stages": ["greeting"],                                │
│    "person_confirmed": true,                                        │
│    "time_given": null,                                              │
│    "visit_confirmed": null,                                         │
│    "service_confirmed": null,                                       │
│    "has_side_effects": null,                                        │
│    "satisfaction_rating": null,                                     │
│    "urgency_flagged": false,                                        │
│    "human_callback_requested": false,                               │
│    "completed": false,                                              │
│    "completion_reason": null                                        │
│  }                                                                   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Database (CallRecord)                                              │
│  ──────────────────────────────────────────────────────────────────  │
│  At call end, flow_manager.get_conversation_data() saved to:        │
│  - call_records.conversation_state (JSON)                           │
│  - call_records.status (completed/failed)                           │
│  - call_records.completion_reason                                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Early Termination Paths

```
┌─────────────────────────────────────────────────────────────────────┐
│  NORMAL FLOW (Complete 7 stages)                                    │
│  Greeting → Introduction → Confirm Visit → Confirm Service →        │
│  [Side Effects] → Satisfaction → Closing                            │
│  Duration: ~2-3 minutes                                             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  WRONG PERSON (End at Stage 1)                                      │
│  Greeting → END                                                      │
│  Duration: ~15 seconds                                              │
│  Flags: wrong_person=True, completion_reason="wrong_person"         │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  DECLINED CALL (End at Stage 2)                                     │
│  Greeting → Introduction → END                                       │
│  Duration: ~30 seconds                                              │
│  Flags: declined_call=True, completion_reason="declined"            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  SKIP SIDE EFFECTS (Non-vaccination)                                │
│  Greeting → Introduction → Confirm Visit → Confirm Service →        │
│  Satisfaction → Closing                                             │
│  Duration: ~1.5-2 minutes (Stage 5 skipped)                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Legend

```
┌──────┐
│ Node │  = Conversation stage (NodeConfig)
└──────┘

   │
   ▼      = Flow transition

┌─────┐
│ END │  = Call terminates (EndFrame queued)
└─────┘

  (?)    = Conditional branch based on state
```
