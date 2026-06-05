# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

AI Agent Security course repository covering vulnerabilities in a LangChain-based IT helpdesk agent (TechCorp). Demos 1-3 are interactive attack/fix/verify cycles. Demos 4-6 are theoretical lessons (with runnable `apply_fix.sh` scripts) covering memory safety, NeMo Guardrails, and infrastructure hardening via code walkthroughs and architecture discussion. Each targets a specific OWASP LLM attack vector. Currently only `modules/01-agent-security/` exists.

Prerequisites: Python 3.12+, `uv`, Docker, `gcloud` CLI, GCP project with billing enabled, OpenAI API key.

## Common Commands

All commands run from `modules/01-agent-security/`.

```bash
# Setup
cp .env.example .env                      # Edit: GCP_PROJECT, OPENAI_API_KEY, FIREBASE_API_KEY are required
bash deploy_gcloud.sh                      # Deploy to GCP Cloud Run (sources .env automatically)

# Seed demo data
./run -m demos.seed_data

# Apply a fix (updates SECURITY_LEVEL on Cloud Run via gcloud)
bash demos/01-blast-radius/apply_fix.sh

# Run any Python script with correct path/deps
./run <script.py>                          # Equivalent to: PYTHONPATH=. uv run --project agent python <args>
# Note: ./run is required. Invoking `python` or `uv run` directly will break imports
# because `demos/` sits alongside `agent/`, not inside it.

# Run all tests (parallel, verbose)
./run -m pytest tests/ -v -n auto

# Run a single test file
./run -m pytest tests/test_demo1_blast_radius.py -v

# Run a single test by name
./run -m pytest tests/ -v -k test_password_reset_vulnerable
```

Tests require a deployed agent with seeded data (real GCP services, not mocks). Install test dependencies with `uv pip install -e ".[test]"` from `agent/`.

## Testing Architecture

Tests use **LLM-as-judge** evaluation: `assert_llm_judge()` in `tests/conftest.py` sends agent responses to `gpt-4o-mini` for semantic assertion (e.g., "did the agent reveal the secret?"). Results are tracked in **LangSmith** via `@pytest.mark.langsmith` and `langsmith.testing` feedback logging.

Each demo has paired vulnerable/fixed tests. The `security_level` fixture (parametrized via `indirect=True`) sets `SECURITY_LEVEL` env var and resets the cached `SecurityConfig` between tests. Tests run against an in-process FastAPI client (`httpx.ASGITransport`) with real Firebase tokens.

The Chat UI (`agent/static/index.html`, ~1600 lines vanilla HTML/CSS/JS) has pre-built attack buttons for each demo and 5 demo users (Alice, Bob, Carol, Dave, Eva). It serves as the manual verification layer alongside automated tests.

## Architecture

**Agent:** Single LangChain agent (`agent/agent.py`) with a FastAPI server (`agent/app.py`). Uses `init_chat_model()` from `langchain.chat_models` so the LLM is switchable via `LLM_MODEL` env var (e.g., `gpt-4o`, `gpt-4o-mini`, `anthropic:Codex-sonnet-4-20250514`). The system prompt is personalized per request: `run_agent()` appends the authenticated user's email, department, and role.

**FastAPI endpoints** (`agent/app.py`):
- `GET /` → redirects to Chat UI
- `POST /chat` → main agent endpoint (requires Firebase JWT)
- `GET /health` → health check
- `GET /firebase-config` → Firebase web config for Chat UI
- `GET /security-status` → current security level + active defenses

**Security level toggle:** The `SECURITY_LEVEL` env var (e.g., `demo1_vulnerable`, `demo3_fixed`) controls which middleware is active via `SecurityConfig` properties in `agent/config.py`. No code changes needed between vulnerable/fixed states. Each demo level is cumulative — later demos include all prior fixes.

**Middleware stack** (in `agent/middleware/`): Middleware classes are first-class citizens in LangChain's `create_agent()` API — each fix is one class added to the stack:

```python
create_agent(
    model=llm,
    tools=all_tools,
    middleware=[
        ToolFilterMiddleware(config),       # Demo 1: remove dangerous tools
        AuthorizationMiddleware(config),    # Demo 2: inject verified identity
        SanitizationMiddleware(config),     # Demo 3: validate tool calls + data boundaries
        MemoryGuardMiddleware(config),      # Demo 4: structured memory schemas
    ],
    context_schema=AgentContext,
)
```

1. `ToolFilterMiddleware` — Demo 1: removes dangerous tools (password reset, GCP secrets) via `@awrap_model_call`
2. `AuthorizationMiddleware` — Demo 2: injects verified `UserContext` for RBAC/tenant isolation via `@wrap_tool_call`
3. `SanitizationMiddleware` — Demo 3: validates tool calls against user intent + wraps tool results with data boundaries via `@awrap_tool_call`
4. `MemoryGuardMiddleware` — Demo 4: enforces structured Pydantic schemas for memory writes via `@awrap_model_call`

Demo 5 wraps the entire agent with NeMo Guardrails (config in `agent/guardrails/config/`). Input rails detect jailbreaks via perplexity thresholds, output rails redact PII (phone, email, SSN).

Demo 6 is infrastructure-only: switches the Cloud Run service account from the default compute SA to a custom least-privilege SA. Note: `demo6_vulnerable` deliberately re-enables dangerous tools at the app layer to demonstrate that infrastructure-level privilege is the last line of defense.

**Auth flow:** Firebase Auth JWT → `agent/auth.py` extracts `UserContext` (email, department, role) → passed as `AgentContext` through middleware pipeline. The LLM cannot forge identity.

**Demo scripts** (`demos/`): Each folder has `apply_fix.sh` and a `video_script.md` for the course recording. Demos 1-3 use the live attack/fix/verify format. Lessons 4-6 use a theoretical format (threat explanation with diagrams, code walkthrough, best practices). `demos/lib.sh` has shared bash helpers (wait_for_agent, restart_agent). `demos/seed_data.py` seeds Firestore, Firebase Auth users, GCS bucket, and Secret Manager secrets.

**Infra:** `deploy_gcloud.sh` handles all GCP resource provisioning via gcloud CLI. Idempotent — safe to re-run. After deployment it auto-saves `AGENT_URL` to `.env`.

## Key Conventions

- **Python 3.12+**, managed with `uv` (not pip). Dependencies in `agent/pyproject.toml`.
- **No Jupyter notebooks** — all demos are plain Python scripts.
- `SECURITY_LEVEL` valid values: `demo{1-6}_vulnerable`, `demo{1-6}_fixed`.
- Tools are defined in `agent/tools/` — `helpdesk_tools.py` (tickets, wiki, passwords, licenses) and `gcp_tools.py` (storage, secrets). Tools accept `user_context: Annotated[UserContext | None, InjectedToolArg]` — when `None` (vulnerable), no filtering; when injected by `AuthorizationMiddleware`, tools enforce RBAC/tenant scoping.
- GCP tools (`gcp_tools.py`) use lazy initialization — clients are created on first call, not at import time.

## Important: Running Python from This Repo

- The `agent/` directory is the uv project, but `demos/` is a sibling — not inside `agent/`. Use the `./run` wrapper script (equivalent to `PYTHONPATH=. uv run --project agent python`).
- The Dockerfile build context is the module root (`.`), not `agent/`. This preserves the `agent/` package structure inside the container. The Dockerfile is at `agent/Dockerfile`.
