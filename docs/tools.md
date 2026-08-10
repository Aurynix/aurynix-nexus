# Tools — Gmail, Calendar, Web Search, Human Handoff

The LangGraph agent chooses tools at runtime based on the user's request. All tools follow the same factory pattern: they are instantiated per-request with the current `user_id` so they never share mutable state across users.

---

## Tool Architecture

```
app/tools/
    __init__.py
    registry.py        ← make_tools(user_id, db) → list[BaseTool]
    rag_tool.py        ← Phase 1: knowledge base search
    web_search.py      ← Tavily web search
    gmail.py           ← Gmail read/send/reply/archive
    calendar.py        ← Google Calendar CRUD
    human_handoff.py   ← LangGraph interrupt + ticket
```

### `make_tools(user_id, db)` — registry

```python
# app/tools/registry.py
async def make_tools(user_id: str, db: AsyncSession) -> list[BaseTool]:
    tools: list[BaseTool] = [
        make_rag_tool(user_id),
        make_web_search_tool(),
    ]
    # Only add OAuth tools if the user has connected Google
    if await has_oauth_token(user_id, "google", db):
        tools += [
            make_gmail_tool(user_id, db),
            make_calendar_tool(user_id, db),
        ]
    tools.append(make_human_handoff_tool(user_id))
    return tools
```

This replaces the hard-coded `[knowledge_base_search]` list from Phase 1. The agent node calls `make_tools()` at the start of each run.

---

## Web Search Tool

