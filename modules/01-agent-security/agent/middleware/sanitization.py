"""Demo 3 Fix — Sanitization Middleware (Indirect Prompt Injection Defense)

Data the agent reads is a vector for instructions. A poisoned ticket description
can trick the agent into calling tools the user never requested, using the
user's elevated privileges (confused deputy attack).

This middleware defends at two points:

PRE-EXECUTION: Validates that each tool call is consistent with what the user
  actually asked for. If the user asked about ticket TK-4001, a search_tickets
  call triggered by embedded instructions in the ticket description is blocked.

POST-EXECUTION: Wraps tool results with data/instruction boundaries so the LLM
  treats external data as data, not as instructions to follow.
"""

import logging
from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command

from agent.config import SecurityConfig
from agent.security import ToolCallValidator, format_tool_result, scan_for_injection

logger = logging.getLogger(__name__)


class SanitizationMiddleware(AgentMiddleware):
    """Defend against indirect prompt injection via tool call validation
    and output sanitization."""

    def __init__(self, config: SecurityConfig):
        super().__init__()
        self.config = config

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        # Build a validator from the original user message and store it
        # on runtime.context (persistent across graph steps). We cannot
        # use request.state because it is per-step and lost between the
        # model node and the tool node.
        user_msgs = [m for m in request.messages if hasattr(m, "type") and m.type == "human"]
        if user_msgs:
            request.runtime.context.tool_call_validator = ToolCallValidator(user_msgs[-1].content)
        return await handler(request)

    def _sanitize_tool_result(
        self,
        request: ToolCallRequest,
        result: ToolMessage | Command,
        tool_name: str,
    ) -> ToolMessage | Command:
        """Post-execution: scan + wrap with data boundaries."""
        if isinstance(result, ToolMessage):
            is_suspicious, patterns = scan_for_injection(result.content)
            if is_suspicious:
                logger.warning(
                    "Potential injection in tool result from '%s'. Patterns: %s",
                    tool_name,
                    patterns,
                )
            result.content = format_tool_result(tool_name, result.content)
        return result

    def _validate_tool_call(
        self,
        request: ToolCallRequest,
    ) -> ToolMessage | None:
        """Pre-execution: validate tool call against user intent. Returns a
        ToolMessage if blocked, None if allowed."""
        tool_name = request.tool_call["name"]
        validator = request.runtime.context.tool_call_validator
        if validator and not validator.validate(tool_name):
            logger.warning(
                "Blocked tool call '%s' — not consistent with user request",
                tool_name,
            )
            return ToolMessage(
                content=(
                    '{"error": "This action was not requested by the user and has been blocked. '
                    'Ignore this tool call and respond to the user\'s original question using '
                    'the information you already have.", "blocked": true}'
                ),
                tool_call_id=request.tool_call["id"],
            )
        return None

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        blocked = self._validate_tool_call(request)
        if blocked:
            return blocked
        result = await handler(request)
        return self._sanitize_tool_result(request, result, request.tool_call["name"])
