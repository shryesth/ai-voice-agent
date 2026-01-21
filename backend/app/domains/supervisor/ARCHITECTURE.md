# Architecture Comparison: Supervisor Conversation Flow

## Problem Statement

The original implementation had **conflicting dual control structure**:

- comprehensive.txt defined detailed "Stage 1, Stage 2, Stage 3..." instructions
- Pipecat Flows NodeConfig also provided task_messages per stage

This violated Pipecat best practices and caused:

- AI deviation from script
- Not following conversation stages correctly
- LLM confusion about which instructions to follow

## Solution: Clean Separation + Official Package

Following Pipecat v0.0.99 documentation, we:

1. Separated concerns (personality vs. structure)
2. **Switched to official `pipecat-ai-flows` package** instead of custom implementation

### Before (Problematic)

#### comprehensive.txt (Conflicting)

```
## Conversation Flow

Follow these stages in order:

### Stage 1: Greeting
- Greet the person warmly
- Confirm you are speaking with the correct person
- If they confirm, proceed to introduction
- If wrong person, politely apologize and end the call

### Stage 2: Introduction
- Explain you are calling from the Ministry of Health
- Mention this is about a recent health visit
- Ask if they have a few minutes to answer some questions
- If they decline, thank them and end the call politely

[... more detailed stage instructions ...]
```

#### NodeConfig (Also defining stages)

```python
NodeConfig(
    name="greeting",
    task_messages=[
        {"role": "system", "content": "Greet and confirm identity..."}
    ]
)
```

**Problem:** LLM receives TWO different sets of stage instructions!

---

### After (Clean Architecture)

#### comprehensive.txt (Personality & Guidelines ONLY)

```
You are an AI assistant calling on behalf of the Ministry of Health.

## Your Identity and Role
- You represent the Ministry of Health
- You are professional, friendly, and respectful
- You speak clearly at a moderate pace
[...]

## Communication Guidelines
- Keep responses concise - aim for 2-3 sentences maximum
- Use simple, clear language
- Show empathy and warmth
[...]

## Boundaries and Scope

### What You CAN Do
✓ Verify visit information
✓ Ask about satisfaction
✓ Flag urgent concerns
[...]

### What You CANNOT Do
✗ Provide medical advice
✗ Share patient information
✗ Pressure anyone to answer
[...]

## Handling Difficult Situations

### Wrong Person or Wrong Number
- Apologize politely
- Thank them for their time
- End gracefully
[...]
```

**No stage/phase instructions** - just personality, rules, boundaries

#### conversation_flow.py (Structure ONLY)

```python
def create_greeting_node() -> NodeConfig:
    """
    Initial greeting and person confirmation.
    
    Goal: Greet warmly and confirm speaking with the correct person.
    """
    
    async def greeting_handler(args: FlowArgs, flow_manager: FlowManager):
        person_confirmed = args.get("person_confirmed", False)
        
        if not person_confirmed:
            # Wrong person - end call
            return GreetingResult(person_confirmed=False), None
        
        # Confirmed - proceed to introduction
        return GreetingResult(person_confirmed=True), create_introduction_node()
    
    return NodeConfig(
        name="greeting",
        role_messages=[
            {"role": "system", "content": "You are a friendly assistant calling on behalf of the Ministry of Health."}
        ],
        task_messages=[
            {"role": "system", "content": "Greet the person warmly. Ask if you are speaking with the correct person by name. If they confirm, proceed. If wrong person, apologize and end."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="confirm_person",
                description="Person confirmed whether they are correct person",
                properties={
                    "person_confirmed": {
                        "type": "boolean",
                        "description": "True if correct person, False if wrong"
                    }
                },
                required=["person_confirmed"],
                handler=greeting_handler
            )
        ]
    )
```

**Clear structure** - ONE focused instruction per stage

---

## Benefits of New Architecture

### 1. Improved LLM Accuracy

**Before:** LLM confused by two instruction sources
**After:** LLM sees exactly ONE task per stage

### 2. Reduced Deviation

**Before:** AI went off-topic when comprehensive.txt said "Stage 1, Stage 2..." but NodeConfig said something else
**After:** AI stays focused on current node's single task

### 3. Better Maintainability

**Before:** Had to update stage logic in TWO places (comprehensive.txt AND conversation_flow.py)
**After:** Update stages in conversation_flow.py ONLY, personality stays in comprehensive.txt

