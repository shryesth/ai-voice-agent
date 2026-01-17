"""
Custom flow management for conversation state machine.

Replaces imaginary pipecat-flows package with local implementation.
Provides FlowManager, NodeConfig, FlowArgs, FlowResult, and FlowsFunctionSchema
for multi-stage conversation flows.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel


class FlowResult(BaseModel):
    """Base class for flow stage results."""
    pass


@dataclass
class FlowsFunctionSchema:
    """
    Function schema for LLM function calling.

    Defines the structure for tools/functions that can be called
    by the LLM during conversation flow execution.
    """
    name: str
    description: str
    properties: Dict[str, Any]
    required: List[str]
    handler: Callable

    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": self.required
                }
            }
        }


@dataclass
class NodeConfig:
    """
    Configuration for a conversation stage node.

    Defines the prompts, context, and available functions for
    a specific stage in the conversation flow.
    """
    name: str
    role_messages: List[Dict[str, str]]
    task_messages: List[Dict[str, str]]
    functions: List[FlowsFunctionSchema] = field(default_factory=list)

    def get_messages(self) -> List[Dict[str, str]]:
        """Get combined role and task messages for LLM context."""
        return self.role_messages + self.task_messages


class FlowArgs(dict):
    """
    Dictionary wrapper for function handler arguments.

    Provides a dict-like interface for accessing arguments
    passed to flow function handlers from LLM function calls.
    """
    pass


class FlowManager:
    """
    State machine for multi-stage conversation flows.

    Manages conversation state, tracks the current stage (node),
    and provides function schemas to the LLM based on the
    current conversation stage.
    """

    def __init__(self, initial_node: NodeConfig, context: Any = None):
        """
        Initialize the flow manager.

        Args:
            initial_node: Starting node configuration for the conversation
            context: Optional LLM context object for state management
        """
        self.current_node: Optional[NodeConfig] = initial_node
        self.context = context
        self.state: Dict[str, Any] = {}
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the flow manager and prepare for conversation."""
        self._initialized = True
        self.state["started_at"] = True

    def get_current_function_schemas(self) -> List[FlowsFunctionSchema]:
        """
        Get function schemas for current node.

        Returns:
            List of FlowsFunctionSchema objects available at current stage
        """
        if not self.current_node:
            return []
        return self.current_node.functions

    def get_current_messages(self) -> List[Dict[str, str]]:
        """
        Get messages for current node.

        Returns:
            Combined role and task messages for current stage
        """
        if not self.current_node:
            return []
        return self.current_node.get_messages()

    async def transition_to(self, next_node: Optional[NodeConfig]) -> None:
        """
        Transition to the next conversation stage.

        Args:
            next_node: The next NodeConfig to transition to, or None to end
        """
        if next_node:
            self.current_node = next_node
        else:
            self.current_node = None
            self.state["completed"] = True

    async def handle_function_call(
        self,
        function_name: str,
        arguments: Dict[str, Any]
    ) -> tuple[FlowResult, Optional[NodeConfig]]:
        """
        Handle a function call from the LLM.

        Finds the matching function schema in the current node and
        executes its handler with the provided arguments.

        Args:
            function_name: Name of the function being called
            arguments: Arguments passed by the LLM

        Returns:
            Tuple of (FlowResult, next_node or None)

        Raises:
            ValueError: If function not found in current node
        """
        if not self.current_node:
            raise ValueError("No current node - flow may have ended")

        # Find matching function
        for func_schema in self.current_node.functions:
            if func_schema.name == function_name:
                args = FlowArgs(arguments)
                result, next_node = await func_schema.handler(args, self)

                # Transition to next node
                await self.transition_to(next_node)

                return result, next_node

        raise ValueError(f"Function '{function_name}' not found in current node '{self.current_node.name}'")

    @property
    def is_complete(self) -> bool:
        """Check if the conversation flow has completed."""
        return self.current_node is None or self.state.get("completed", False)

    @property
    def current_stage(self) -> Optional[str]:
        """Get the name of the current conversation stage."""
        return self.current_node.name if self.current_node else None
