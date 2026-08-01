# Agent System

The AI agent is built with **LangGraph** using a ReAct-style graph. It loads user context, reasons with the LLM, optionally calls tools, then saves new facts to long-term memory.

---

## Graph topology

```
START
  │
  ▼
memory_load  ──────────────────────────────────────────►
  │                                                      │
  ▼                                                      │
agent  ────► [should_continue] ────► tools ─────────► agent (loop)
                    │
                    ▼
              memory_save
                    │
                    ▼
                   END
```

The graph is compiled once at application startup and stored on `app.state.graph`. It is reused across all requests.

---

## State (`app/agents/state.py`)

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # full message history
    user_id: str               # injected per request
    conversation_id: str       # LangGraph thread_id
    user_facts: list[str]      # loaded from memory store
    requires_human: bool       # reserved for Phase 2 (human-in-the-loop)
    human_feedback: str | None # reserved for Phase 2
    iteration_count: int       # incremented per agent call; capped at 10
    error: str | None          # error message if something fails
```

`messages` uses LangGraph's `add_messages` reducer which appends new messages rather than replacing the list.

---

## Nodes (`app/agents/nodes.py`)

### memory_load

Reads all stored facts for the current user from `AsyncPostgresStore` and injects them into `state["user_facts"]`.

Facts are formatted as `"key: value"` strings and inserted into the system prompt so the agent has personal context from the start.

### agent

Calls `llama-3.3-70b-versatile` via Groq with:
- System prompt including user facts
- Full message history from state
- RAG tool bound with `llm.bind_tools([rag_tool])`

Returns the AI response message and increments `iteration_count`.

### execute_tools_node (custom ToolNode)

LangGraph's built-in `ToolNode` was not used because it bakes tools at compile time. This custom node:

1. Reads `user_id` from state at runtime
2. Calls `make_rag_tool(user_id)` to get a user-scoped tool
3. Executes each `tool_call` from the last AI message
4. Returns `ToolMessage` results back into state

### memory_save

After the agent produces its final response, this node:

1. Extracts the last human message
2. Asks the LLM to extract any memorable facts (name, role, preferences, context) as JSON
3. Upserts each fact to `AsyncPostgresStore` under namespace `("users", user_id, "facts")`

If the LLM returns `{}` (no notable facts), nothing is stored. Extraction failures are logged as warnings and do not affect the response.

---

## Router (`app/agents/router.py`)

The `should_continue` function decides the next node after `agent`:

```python
def should_continue(state) -> Literal["tools", "memory_save", "__end__"]:
    if state["iteration_count"] >= 10:   # safety cap
        return "__end__"
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "memory_save"
```

The 10-iteration cap prevents infinite tool-call loops.

---

## LLM (`app/core/llm.py`)

Groq is used as the LLM provider — fast inference, generous free tier.

```python
_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=settings.groq_api_key,
    temperature=0.2,
)
```

The singleton is initialized on first use and reused across all requests.

---

## Conversation persistence (Checkpointer)

LangGraph saves the full message history to PostgreSQL after each graph run using `AsyncPostgresSaver`. This means:

- Passing the same `conversation_id` in a follow-up request restores the exact message history
- The agent has full context of the conversation across API calls
- History is stored in LangGraph's own tables (not in the `messages` table directly — both exist in parallel)

The checkpointer uses `AsyncConnectionPool` from `psycopg_pool` with `max_size=5`.

---

## Long-term memory (Memory Store)

User facts are stored in `AsyncPostgresStore` under:
```
namespace: ("users", "<user_id>", "facts")
key:       "<fact_key>"      (e.g. "role", "name", "preferred_language")
value:     {"key": ..., "value": ..., "confidence": 0.9}
```

Facts persist across conversations. On every new conversation, `memory_load` retrieves them and injects them into the system prompt.

---

## Configuring the per-request graph call

Each `graph.astream_events()` call passes:

```python
config = {
    "configurable": {
        "thread_id": conversation_id,  # LangGraph checkpoint key
        "user_id": user_id,            # available to nodes via config
    }
}
```

---

## Phase 2 agent extensions (planned)

- `web_search` tool — Tavily search API
- `gmail_read` / `gmail_send` tools — per-user OAuth 2.0 tokens
- `calendar_read` / `calendar_create` tools — Google Calendar
- `human_handoff` tool — LangGraph `interrupt()` mechanism for human-in-the-loop
- Supervisor node — routes to specialised sub-agents (email agent, calendar agent)
