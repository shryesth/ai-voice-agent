# Migration to Official pipecat-ai-flows Package

## What Changed

We migrated from a **custom flow_manager.py** implementation to the **official pipecat-ai-flows package** (v0.0.22).

## Why?

Our custom implementation had fundamental issues:

| Issue | Custom | Official |
|-------|--------|----------|
| **FlowResult type** | Pydantic BaseModel ❌ | TypedDict ✅ |
| **NodeConfig type** | Pydantic BaseModel ❌ | TypedDict ✅ |
| **FlowsFunctionSchema** | Pydantic BaseModel ❌ | @dataclass ✅ |
| **FlowManager deps** | Standalone ❌ | Requires Pipecat components ✅ |
| **LLM providers** | None ❌ | OpenAI, Anthropic, Gemini, Bedrock ✅ |
| **Actions** | None ❌ | Full action framework ✅ |
| **Context strategy** | None ❌ | APPEND, RESET, RESET_WITH_SUMMARY ✅ |
| **Maintenance** | Us ❌ | Pipecat team ✅ |

## Installation

```bash
pip install pipecat-ai-flows
```

Already added to [requirements.txt](../../../requirements.txt):

```requirements
pipecat-ai-flows>=0.0.22
```

## Code Changes

### Before (Custom Implementation)

```python
# ❌ OLD: Custom flow_manager.py
from backend.app.domains.supervisor.flow_manager import (
    FlowManager,
    FlowResult,
    NodeConfig,
    FlowsFunctionSchema,
)
```

### After (Official Package)

```python
# ✅ NEW: Official package
from pipecat_flows import (
    FlowManager,
    FlowResult,
    NodeConfig,
    FlowsFunctionSchema,
    FlowArgs,
)
```

## FlowManager Initialization

### Before (Incorrect - Standalone)

```python
# ❌ This was wrong - FlowManager can't work standalone
flow_manager = FlowManager()
await flow_manager.initialize()
```

### After (Correct - With Pipecat Pipeline)

```python
# ✅ FlowManager needs Pipecat components
from pipecat_flows import FlowManager

flow_manager = FlowManager(
    task=pipeline_task,              # PipelineTask
    llm=llm_service,                 # LLMService (OpenAI, Anthropic, etc.)
    context_aggregator=llm_context,  # LLMContext
    tts=tts_service,                 # Optional TTS
    transport=transport,             # Optional transport
)

# Initialize with starting node
await flow_manager.initialize(initial_node=create_greeting_node())
```

## Type Definitions

### FlowResult (TypedDict)

```python
from typing import TypedDict

class FlowResult(TypedDict, total=False):
    status: str
    error: str

# Custom results extend FlowResult
class GreetingResult(FlowResult):
    person_confirmed: bool
```

### NodeConfig (TypedDict)

```python
from typing import TypedDict, List, Dict, Any

class NodeConfig(TypedDict, total=False):
    name: str                                  # Optional
    task_messages: List[Dict[str, Any]]       # Required
    role_messages: List[Dict[str, Any]]       # Optional
    functions: List[...]                       # Optional
    pre_actions: List[ActionConfig]           # Optional
    post_actions: List[ActionConfig]          # Optional
    context_strategy: ContextStrategyConfig   # Optional
```

### FlowsFunctionSchema (@dataclass)

```python
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Callable

@dataclass
class FlowsFunctionSchema:
    name: str
    description: str
    properties: Dict[str, Any]
    required: List[str]
    handler: Optional[Callable] = None
    transition_to: Optional[str] = None        # Deprecated
    transition_callback: Optional[Callable] = None  # Deprecated
```

## Function Handler Signature

```python
from pipecat_flows import FlowArgs, FlowManager, FlowResult, NodeConfig
from typing import Optional, Tuple

async def handler(
    args: FlowArgs,           # Dict[str, Any]
    flow_manager: FlowManager
) -> Tuple[Optional[FlowResult], Optional[NodeConfig]]:
    """
    Modern consolidated handler pattern.
    
    Returns:
        (result, next_node) tuple where:
        - result: FlowResult with status/data (optional)
        - next_node: NodeConfig for next stage or None to end
    """
    # Process arguments
    value = args.get("param_name")
    
    # Update flow state
    flow_manager.state["key"] = value
    
    # Return result and next node
    return GreetingResult(person_confirmed=True), create_introduction_node()
```

## State Management

```python
# Access flow state
flow_manager.state["person_confirmed"] = True
flow_manager.state["visit_confirmed"] = False

# Check completion
if flow_manager.current_node is None:
    # Flow ended
    conversation_data = flow_manager.state
```

## Multi-Provider Support

The official package automatically handles format differences:

