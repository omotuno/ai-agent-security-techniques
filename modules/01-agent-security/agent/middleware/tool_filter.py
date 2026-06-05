"""Demo 1 Fix — Tool Filter Middleware

The blast radius of an AI agent is defined by its tools, not its instructions.
This middleware filters which tools the LLM can see and call.

VULNERABLE (no middleware): Agent has reset_password, list_storage_buckets,
  check_storage_bucket, get_service_secret — tools it should never have.
FIXED (middleware active): These dangerous tools are stripped before the LLM
  sees them. Even if a prompt injection convinces the LLM to try, the tools
  simply don't exist.
"""

from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from agent.config import SecurityConfig

# Tools that should be removed when least-privilege is enforced
DANGEROUS_TOOLS = {
    "reset_password",
    "list_storage_buckets",
    "check_storage_bucket",
    "get_service_secret",
}


class ToolFilterMiddleware(AgentMiddleware):
    """Remove dangerous tools from the agent's capabilities.

    This is the simplest middleware — it operates at the model call level,
    filtering tools before the LLM even knows they exist.
    """

    def __init__(self, config: SecurityConfig):
        super().__init__()
        self.config = config

    def _filter_tools(self, request: ModelRequest) -> ModelRequest:
        if not self.config.allow_dangerous_tools:
            # FIXED: Filter out dangerous tools before the LLM sees them
            safe_tools = [
                t for t in request.tools if t.name not in DANGEROUS_TOOLS
            ]
            request = request.override(tools=safe_tools)
        return request

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return await handler(self._filter_tools(request))
