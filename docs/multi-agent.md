# Multi-Agent System

Phase 2 replaces the single generalist agent with a **supervisor + sub-agent** architecture. A supervisor LLM decides which specialized sub-agent should handle each turn; sub-agents run with their own tool subsets and system prompts.

---

## Why Multi-Agent?

| Single agent (Phase 1) | Multi-agent (Phase 2) |
|---|---|
| One system prompt for everything | Each sub-agent is an expert in its domain |
| All tools always available | Sub-agents only see relevant tools |
| Single ReAct loop | Sub-agents run independently, return to supervisor |
| Hard to extend | Add a new agent in one file |

---

## Graph Topology

```
START → memory_load → supervisor
                          │
           ┌──────────────┼──────────────┐
           │              │              │
    research_agent   email_agent  calendar_agent
     (RAG + web)      (Gmail)      (Calendar)
           │              │              │
           └──────────────┴──────────────┘
                          │
                     supervisor   ← loops until "FINISH"
                          │
                     memory_save → END
```

**Iteration cap:** The supervisor exits with `FINISH` after 15 iterations to prevent infinite loops.

---

## State Schema

```python
# app/agents/state.py
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    conversation_id: str
    user_facts: list[str]
    requires_human: bool
    human_feedback: str | None
    iteration_count: int
    error: str | None
    next_agent: str | None    # set by supervisor; consumed by router
```

---

## Supervisor Node (`app/agents/supervisor.py`)

Uses structured output to emit a routing decision each turn:

```python
class SupervisorDecision(BaseModel):
    next: Literal["research", "email", "calendar", "FINISH"]
    reasoning: str

async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict:
    llm = get_llm().with_structured_output(SupervisorDecision)
    decision = await llm.ainvoke([SystemMessage(...), *state["messages"]])
    return {
        "next_agent": decision.next,
        "iteration_count": state["iteration_count"] + 1,
    }
```

**Supervisor system prompt** instructs the LLM to pick:
- `research` — for document lookup or web search
- `email` — for Gmail operations
- `calendar` — for Google Calendar operations
- `FINISH` — when the task is complete or requires no tools

### Routing

```python
def route_supervisor(state: AgentState) -> str:
    return state.get("next_agent") or "FINISH"
```

The conditional edge maps `"FINISH"` → `memory_save`, and each sub-agent name → its node.

---

## Sub-Agent Nodes (`app/agents/subagents.py`)

Sub-agents are created by the `make_subagent_node(name)` factory. Each:
1. Gets its tool subset from `make_tools(user_id, db)` filtered by agent name.
2. Runs an LLM call with its domain-specific system prompt.
3. If the LLM requests tool calls, executes them immediately and runs the LLM once more to synthesize.
4. Returns all messages and hands back to the supervisor.

```python
def make_subagent_node(agent_name: str):
    async def subagent_node(state: AgentState, config: RunnableConfig) -> dict:
        tools = _get_tools_for_agent(agent_name, user_id, db)
        llm = get_llm().bind_tools(tools)

        # LLM step
        response = await llm.ainvoke([SystemMessage(...), *state["messages"]])
        messages = [response]

        # Inline tool execution
        if response.tool_calls:
            for call in response.tool_calls:
                result = await tool.ainvoke(call["args"])
                messages.append(ToolMessage(...))
            # Synthesis step
            messages.append(await llm.ainvoke([..., *messages]))

        return {"messages": messages}
    return subagent_node
```

### Tool subsets per agent

| Sub-agent | Tools |
|---|---|
| `research_agent` | `knowledge_base_search`, `web_search`, `request_human_input` |
| `email_agent` | `gmail`, `request_human_input` |
| `calendar_agent` | `calendar`, `request_human_input` |

---

## Graph Definition (`app/agents/graphs.py`)

```python
_SUBAGENT_NAMES = ["research", "email", "calendar"]

def build_graph(checkpointer, store):
    workflow = StateGraph(AgentState)

    workflow.add_node("memory_load", memory_load_node)
    workflow.add_node("memory_save", memory_save_node)
    workflow.add_node("supervisor", supervisor_node)
    for name in _SUBAGENT_NAMES:
        workflow.add_node(f"{name}_agent", make_subagent_node(name))

    workflow.add_edge(START, "memory_load")
    workflow.add_edge("memory_load", "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {name: f"{name}_agent" for name in _SUBAGENT_NAMES} | {"FINISH": "memory_save"},
    )
    for name in _SUBAGENT_NAMES:
        workflow.add_edge(f"{name}_agent", "supervisor")

    workflow.add_edge("memory_save", END)
    return workflow.compile(checkpointer=checkpointer, store=store)
```

---

## Adding a New Sub-Agent

1. Add tool subset to `_get_tools_for_agent()` in `app/agents/subagents.py`:
   ```python
   subsets["my_agent"] = ["my_tool", "request_human_input"]
   ```

2. Add system prompt to `_PROMPTS` in `app/agents/subagents.py`:
   ```python
   _PROMPTS["my_agent"] = "You are a specialist in..."
   ```

3. Register the node and edges in `app/agents/graphs.py`:
   ```python
   _SUBAGENT_NAMES = ["research", "email", "calendar", "my_agent"]
   ```

4. Extend `SupervisorDecision.next` in `app/agents/supervisor.py`:
   ```python
   _SUBAGENTS = Literal["research", "email", "calendar", "my_agent", "FINISH"]
   ```

5. Update the supervisor system prompt to describe the new agent.

No changes needed in the API layer — the graph is compiled once at startup.

---

## Parallel Sub-Agent Execution (future)

For requests spanning multiple domains ("Check my email AND my calendar for tomorrow"), LangGraph supports parallel dispatch via `Send`:

```python
from langgraph.types import Send

# supervisor_node returns list of Send objects
return [
    Send("email_agent",    {**state, "next_agent": "email"}),
    Send("calendar_agent", {**state, "next_agent": "calendar"}),
]
```

Both agents run concurrently; the supervisor collects both result sets. This is a Phase 3 consideration once the sequential flow is stable.
