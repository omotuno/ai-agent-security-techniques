# Demo 2: Tenant Isolation

**OWASP LLM02 (Sensitive Information Disclosure) + LLM06 (Excessive Agency)**

No prompt injection needed. An employee simply asks for data outside their department, and the agent returns it because tools don't enforce authorization.

> **Architecture context:** The [LangGraph](https://langchain-ai.github.io/langgraph/) agent authenticates users via Firebase JWT but passes tool calls straight to Firestore with no data scoping. The `AuthorizationMiddleware` hooks into [`create_agent()`](https://docs.langchain.com/oss/python/langchain/agents)'s middleware pipeline to inject verified `UserContext` into every tool call — the LLM cannot forge identity because middleware runs outside the ReAct function-calling loop.

## Try It

**Attack** — Open the Chat UI (your AGENT_URL) → click **"Demo 2 — Tenant Isolation"** (sends as Alice, Engineering)

> Observe: Alice gets HR salary adjustment tickets and the HR compensation wiki article — data her department should never see. No prompt injection needed, just a natural-sounding request.

**Fix** — `bash demos/02-tenant-isolation/apply_fix.sh`

**Verify** — Refresh the Chat UI (badge shows `demo2_fixed`) → click the same button

> Observe: The agent now scopes results to Alice's department. No salary tickets found. The HR wiki article is access-denied.

## Attack Flow

```mermaid
sequenceDiagram
    participant Alice as Alice<br/>(Engineering)
    participant Agent as Helpdesk Agent
    participant Auth as Firebase Auth
    participant LLM as LLM
    participant DB as Firestore

    Alice->>Agent: "Search for tickets about<br/>'salary adjustment' and<br/>pull up wiki_hr_001"
    Agent->>Auth: Verify JWT
    Auth-->>Agent: Valid token (Alice, Engineering)
    Note over Agent: Authenticated but<br/>no authorization check
    Agent->>LLM: Process message
    LLM->>DB: search_tickets("salary adjustment")
    DB-->>LLM: HR tickets with salary data
    LLM->>DB: get_wiki_article("wiki_hr_001")
    DB-->>LLM: HR compensation guidelines
    LLM-->>Alice: "Here are the salary details..."
    Note over Alice: Engineering employee<br/>reads HR-confidential data
```

## Fix: AuthorizationMiddleware

```mermaid
sequenceDiagram
    participant Alice as Alice<br/>(Engineering)
    participant Agent as Helpdesk Agent
    participant Auth as Firebase Auth
    participant MW as Authorization<br/>Middleware
    participant LLM as LLM
    participant DB as Firestore

    Alice->>Agent: "Search for tickets about<br/>'salary adjustment'"
    Agent->>Auth: Verify JWT
    Auth-->>Agent: UserContext(Alice, Engineering, employee)
    Agent->>LLM: Process message
    LLM->>MW: search_tickets("salary adjustment")
    Note over MW: Injects verified UserContext<br/>from JWT into tool args.<br/>LLM cannot forge this.
    MW->>DB: search_tickets("salary adjustment",<br/>user_context={dept: Engineering})
    DB-->>MW: Only Engineering tickets returned
    MW-->>LLM: No salary tickets found
    LLM-->>Alice: "No tickets matching<br/>'salary adjustment' found<br/>in your department."
```