### 4. Easier Debugging

**Before:** Hard to tell which instruction set LLM was following
**After:** Clear which node is active and what it should do

### 5. Follows Pipecat Best Practices

**Before:** Violated "large monolithic prompts" warning
**After:** Matches documented pattern with focused nodes

## Pipecat Documentation Quote

> "Traditional methods often use large, monolithic prompts with many tools available at once, leading to hallucinations and lower accuracy. Pipecat Flows solves this by: Breaking complex tasks into focused steps - Each node has a clear, single purpose."

> "Pipecat Flows is best suited for use cases where: You need precise control over how a conversation progresses through specific steps... You want to improve LLM accuracy by focusing the model on one specific task at a time instead of managing multiple responsibilities simultaneously."

## File Changes Summary

### Created Files

1. `backend/app/domains/supervisor/conversation_flow.py` - 7 NodeConfig functions using official package
2. `backend/app/domains/supervisor/README.md` - Architecture documentation
3. `backend/app/domains/supervisor/ARCHITECTURE.md` - This comparison document
4. `backend/app/domains/supervisor/FLOW_DIAGRAM.md` - Visual flow diagrams

### Modified Files

1. `backend/app/domains/supervisor/prompts/en/comprehensive.txt` - Removed stage instructions, kept personality/rules
2. `backend/app/domains/supervisor/__init__.py` - Updated to import from `pipecat_flows`
3. `requirements.txt` - Added `pipecat-ai-flows>=0.0.99`

### Deleted Files

1. `backend/app/domains/supervisor/flow_manager.py` - Replaced by official package

## Why Official Package?

Our initial custom `flow_manager.py` had critical issues:

### Problems with Custom Implementation

❌ **FlowResult** was Pydantic BaseModel (official uses TypedDict)  
❌ **NodeConfig** was Pydantic BaseModel (official uses TypedDict)  
❌ **FlowsFunctionSchema** was Pydantic BaseModel (official uses @dataclass)  
❌ **FlowManager** missing required Pipecat components (task, llm, context_aggregator, tts)  
❌ No LLM provider adapter system (OpenAI, Anthropic, Gemini formats differ)  
❌ Missing action execution framework  
❌ No context strategy management  
❌ Incomplete error handling hierarchy  

### Official Package Advantages

✅ **Correct type system** matching Pipecat standards  
✅ **Fully integrated** with Pipecat pipeline (requires task, llm, context_aggregator)  
✅ **Multi-provider support** with automatic format conversion  
✅ **Tested and maintained** by Pipecat team  
✅ **Complete features**: actions, context strategies, direct functions  
✅ **Better error handling** with custom exception hierarchy  

## Migration Checklist

- [x] Install official pipecat-ai-flows package
- [x] Remove custom flow_manager.py
- [x] Update imports to use pipecat_flows
- [x] Create 7 NodeConfig functions (greeting, introduction, confirm_visit, confirm_service, side_effects, satisfaction, closing)
- [x] Define FlowResult classes for typed returns
- [x] Implement function handlers with state transitions
- [x] Simplify comprehensive.txt to personality/guidelines only
- [x] Update domain **init**.py exports
- [x] Document architecture in README

## Installation

```bash
pip install pipecat-ai-flows
```

Or add to requirements.txt:

```
pipecat-ai-flows>=0.0.99
```

## Next Steps

To integrate into voice pipeline:

1. Initialize FlowManager when call starts
2. Load comprehensive.txt as system instructions
3. Get initial node with `create_greeting_node()`
4. Set LLM tools from node.functions
5. When function called, handler returns next node
6. Update LLM tools with next_node.functions
7. Repeat until conversation ends

## Testing Recommendations

1. Test each stage transition independently
2. Verify state persistence in flow_manager.state
3. Test early termination scenarios (wrong person, declined)
4. Test optional stage (side effects) is skipped when not needed
5. Test urgent flagging (severe side effects, low satisfaction)
6. Verify EndFrame queuing terminates call properly

## References

- [Pipecat Flows Introduction](https://docs.pipecat.ai/flows/introduction)
- [Pipecat Flows Examples](https://github.com/pipecat-ai/pipecat-flows/tree/main/examples)
- Original implementation: `backend/app/domains/patient_feedback/conversation_flow.py` (reference pattern)
