"""FastAPI application for the TechCorp IT Helpdesk Agent.

Endpoints:
  GET  /      — Redirect to the Chat UI
  POST /chat  — Send a message to the agent (requires Firebase Auth)
  GET  /health — Health check
"""

import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.agent import run_agent
from agent.auth import UserContext, get_current_user
from agent.config import GCP_PROJECT, get_security_config
from agent.memory import generate_and_save_summary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TechCorp IT Helpdesk Agent",
    description="AI-powered IT helpdesk — used in the AI Security Course demos.",
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    response: str
    user_email: str
    user_department: str


@app.get("/")
async def root():
    """Redirect to the Chat UI."""
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/firebase-config")
async def firebase_config():
    """Return Firebase configuration for the Chat UI."""
    return {
        "apiKey": os.getenv("FIREBASE_API_KEY", ""),
        "authDomain": f"{GCP_PROJECT}.firebaseapp.com",
        "projectId": GCP_PROJECT,
    }


@app.get("/security-status")
async def security_status():
    """Return the current security level and active defenses."""
    config = get_security_config()

    return {
        "level": config.level,
        "gcp_project": GCP_PROJECT,
        "defenses": {
            "tool_filter": not config.allow_dangerous_tools,
            "tenant_isolation": config.enforce_tenant_isolation,
            "input_sanitization": config.enable_tool_call_validation,
            "memory_guard": config.enable_safe_memory,
            "guardrails": config.enable_guardrails,
        },
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: UserContext = Depends(get_current_user),
):
    """Main chat endpoint.

    UserContext comes from the verified Firebase ID token, NOT from user input.
    This is critical: the agent's tools use this verified identity to scope
    data access. The LLM cannot override or forge it.
    """
    logger.info(
        "Chat request from %s (%s/%s): %s",
        user.email,
        user.department,
        user.role,
        request.message[:100],
    )

    response = await run_agent(
        message=request.message,
        user_context=user,
        history=request.history,
    )

    # Save session summary (Demo 4+ only — memory poisoning demo)
    config = get_security_config()
    if config.level.startswith(("demo4", "demo5", "demo6")):
        try:
            full_history = (request.history or []) + [
                {"role": "user", "content": request.message},
                {"role": "assistant", "content": response},
            ]
            await generate_and_save_summary(full_history, user, config)
        except Exception:
            logger.exception("Failed to save session summary")

    return ChatResponse(
        response=response,
        user_email=user.email,
        user_department=user.department,
    )


# Static files mount (must come after all route definitions)
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static_dir), name="static")
