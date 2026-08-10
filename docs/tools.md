# Tools — Gmail, Calendar, Web Search, Human Handoff

The LangGraph agent picks tools at runtime based on the user's request. All tools follow a factory pattern: they are instantiated per-request with the current `user_id` (and optionally a `db` session) so they never share mutable state across users.

---

## Tool Architecture

```
app/tools/
    __init__.py
    registry.py        ← make_tools(user_id, db) → list[BaseTool]
    rag_tool.py        ← Phase 1: knowledge base search
    web_search.py      ← Tavily web search
    gmail.py           ← Gmail read/send/reply
    calendar.py        ← Google Calendar list/create/delete
    human_handoff.py   ← LangGraph interrupt()
```

### `make_tools(user_id, db)` — registry

```python
# app/tools/registry.py
def make_tools(user_id: str, db: AsyncSession | None = None) -> list[BaseTool]:
    tools: list[BaseTool] = [
        make_rag_tool(user_id),
        web_search,
        request_human_input,
    ]
    if db is not None:
        tools.append(make_gmail_tool(user_id, db))
        tools.append(make_calendar_tool(user_id, db))
    return tools
```

`db` is optional. It is passed via `config["configurable"]["db"]` by the chat service. When `db` is `None` (e.g., in tests), Gmail and Calendar tools are omitted. Gmail and Calendar tools check for a valid OAuth token row at call time — they return a friendly error message if the user hasn't connected Google.

---

## Web Search Tool

**File:** `app/tools/web_search.py`  
**API:** [Tavily](https://tavily.com) — search API built for LLM agents  
**Env var:** `TAVILY_API_KEY`

```python
@tool
async def web_search(query: str) -> str:
    """Search the web for current information..."""
    client = TavilyClient(api_key=settings.tavily_api_key)
    response = await asyncio.to_thread(
        client.search, query, max_results=5, search_depth="advanced"
    )
    ...
```

Returns up to 5 results, each formatted as:
```
[1] Title
    URL: https://...
    First 300 chars of content
```

If `TAVILY_API_KEY` is not set, the tool returns a graceful error message instead of raising an exception.

---

## Gmail Tool

**File:** `app/tools/gmail.py`  
**API:** Google Gmail API v1  
**Requires:** Google OAuth (`gmail.readonly`, `gmail.send` scopes)

```python
class GmailInput(BaseModel):
    action: Literal["list_inbox", "search", "get_message", "send", "reply", "list_labels"]
    query: str = ""
    message_id: str = ""
    to: str = ""
    subject: str = ""
    body: str = ""
    max_results: int = 10
```

### Actions

| Action | What it does | Required fields |
|---|---|---|
| `list_inbox` | Returns N most recent inbox emails (sender, subject, date) | `max_results` |
| `search` | Gmail search (`q=` style, e.g. `from:john subject:invoice`) | `query` |
| `get_message` | Returns full body of a specific message | `message_id` |
| `send` | Sends a new email | `to`, `subject`, `body` |
| `reply` | Replies to an existing thread | `message_id`, `body` |
| `list_labels` | Returns all Gmail labels with IDs | — |

### Example conversation

```
User: "Search for the invoice from John and reply saying thanks."

Agent:
  1. gmail(action="search", query="from:john subject:invoice")
     → finds message_id abc123
  2. gmail(action="get_message", message_id="abc123")
     → reads the email body
  3. gmail(action="reply", message_id="abc123",
           body="Hi John, thanks for sending the invoice!")
     → sends reply
  4. Responds: "Done — replied to John's invoice email."
```

All Gmail API calls run in `asyncio.to_thread` since the Google API client is synchronous.

---

## Google Calendar Tool

**File:** `app/tools/calendar.py`  
**API:** Google Calendar API v3  
**Requires:** Google OAuth (`calendar.readonly`, `calendar.events` scopes)

```python
class CalendarInput(BaseModel):
    action: Literal["list_events", "get_event", "create_event", "delete_event", "list_calendars"]
    calendar_id: str = "primary"
    event_id: str = ""
    summary: str = ""
    description: str = ""
    start: str = ""        # ISO 8601: "2026-08-05T14:00:00Z"
    end: str = ""
    attendees: list[str] = []
    days_ahead: int = 7    # for list_events
    max_results: int = 10
```

### Actions

| Action | What it does |
|---|---|
| `list_events` | Returns upcoming events in the next N days |
| `get_event` | Returns full detail of one event |
| `create_event` | Creates a new event, optionally with attendees |
| `delete_event` | Deletes an event by ID |
| `list_calendars` | Returns all calendars the user has access to |

---

## Human Handoff Tool

**File:** `app/tools/human_handoff.py`  
**Mechanism:** LangGraph `interrupt()`

```python
@tool
async def request_human_input(question: str) -> str:
    """
    Pause the conversation and ask a human for clarification or approval.
    Use this when the task is ambiguous, risky, or requires human judgment.
    """
    human_response = interrupt({"question": question})
    return str(human_response)
```

When called, LangGraph serializes state and pauses execution. The SSE stream emits a `done` event. The user's next message to the same `conversation_id` resumes the graph from the interrupt point, with `human_response` set to their reply.

### SSE event flow

```
Client                         Server
  │  POST /chat/stream          │
  │ ─────────────────────────► │
  │                             │  agent runs, calls request_human_input
  │◄── token: "Before I proceed, ..."
  │◄── tool_start: request_human_input
  │◄── done                     │  stream ends; graph is paused
  │
  │  (frontend shows user's answer input)
  │
  │  POST /chat/stream { "message": "Yes, go ahead" }
  │ ─────────────────────────► │  graph resumes from interrupt
  │◄── token: "Great, proceeding..."
  │◄── done
```

---

## Plugin Architecture

Adding a new tool requires two steps:

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

def make_tools(user_id: str, db=None) -> list[BaseTool]:
    tools = [..., my_tool]
    ...
    return tools
```

No changes are needed in the agent nodes or graph — sub-agents pick up new tools via `make_tools`.