**File:** `app/tools/web_search.py`
**API:** [Tavily](https://tavily.com) — purpose-built search API for LLM agents
**Env var:** `TAVILY_API_KEY`

```python
@tool
async def web_search(query: str) -> str:
    """Search the web for current information, news, prices, documentation, or anything not in the knowledge base."""
    client = TavilyClient(api_key=settings.tavily_api_key)
    results = await asyncio.to_thread(
        client.search, query, max_results=5, search_depth="advanced"
    )
    return _format_results(results["results"])
```

**When the agent uses it:**
- "What is the current Bitcoin price?"
- "Find the FastAPI docs for background tasks."
- "What happened in the news today?"
- "What's the weather in Dubai?"

**Result format:**

```
[1] Title: FastAPI Background Tasks
    URL: https://fastapi.tiangolo.com/tutorial/background-tasks/
    ---
    Background tasks run after returning a response...

[2] ...
```

---

## Gmail Tool

**File:** `app/tools/gmail.py`
**API:** Google Gmail API v1
**Requires:** Google OAuth (scope: `gmail.modify`)

The Gmail tool is a single LangChain `StructuredTool` with a `GmailAction` enum so the LLM dispatches the right sub-operation:

```python
class GmailInput(BaseModel):
    action: Literal["read", "search", "send", "reply", "archive", "list"]
    query: str | None = None        # for search/list
    message_id: str | None = None   # for read/reply/archive
    to: str | None = None           # for send
    subject: str | None = None      # for send
    body: str | None = None         # for send/reply
    max_results: int = 10
```

### Actions

| Action | What it does | Required fields |
|---|---|---|
| `list` | Returns the N most recent inbox emails (sender, subject, date, snippet) | `max_results` |
| `search` | Gmail `q=` style search (e.g. `from:john subject:invoice`) | `query` |
| `read` | Returns full body of a specific message | `message_id` |
| `send` | Sends a new email | `to`, `subject`, `body` |
| `reply` | Replies to an existing thread | `message_id`, `body` |
| `archive` | Archives (removes from inbox) a message | `message_id` |

### Example conversation

```
User: "Reply to John's email about the invoice and thank him."

Agent:
  1. gmail(action="search", query="from:john subject:invoice")
     → finds message_id abc123
  2. gmail(action="read", message_id="abc123")
     → reads the email body
  3. gmail(action="reply", message_id="abc123",
           body="Hi John, thanks for sending the invoice...")
     → sends reply
  4. Responds: "Done — I've replied to John's invoice email."
```

### Safety guardrail

Before sending or replying, the agent emits a `tool_start` SSE event. If `GMAIL_REQUIRE_CONFIRMATION=true` (default in production), the frontend can show a "confirm send" UI before the action executes. The agent uses `interrupt()` to pause and wait for confirmation (see [Human Handoff](#human-handoff)).

---

## Google Calendar Tool

**File:** `app/tools/calendar.py`
**API:** Google Calendar API v3
**Requires:** Google OAuth (scope: `calendar`)

```python
class CalendarInput(BaseModel):
    action: Literal["list", "create", "get", "delete", "find_free"]
    calendar_id: str = "primary"
    event_id: str | None = None
    title: str | None = None
    start: str | None = None    # ISO 8601: "2026-08-05T14:00:00"
    end: str | None = None
    description: str | None = None
    attendees: list[str] = []   # email addresses
    time_min: str | None = None # for list/find_free range
    time_max: str | None = None
    max_results: int = 10
```

### Actions

| Action | What it does |
|---|---|
| `list` | Returns upcoming events in a time range |
| `get` | Returns details of a specific event |
| `create` | Creates a new event, optionally with attendees |
| `delete` | Deletes an event by ID |
| `find_free` | Returns free time slots in a given range |

### Example conversation

```
User: "Book a meeting with Sarah tomorrow at 2 PM for an hour."

Agent:
  1. calendar(action="find_free", time_min="tomorrow 00:00", time_max="tomorrow 23:59")
     → confirms 2 PM is free
  2. calendar(action="create",
              title="Meeting with Sarah",
              start="2026-08-03T14:00:00",
              end="2026-08-03T15:00:00",
              attendees=["sarah@example.com"])
     → event created, returns event_id
  3. Responds: "Done — I've booked 'Meeting with Sarah' tomorrow at 2–3 PM."
```

---

## Human Handoff Tool

**File:** `app/tools/human_handoff.py`
**Mechanism:** LangGraph `interrupt()`

Used when the agent cannot resolve a request confidently or when the task requires explicit human approval (e.g., sending an email, deleting a calendar event).

### How it works

```python
@tool
async def request_human_handoff(
    reason: str,
    context: str,
    urgency: Literal["low", "medium", "high"] = "medium",
) -> str:
    """
    Pause and request a human to take over or approve this action.
    Use when: confidence is low, the action is irreversible, or the user
    explicitly asks for a human agent.
    """
    interrupt({
        "type": "handoff",
        "reason": reason,
        "context": context,
        "urgency": urgency,
    })
    # Execution resumes here after human_feedback is provided
    return "Human has been notified. Awaiting their response."
```

### SSE event flow

```
client                   server (SSE stream)
  │                           │
  │  POST /chat/stream        │
  │ ─────────────────────────►│
  │                           │  agent runs...
  │◄── token: "Let me check..."
  │◄── tool_start: human_handoff
  │◄── event: { type: "handoff", reason: "...", urgency: "high" }
  │◄── done
  │
  │  (frontend shows handoff UI)
  │
  │  POST /chat/stream { human_feedback: "approved" }
  │ ─────────────────────────►│
  │                           │  graph resumes from interrupt
  │◄── token: "Great, proceeding..."
  │◄── done
```

### Handoff ticket

When `urgency = "high"` (or when `HANDOFF_WEBHOOK_URL` is set), Aurynix also POSTs a JSON payload to the configured webhook:

```json
{
  "type": "handoff_request",
  "user_id": "uuid",
  "conversation_id": "uuid",
  "reason": "User wants to send email to all clients — needs approval",
  "urgency": "high",
  "timestamp": "2026-08-01T10:00:00Z"
}
```

This integrates with Slack, PagerDuty, Linear, or any webhook-compatible system.

---

## Plugin Architecture

Adding a new tool requires only two steps:

**1. Create `app/tools/my_tool.py`:**
```python
from langchain_core.tools import tool

@tool
async def my_tool(input: str) -> str:
    """One-sentence description the LLM uses to decide when to call this."""
    ...
```

**2. Register in `app/tools/registry.py`:**
```python
from app.tools.my_tool import my_tool

async def make_tools(user_id, db):
    return [..., my_tool]
```

No changes needed in the agent graph, nodes, or router — LangGraph's `ToolNode` picks up new tools automatically.
