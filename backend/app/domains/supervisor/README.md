# Supervisor Conversation Flow Architecture

## Overview

The Supervisor domain implements a **7-stage conversation flow** using the **official pipecat-ai-flows package** (v0.0.22). This architecture separates conversation structure from personality/rules, following Pipecat best practices.

## Installation

```bash
pip install pipecat-ai-flows
```

## Architecture Pattern

### Two-Layer Design

1. **Flow Layer** (`conversation_flow.py`): Defines conversation structure with NodeConfig nodes
   - Each stage = one NodeConfig with focused task_messages
   - Function handlers control transitions between stages
   - Stores state in FlowManager for persistence

2. **Personality Layer** (`prompts/en/comprehensive.txt`): Defines AI behavior and guidelines
   - Identity, role, and communication style
   - Boundaries and scope (CAN/CANNOT do lists)
   - Handling difficult situations
   - Critical rules and guidelines
   - **Does NOT contain phase/stage instructions** (that's in conversation_flow.py)

### Why This Separation?

Per Pipecat documentation:
> "Traditional methods often use large, monolithic prompts with many tools available at once, leading to hallucinations and lower accuracy. Pipecat Flows solves this by: Breaking complex tasks into focused steps - Each node has a clear, single purpose."

**Benefits:**

- LLM focuses on ONE task at a time (current node's task_messages)
- Reduces confusion from conflicting instructions
- Improves accuracy by limiting available functions per stage
- Easier to debug and modify individual stages

## 7-Stage Flow

### Stage 1: Greeting

**Goal:** Warmly greet and confirm speaking with correct person

**Functions:**

- `confirm_person(person_confirmed: bool)`

**Transitions:**

- If confirmed → Stage 2 (Introduction)
- If wrong person → End call

### Stage 2: Introduction

**Goal:** Explain purpose (Ministry of Health call) and ask for time

**Functions:**

- `confirm_availability(time_given: bool)`

**Transitions:**

- If agreed → Stage 3 (Confirm Visit)
- If declined → End call

### Stage 3: Confirm Visit

**Goal:** Verify they visited specific facility on date

**Functions:**

- `record_visit_response(visit_confirmed: bool, discrepancy_noted: bool)`

**Transitions:**

- Always → Stage 4 (Confirm Service)
- If discrepancy → Flag for human callback

### Stage 4: Confirm Service

**Goal:** Verify exact service received (event-specific question)

**Functions:**

- `record_service_response(service_confirmed: bool)`

**Transitions:**

- If `requires_side_effects=True` → Stage 5 (Side Effects)
- Else → Stage 6 (Satisfaction)

### Stage 5: Side Effects (Optional)

**Goal:** Ask about side effects from vaccination

**Functions:**

- `record_side_effects(has_side_effects: bool, details: str, severe: bool)`

**Transitions:**

- Always → Stage 6 (Satisfaction)
- If severe → Flag as urgent

### Stage 6: Satisfaction Rating

**Goal:** Collect 1-10 rating and feedback

**Functions:**

- `record_satisfaction(rating: int, feedback: str)`

**Transitions:**

- Always → Stage 7 (Closing)
- If rating < 5 → Flag for follow-up

### Stage 7: Closing

**Goal:** Thank caller and end professionally

**Functions:**

- `end_call(reason: str)`

**Transitions:**

- None (call ends)

## File Structure

```
backend/app/domains/supervisor/
├── __init__.py                          # Exports flow components (imports from pipecat_flows)
├── conversation_flow.py                 # 7 NodeConfig functions
├── event_type_config.py                 # Event-specific configurations
└── prompts/
    └── en/
        └── comprehensive.txt            # Personality & guidelines ONLY
```

**Note:** We use the official `pipecat-ai-flows` package instead of custom flow_manager.py.

## Usage Example

```python
from pipecat_flows import FlowManager
from backend.app.domains.supervisor import create_greeting_node
)

# Initialize flow
flow_manager = FlowManager()
await flow_manager.initialize()

# Get starting node
initial_node = create_greeting_node()

# Access current state
current_stage = flow_manager.current_stage  # "greeting"
is_done = flow_manager.is_complete  # False

# Store task reference for frame queuing
flow_manager.task = pipeline_task

# Get collected data for persistence
conversation_data = flow_manager.get_conversation_data()
```

## State Management

FlowManager tracks:

- `current_stage`: Name of active stage
- `completed_stages`: List of finished stages
- `person_confirmed`: Greeting result
- `time_given`: Introduction result
- `visit_confirmed`: Visit verification result
- `service_confirmed`: Service verification result
- `has_side_effects`: Side effects result
- `satisfaction_rating`: 1-10 rating
- `satisfaction_feedback`: Open-ended feedback
- `human_callback_requested`: Flag for follow-up
- `urgency_flagged`: Medical urgency flag
- `completed`: Boolean indicating call finished
- `completion_reason`: Why call ended

## NodeConfig Structure

Each stage follows this pattern:

```python
def create_stage_node() -> NodeConfig:
    async def handler(args: FlowArgs, flow_manager: FlowManager):
        # 1. Extract function arguments
        value = args.get("param_name")
        
        # 2. Update flow state
        flow_manager.state["key"] = value
        flow_manager.state["completed_stages"].append("stage_name")
        flow_manager.state["current_stage"] = "next_stage"
        
        # 3. Return result and next node
        return StageResult(value=value), create_next_node()
    
    return NodeConfig(
        name="stage_name",
        role_messages=[
            {"role": "system", "content": "Your identity/personality"}
        ],
        task_messages=[
            {"role": "system", "content": "What to do in THIS stage ONLY"}
        ],
        functions=[
            FlowsFunctionSchema(
                name="function_name",
                description="What the function does",
                properties={
                    "param_name": {
                        "type": "boolean",
                        "description": "Parameter description"
                    }
                },
                required=["param_name"],
                handler=handler
            )
        ]
    )
```

## Key Principles

1. **One Node = One Task**: Each NodeConfig has a single, focused purpose
2. **Minimal Functions**: Only include functions needed for current stage
3. **Clear Transitions**: Handler explicitly returns next node (or None to end)
4. **State Persistence**: Store all data in flow_manager.state for later retrieval
5. **Frame Queuing**: Use flow_manager.task.queue_frames() for TTS and EndFrame
6. **Prompt Separation**: comprehensive.txt contains personality/rules, NOT stage instructions

## Comparison: Before vs After

### ❌ Before (Conflicting Dual Control)

- **comprehensive.txt**: "Phase 1: Greeting... Phase 2: Introduction..."
- **FlowManager**: NodeConfig with task_messages per stage
- **Problem**: LLM receives TWO sets of flow instructions → confusion, deviation

### ✅ After (Clean Separation)

- **comprehensive.txt**: Identity, boundaries, communication style (no phases)
- **conversation_flow.py**: NodeConfig per stage with focused task_messages
- **Result**: LLM sees ONE clear instruction per stage → better accuracy

## Why Official pipecat-ai-flows Package?

Our initial custom implementation had several issues that the official package solves:

### Custom Implementation Problems

- ❌ FlowResult was Pydantic BaseModel (should be TypedDict)
- ❌ NodeConfig was Pydantic BaseModel (should be TypedDict)
- ❌ FlowsFunctionSchema was Pydantic BaseModel (should be @dataclass)
- ❌ FlowManager missing required Pipecat dependencies (task, llm, context_aggregator)
- ❌ No LLM provider adapter system
- ❌ Missing action execution framework

### Official Package Benefits

- ✅ Correct type system (TypedDict, @dataclass as per Pipecat standards)
- ✅ Properly integrated with Pipecat pipeline components
- ✅ Multi-provider support (OpenAI, Anthropic, Gemini, AWS Bedrock)
- ✅ Tested and maintained by the Pipecat team
- ✅ Complete feature set (actions, context strategies, error handling)
- ✅ Automatic function registration and validation

## Integration with Pipecat

```python
from pipecat.services.openai_realtime import OpenAIRealtimeService
from backend.app.domains.supervisor import create_greeting_node

# Create LLM service
llm = OpenAIRealtimeService(
    api_key=settings.OPENAI_API_KEY,
    model="gpt-4o-realtime-preview-2024-12-17"
)

# Load personality prompt
with open("prompts/en/comprehensive.txt") as f:
    system_prompt = f.read()

# Set initial instructions
llm.set_instructions(system_prompt)

# Get starting node and set available functions
initial_node = create_greeting_node()
llm.set_tools([func.to_openai_tool() for func in initial_node.functions])

# When function called, handler returns next node
result, next_node = await handler(args, flow_manager)
if next_node:
    llm.set_tools([func.to_openai_tool() for func in next_node.functions])
```

## Testing

See `tests/integration/test_voice_pipeline.py` for FlowManager test examples:

- Initialization
- Stage transitions
- State persistence
- Conversation data retrieval

## Migration Guide

If you have existing monolithic prompts with detailed phases:

1. **Extract personality/rules** → Move to comprehensive.txt
2. **Extract phase instructions** → Create NodeConfig functions in conversation_flow.py
3. **Define function schemas** → Add to each NodeConfig with handlers
4. **Update LLM integration** → Use initial node's functions, switch on transitions

## References

- [Pipecat Flows Documentation](https://docs.pipecat.ai/flows/introduction)
- [Patient Intake Example](https://github.com/pipecat-ai/pipecat-flows/blob/main/examples/patient_intake.py)
- Pipecat v0.0.99 API
