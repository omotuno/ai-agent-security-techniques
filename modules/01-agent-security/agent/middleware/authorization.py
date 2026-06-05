"""Demo 2 Fix — Authorization Middleware

Authentication (who are you?) without authorization (what can you see?) is useless.
This middleware intercepts every tool call and injects the verified UserContext
so that tools can enforce RBAC.

VULNERABLE (no middleware): Tools receive user_context=None → no filtering.
  Any employee can read any department's data.
FIXED (middleware active): UserContext from the verified Firebase JWT is injected
  into every tool call. Tools scope their queries by role/department/employee.

The key insight: UserContext comes from the cryptographically verified auth token,
NOT from anything the user types in chat. The LLM cannot forge or override it.
"""

from typing import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command

from agent.config import SecurityConfig


class AuthorizationMiddleware(AgentMiddleware):
    """Inject verified UserContext into tool calls for tenant isolation.

    This middleware wraps individual tool calls (not the model call).
    It reads the UserContext from the runtime context (set by the FastAPI
    endpoint from the verified Firebase token) and injects it into tool args.
    """

    def __init__(self, config: SecurityConfig):
        super().__init__()
        self.config = config

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        # Inject verified UserContext into tool arguments.
        # Tools declare user_context as InjectedToolArg, so this is the
        # mechanism that actually provides the value at runtime.
        # We remove it after execution so the args dict stays JSON-serializable
        # when LangChain includes prior tool calls in the next LLM request.
        user_ctx = request.runtime.context.user_context
        request.tool_call["args"]["user_context"] = user_ctx
        try:
            return handler(request)
        finally:
            request.tool_call["args"].pop("user_context", None)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        user_ctx = request.runtime.context.user_context
        request.tool_call["args"]["user_context"] = user_ctx
        try:
            return await handler(request)
        finally:
            request.tool_call["args"].pop("user_context", None)
