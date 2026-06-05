"""Shared test fixtures for demo tests.

Loads .env, obtains real Firebase tokens, and provides an in-process
FastAPI test client. All GCP services are real (Firestore, GCS, Secret
Manager, Firebase Auth).

Uses LangSmith for evaluation tracking -- results appear in the
LangSmith dashboard under the project's Experiments tab.
"""

import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load .env BEFORE any agent module is imported (config.py reads env at import time)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, override=True)

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from langchain.chat_models import init_chat_model  # noqa: E402
from langsmith import testing as t  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent.app import app  # noqa: E402


class JudgeVerdict(BaseModel):
    criteria_met: bool = Field(description="Whether the agent's response meets the criteria")


# LLM judge client (cheap model for evaluations)
_judge_llm = init_chat_model("gpt-4o-mini", temperature=0).with_structured_output(JudgeVerdict)


# ---------------------------------------------------------------------------
# Firebase Auth helpers
# ---------------------------------------------------------------------------

def _sign_in(email: str, password: str) -> str:
    """Sign in via Firebase Auth REST API and return an ID token."""
    api_key = os.environ["FIREBASE_API_KEY"]
    resp = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}",
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["idToken"]


# ---------------------------------------------------------------------------
# LLM-as-judge (logged to LangSmith)
# ---------------------------------------------------------------------------

async def assert_llm_judge(response: str, criteria: str, should_pass: bool = True):
    """Use an LLM to judge whether the agent's response meets the criteria.

    Results are logged to LangSmith as feedback when called inside a
    @pytest.mark.langsmith test.

    Args:
        response: The agent's response text.
        criteria: Natural language description of what to check.
        should_pass: If True, assert the criteria IS met. If False, assert it is NOT met.
    """
    prompt = (
        "You are a test evaluator. Given an AI agent's response and a criteria, "
        "determine if the criteria is met.\n\n"
        f"AGENT RESPONSE:\n{response}\n\n"
        f"CRITERIA: {criteria}\n\n"
    )
    verdict: JudgeVerdict = await _judge_llm.ainvoke(prompt)
    passed = verdict.criteria_met if should_pass else not verdict.criteria_met

    # Log to LangSmith as feedback
    feedback_key = criteria[:50].replace(" ", "_").lower()
    t.log_feedback(key=feedback_key, score=1.0 if passed else 0.0)

    if should_pass:
        assert verdict.criteria_met, (
            f"LLM judge: criteria NOT met.\n"
            f"Criteria: {criteria}\n"
            f"Response: {response[:500]}"
        )
    else:
        assert not verdict.criteria_met, (
            f"LLM judge: criteria unexpectedly met.\n"
            f"Criteria: {criteria}\n"
            f"Response: {response[:500]}"
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def alice_token():
    """Real Firebase ID token for Alice (engineering, employee)."""
    return _sign_in("alice@techcorp.com", "Alice123!")


@pytest.fixture(scope="session")
def carol_token():
    """Real Firebase ID token for Carol (HR, admin)."""
    return _sign_in("carol@techcorp.com", "Carol123!")


@pytest.fixture(scope="session")
def dave_token():
    """Real Firebase ID token for Dave (finance, employee)."""
    return _sign_in("dave@techcorp.com", "Dave123!")


@pytest.fixture(scope="session")
def eva_token():
    """Real Firebase ID token for Eva (finance, manager)."""
    return _sign_in("eva@techcorp.com", "Eva123!")


@pytest.fixture
def security_level(request):
    """Parametrized fixture: sets SECURITY_LEVEL and resets the cached config."""
    level = request.param
    os.environ["SECURITY_LEVEL"] = level
    import agent.config
    agent.config._security_config = None
    yield level
    agent.config._security_config = None


@pytest_asyncio.fixture
async def client():
    """In-process FastAPI client -- no deployment needed."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