```python
# Works with all providers:
# - OpenAI (function calling)
# - Anthropic (native tools)
# - Google Gemini (function declarations)
# - AWS Bedrock (Anthropic-compatible)

flow_manager = FlowManager(
    task=task,
    llm=openai_service,  # or anthropic_service, gemini_service, etc.
    context_aggregator=context,
)
```

## Error Handling

```python
from pipecat_flows import (
    FlowError,
    FlowInitializationError,
    FlowTransitionError,
    InvalidFunctionError,
    ActionError,
)

try:
    await flow_manager.initialize(initial_node=greeting_node)
except FlowInitializationError as e:
    logger.error(f"Failed to initialize flow: {e}")
except FlowTransitionError as e:
    logger.error(f"Invalid transition: {e}")
```

## Actions (New Feature)

```python
from pipecat_flows import ActionConfig

# Pre-action (before LLM inference)
pre_action = ActionConfig(
    type="log_entry",
    handler=log_handler,
    message="Entering greeting stage"
)

# Post-action (after LLM inference)
post_action = ActionConfig(
    type="tts_say",
    text="Please hold while we process..."
)

node = NodeConfig(
    task_messages=[...],
    functions=[...],
    pre_actions=[pre_action],
    post_actions=[post_action]
)
```

## Context Strategies (New Feature)

```python
from pipecat_flows import ContextStrategy, ContextStrategyConfig

# Append messages (default)
context_strategy = ContextStrategyConfig(
    strategy=ContextStrategy.APPEND
)

# Reset context with new messages only
context_strategy = ContextStrategyConfig(
    strategy=ContextStrategy.RESET
)

# Reset with LLM-generated summary
context_strategy = ContextStrategyConfig(
    strategy=ContextStrategy.RESET_WITH_SUMMARY
)

node = NodeConfig(
    task_messages=[...],
    context_strategy=context_strategy
)
```

## Direct Functions (New Feature)

Automatically extract metadata from function signature:

```python
async def do_something(
    flow_manager: FlowManager,
    foo: int,
    bar: str = ""
) -> Tuple[FlowResult, NodeConfig]:
    """
    Do something interesting.
    
    Args:
        foo: The foo to do something with.
        bar: The bar to do something with.
    """
    result = await process(foo, bar)
    return result, create_next_node()

# Use directly without FlowsFunctionSchema
node = NodeConfig(
    task_messages=[...],
    functions=[do_something]  # Metadata auto-extracted!
)
```

## Files Affected

### Deleted

- ❌ `backend/app/domains/supervisor/flow_manager.py`

### Modified

- ✅ `backend/app/domains/supervisor/__init__.py` - Updated imports
- ✅ `backend/app/domains/supervisor/conversation_flow.py` - Updated imports
- ✅ `requirements.txt` - Added pipecat-ai-flows

### Documentation Updated

- ✅ `backend/app/domains/supervisor/README.md`
- ✅ `backend/app/domains/supervisor/ARCHITECTURE.md`
- ✅ `backend/app/domains/supervisor/MIGRATION.md` (this file)

## Testing

After migration, verify:

1. **Import check:**

   ```bash
   python -c "from pipecat_flows import FlowManager, FlowResult, NodeConfig, FlowsFunctionSchema; print('✅ Imports OK')"
   ```

2. **Type check:**

   ```bash
   mypy backend/app/domains/supervisor/conversation_flow.py
   ```

3. **Run tests:**

   ```bash
   pytest tests/integration/test_voice_pipeline.py -v
   ```

## Benefits Realized

1. ✅ **Correct type system** - No more Pydantic where TypedDict/dataclass should be used
2. ✅ **Proper integration** - FlowManager works with Pipecat pipeline
3. ✅ **Multi-provider** - Works with OpenAI, Anthropic, Gemini automatically
4. ✅ **Feature complete** - Actions, context strategies, error handling
5. ✅ **Maintained** - Updates and bug fixes from Pipecat team
6. ✅ **Tested** - Battle-tested in production environments

## References

- [Pipecat Flows Documentation](https://docs.pipecat.ai/frameworks/flows/pipecat-flows)
- [Pipecat Flows GitHub](https://github.com/pipecat-ai/pipecat-flows)
- [Official Examples](https://github.com/pipecat-ai/pipecat-flows/tree/main/examples)
- [Patient Intake Example](https://github.com/pipecat-ai/pipecat-flows/blob/main/examples/patient_intake.py)

## Support

If you encounter issues:

1. Check [Pipecat Flows Issues](https://github.com/pipecat-ai/pipecat-flows/issues)
2. Join [Pipecat Discord](https://discord.gg/pipecat)
3. Review [API Reference](https://reference-flows.pipecat.ai/)
