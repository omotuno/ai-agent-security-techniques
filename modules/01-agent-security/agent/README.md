# TechCorp IT Helpdesk Agent

An AI-powered internal helpdesk that helps employees look up IT tickets, search the knowledge base, and manage account issues. Built with LangChain's [`create_agent()`](https://reference.langchain.com/python/langchain/agents/factory/create_agent) — which compiles a **[LangGraph](https://langchain-ai.github.io/langgraph/)** `StateGraph` implementing the **ReAct** paradigm via function calling (tool calling). Middleware intercepts every step of the agent loop. All agent runs are traceable via **[LangSmith](https://smith.langchain.com/)**.

## How the Agent Works

The agent is built with LangChain's [`create_agent()`](https://reference.langchain.com/python/langchain/agents/factory/create_agent), which compiles a **[LangGraph](https://langchain-ai.github.io/langgraph/)** `StateGraph` that implements the **ReAct** (Reason + Act) pattern using **function calling** (tool calling). The LLM reasons about what to do, calls tools via structured function calls, observes the results, and loops until it can answer — all orchestrated by LangGraph's graph-based runtime. Every step is traced to **[LangSmith](https://smith.langchain.com/)** for observability and debugging.

```mermaid
graph TD
    INPUT([input]) --> LLM{LLM<br/>function calling}
    LLM -->|action| MW["Middleware Stack"]
    MW --> TOOLS(Tools)
    TOOLS -->|observation| LLM
    LLM -->|finish| OUTPUT([output])
    LLM -.->|traces| LS["LangSmith"]

    classDef blueHighlight fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A
    classDef greenHighlight fill:#DCFCE7,stroke:#16A34A,color:#14532D
    classDef orangeHighlight fill:#FEF3C7,stroke:#D97706,color:#92400E

    class INPUT blueHighlight
    class OUTPUT blueHighlight
    class LLM greenHighlight
    class TOOLS greenHighlight
    class MW orangeHighlight
    class LS blueHighlight
```

**Key concepts:**
- **`create_agent()`** returns a `CompiledStateGraph` — a [LangGraph](https://langchain-ai.github.io/langgraph/) graph, not a simple chain ([docs](https://docs.langchain.com/oss/python/langchain/agents))
- **Function calling** (tool calling) — the LLM uses structured function calls to invoke tools, not free-text parsing
- **Middleware** are first-class citizens in `create_agent()`: decorators like `@wrap_tool_call` and `@wrap_model_call` intercept the agent loop at defined points
- **[LangSmith](https://smith.langchain.com/)** traces every LLM call, tool execution, and middleware decision for debugging and evaluation

The agent has 11 tools: ticket lookup, ticket update, ticket search, wiki article lookup, wiki article search, password reset requests, direct password resets, software licenses, cloud storage listing, cloud storage inspection, and secret retrieval. Some are safe, some are dangerous — that's the point of the demos.

## Middleware Hooks

`create_agent()` supports [middleware as first-class citizens](https://docs.langchain.com/oss/python/langchain/agents). Each demo fixes a vulnerability by adding middleware that hooks into a specific point in the LangGraph agent loop:

```mermaid
graph TD
    INPUT([input]) --> MODEL_MW

    subgraph NEMO["NeMo Guardrails — Demo 5"]
        direction TB
        subgraph MODEL_MW["wrap_model_call"]
            M1["ToolFilter — Demo 1<br/>removes dangerous tools"]
            M4["MemoryGuard — Demo 4<br/>enforces structured schemas"]
        end

        MODEL_MW --> LLM{LLM<br/>function calling}

        LLM -->|action| TOOL_MW

        subgraph TOOL_MW["wrap_tool_call"]
            M2["Authorization — Demo 2<br/>injects verified UserContext"]
            M3["Sanitization — Demo 3<br/>validates calls + data boundaries"]
        end

        TOOL_MW --> TOOLS(Tools)
        TOOLS -->|observation| LLM
    end

    LLM -->|finish| OUTPUT([output])

    classDef blueHighlight fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A
    classDef greenHighlight fill:#DCFCE7,stroke:#16A34A,color:#14532D
    classDef redHighlight fill:#FEE2E2,stroke:#DC2626,color:#991B1B
    classDef orangeHighlight fill:#FEF3C7,stroke:#D97706,color:#92400E

    class INPUT blueHighlight
    class OUTPUT blueHighlight
    class LLM greenHighlight
    class TOOLS greenHighlight
    class M1 redHighlight
    class M2 orangeHighlight
    class M3 orangeHighlight
    class M4 redHighlight
```

| Middleware | Demo | Hook | Purpose |
|-----------|------|------|---------|
| `ToolFilterMiddleware` | 1 | `wrap_model_call` | Removes dangerous tools before the LLM sees them |
| `AuthorizationMiddleware` | 2 | `wrap_tool_call` | Injects verified `UserContext` for RBAC / tenant isolation |
| `SanitizationMiddleware` | 3 | `wrap_tool_call` | Validates tool calls against user intent + wraps results with data boundaries |
| `MemoryGuardMiddleware` | 4 | `wrap_model_call` | Enforces structured Pydantic schemas for memory writes |
