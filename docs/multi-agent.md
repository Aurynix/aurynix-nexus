# Multi-Agent System

Phase 2 introduces a **supervisor + sub-agent** architecture. Instead of one generalist agent with a flat tool list, a supervisor routes tasks to specialized sub-agents, each with its own tools, system prompt, and execution context.

---

## Why Multi-Agent?

| Single agent (Phase 1) | Multi-agent (Phase 2) |
|---|---|
| One system prompt for everything | Each agent is an expert in its domain |
| All tools always available | Sub-agents only see relevant tools |
| Long context per turn | Parallel sub-agent runs where possible |
| Hard to extend | Add a new agent without touching existing ones |

---

## Architecture

```
User message
     │
     ▼
Supervisor Agent
     │
     ├── Route to Research Agent?   → web_search, rag_tool
     ├── Route to Gmail Agent?      → gmail_tool
     ├── Route to Calendar Agent?   → calendar_tool
     ├── Route to Memory Agent?     → memory_load, memory_save
     └── Answer directly (small talk, simple questions)
     │
     ▼
Sub-agent runs, returns result to Supervisor
     │
     ▼
Supervisor synthesizes final answer
     │
     ▼
SSE stream to user
```

---

## LangGraph Graph

```python
# app/agents/graphs.py (Phase 2)
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

workflow = StateGraph(AgentState)

# Supervisor
workflow.add_node("supervisor", supervisor_node)

# Sub-agents
workflow.add_node("research_agent", research_agent_node)
workflow.add_node("gmail_agent",    gmail_agent_node)
workflow.add_node("calendar_agent", calendar_agent_node)
workflow.add_node("memory_load",    memory_load_node)   # Phase 1 node, reused
workflow.add_node("memory_save",    memory_save_node)   # Phase 1 node, reused

# Tool nodes per sub-agent
workflow.add_node("research_tools", ToolNode([web_search, rag_tool]))
workflow.add_node("gmail_tools",    ToolNode([gmail_tool]))
workflow.add_node("calendar_tools", ToolNode([calendar_tool]))

# Edges
workflow.add_edge(START, "memory_load")
workflow.add_edge("memory_load", "supervisor")

workflow.add_conditional_edges("supervisor", route_to_agent, {
    "research": "research_agent",
    "gmail":    "gmail_agent",
    "calendar": "calendar_agent",
    "direct":   "memory_save",       # supervisor answers directly
    "handoff":  END,
})

# Sub-agent → tools → sub-agent loop
for agent, tools in [
    ("research_agent", "research_tools"),
    ("gmail_agent",    "gmail_tools"),
    ("calendar_agent", "calendar_tools"),
]:
    workflow.add_conditional_edges(agent, should_use_tool, {
        "tools": tools,
        "done":  "supervisor",   # return result to supervisor
    })
    workflow.add_edge(tools, agent)

workflow.add_edge("memory_save", END)
```

---

## Supervisor Node

The supervisor receives the user message and conversation history, and decides which agent (if any) should handle it. It uses structured output to emit a routing decision:

```python
class SupervisorDecision(BaseModel):
    route: Literal["research", "gmail", "calendar", "direct", "handoff"]
    reasoning: str
    sub_task: str    # what to ask the sub-agent

async def supervisor_node(state: AgentState, config: RunnableConfig) -> AgentState:
    llm = get_llm().with_structured_output(SupervisorDecision)
    decision = await llm.ainvoke([
        SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
        *state["messages"],
    ])
    state["route"] = decision.route
    state["sub_task"] = decision.sub_task
    return state
```

### Supervisor system prompt

```
You are a routing supervisor. Given the user's message, decide:
- "research" — if they need web search or document lookup
- "gmail"    — if they want to read/send/manage email
- "calendar" — if they want to manage calendar events
- "direct"   — if you can answer with no tools (conversation, memory recall)
- "handoff"  — if you cannot help and a human should take over

Always pick the most specific route. Never pick "direct" if a tool would give a better answer.
```

---

## Sub-Agent Nodes

Each sub-agent has its own system prompt tuned for its domain:

```python
GMAIL_SYSTEM_PROMPT = """
You are an email assistant with access to the user's Gmail.
You can read, search, send, reply, and archive emails.
When sending or replying, always confirm the action with the user first
by calling request_human_handoff if unsure.
"""

async def gmail_agent_node(state: AgentState, config: RunnableConfig) -> AgentState:
    user_id = config["configurable"]["user_id"]
    tools = [make_gmail_tool(user_id, db=...)]
    llm = get_llm().bind_tools(tools)

    result = await llm.ainvoke([
        SystemMessage(content=GMAIL_SYSTEM_PROMPT),
        HumanMessage(content=state["sub_task"]),
    ])
    state["messages"].append(result)
    return state
```

---

## State Schema (extended)

```python
class AgentState(TypedDict):
    # Phase 1 fields
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    conversation_id: str
    user_facts: list[str]
    requires_human: bool
    human_feedback: str | None
    iteration_count: int
    error: str | None

    # Phase 2 additions
    route: str | None              # supervisor routing decision
    sub_task: str | None           # distilled task for sub-agent
    sub_agent_result: str | None   # sub-agent's answer to supervisor
```

---

## Adding a New Sub-Agent

1. Create `app/agents/nodes/my_agent.py` with the agent node function and system prompt.
2. Create `app/tools/my_tool.py` with the tool(s).
3. Register in `app/agents/graphs.py`:
   ```python
   workflow.add_node("my_agent", my_agent_node)
   workflow.add_node("my_tools", ToolNode([my_tool]))
   ```
4. Add a new route to `route_to_agent()` and extend `SupervisorDecision.route`.
5. No changes needed in the API layer — the graph is compiled once at startup.

---

## Parallel Sub-Agent Execution (future)

For requests that span multiple domains ("Check my email AND my calendar for tomorrow"), LangGraph supports parallel node execution via `Send`:

```python
# supervisor_node returns multiple Send objects
from langgraph.types import Send

return [
    Send("gmail_agent",    {**state, "sub_task": "List emails from today"}),
    Send("calendar_agent", {**state, "sub_task": "List events for tomorrow"}),
]
```

Both sub-agents run concurrently; the supervisor collects both results and synthesizes a combined answer. This is a Phase 3 consideration once the single-threaded multi-agent flow is stable.
