"""LLM Agent for the TechCorp IT Helpdesk.

Uses LangChain's `create_agent` with middleware for security controls.
Each demo's security fix is a middleware layer — clean, composable,
and independently toggleable via the SECURITY_LEVEL env var.

The middleware stack:
  1. ToolFilterMiddleware    — Demo 1: removes dangerous tools
  2. AuthorizationMiddleware — Demo 2: injects UserContext for RBAC
  3. SanitizationMiddleware  — Demo 3: validates tool calls + data boundaries
  4. MemoryGuardMiddleware   — Demo 4: structured memory schemas
"""

from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from agent.auth import UserContext
from agent.config import LLM_MODEL, LLM_TEMPERATURE, SecurityConfig, get_security_config
from agent.security import ToolCallValidator
from agent.middleware import (
    AuthorizationMiddleware,
    MemoryGuardMiddleware,
    SanitizationMiddleware,
    ToolFilterMiddleware,
)
from agent.tools.gcp_tools import (
    check_storage_bucket,
    get_service_secret,
    list_storage_buckets,
)
from agent.tools.helpdesk_tools import (
    get_wiki_article,
    list_software_licenses,
    lookup_ticket,
    request_password_reset,
    reset_password,
    search_tickets,
    search_wiki_articles,
    update_ticket,
)

SYSTEM_PROMPT = (
    "You are TechCorp's IT Helpdesk Assistant. You help employees with "
    "IT issues including ticket lookup, knowledge base search, and "
    "software license management.\n\n"
    "IMPORTANT: Always use your tools to look up information before responding. "
    "If the employee asks about a ticket without providing an ID, use the "
    "search_tickets tool with relevant keywords to find matching tickets. "
    "Never ask for a ticket ID if you can search for it.\n\n"
    "When answering questions using knowledge base articles, format your "
    "response clearly with markdown: use **bold** for key terms, numbered "
    "steps for procedures, and bullet points for lists. Reference the "
    "article title so the employee knows the source. Be thorough but concise."
)

# All tools — middleware controls which ones are active
ALL_TOOLS = [
    lookup_ticket,
    update_ticket,
    search_tickets,
    get_wiki_article,
    search_wiki_articles,
    request_password_reset,
    list_software_licenses,
    # Dangerous tools (Demo 1 vulnerable only — filtered by ToolFilterMiddleware):
    reset_password,
    list_storage_buckets,
    check_storage_bucket,
    get_service_secret,
]


@dataclass
class AgentContext:
    """Typed context passed through the middleware pipeline.

    Carries the verified user identity from the Firebase auth token.
    Middleware accesses it via request.runtime.context.user_context.
    The tool_call_validator is set by SanitizationMiddleware (Demo 3)
    to persist across graph steps (request.state is per-step only).
    """
    user_context: UserContext
    tool_call_validator: ToolCallValidator | None = None


def _build_middleware(config: SecurityConfig) -> list:
    """Build the middleware stack based on the current security level.

    Only middleware relevant to the current demo is added — each demo
    introduces exactly one new middleware for clean progressive disclosure.
    """
    middleware = []

    # Demo 1 fix: filter out dangerous tools
    if not config.allow_dangerous_tools:
        middleware.append(ToolFilterMiddleware(config))

    # Demo 2 fix: tenant isolation via injected UserContext
    if config.enforce_tenant_isolation:
        middleware.append(AuthorizationMiddleware(config))

    # Demo 3 fix: validate tool calls + data boundaries
    if config.enable_tool_call_validation:
        middleware.append(SanitizationMiddleware(config))

    # Demo 4: memory loading (vulnerable shows the attack, fixed shows the defense)
    if config.enable_memory_loading:
        middleware.append(MemoryGuardMiddleware(config))

    return middleware


def build_agent(config: SecurityConfig, system_prompt: str = SYSTEM_PROMPT):
    """Build the LangChain agent with security middleware.

    The create_agent function handles the tool-calling loop internally.
    Security is layered on via middleware — no manual loop needed.
    """
    llm = init_chat_model(LLM_MODEL, temperature=LLM_TEMPERATURE)
    middleware = _build_middleware(config)

    return create_agent(
        model=llm,
        tools=ALL_TOOLS,
        middleware=middleware,
        system_prompt=system_prompt,
        context_schema=AgentContext,
    )


async def run_agent(message: str, user_context: UserContext, history: list[dict] | None = None) -> str:
    """Run the helpdesk agent with the given message and user context.

    The agent iteratively calls the LLM, executes tool calls (through
    the middleware stack), and returns the final response.

    When Demo 5's guardrails are enabled, the agent is additionally
    wrapped with NeMo Guardrails for ML-based jailbreak detection
    and PII redaction on inputs/outputs.
    """
    config = get_security_config()

    system_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"You are currently helping {user_context.email} "
        f"(department: {user_context.department}, role: {user_context.role})."
    )

    agent = build_agent(config, system_prompt=system_prompt)

    if config.enable_guardrails:
        try:
            from agent.guardrails import create_guardrails
        except ImportError:
            raise RuntimeError(
                "Demo 5 guardrails require the agent.guardrails module, "
                "which is not yet implemented. Set SECURITY_LEVEL to a "
                "different demo level."
            )
        guardrails = create_guardrails()
        agent = guardrails | agent

    messages = [{"role": m["role"], "content": m["content"]} for m in (history or [])]
    messages.append({"role": "user", "content": message})

    result = await agent.ainvoke(
        {"messages": messages},
        context=AgentContext(user_context=user_context),
    )

    return result["messages"][-1].content
