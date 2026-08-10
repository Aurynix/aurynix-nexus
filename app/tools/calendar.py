"""Google Calendar tool — list, create, and delete events."""
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


class CalendarInput(BaseModel):
    action: Literal["list_events", "get_event", "create_event", "delete_event", "list_calendars"]
    calendar_id: str = "primary"
    event_id: str = ""
    summary: str = ""
    description: str = ""
    start: str = ""
    end: str = ""
    attendees: list[str] = []
    days_ahead: int = 7
    max_results: int = 10


def _build_calendar_service(credentials):
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _list_events(service, calendar_id: str, days_ahead: int, max_results: int) -> str:
    now = datetime.now(UTC)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = result.get("items", [])
    if not events:
        return f"No events in the next {days_ahead} days."

    lines = []
    for e in events:
        start = e.get("start", {})
        start_str = start.get("dateTime", start.get("date", "unknown"))
        lines.append(
            f"ID: {e['id']}\n"
            f"  Summary: {e.get('summary', '(no title)')}\n"
            f"  Start: {start_str}\n"
            f"  Location: {e.get('location', 'N/A')}"
        )
    return "\n\n".join(lines)


def _get_event(service, calendar_id: str, event_id: str) -> str:
    e = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    start = e.get("start", {})
    end = e.get("end", {})
    attendees = ", ".join(a.get("email", "") for a in e.get("attendees", []))
    return (
        f"Summary: {e.get('summary', '(no title)')}\n"
        f"Description: {e.get('description', 'N/A')}\n"
        f"Start: {start.get('dateTime', start.get('date', 'unknown'))}\n"
        f"End: {end.get('dateTime', end.get('date', 'unknown'))}\n"
        f"Location: {e.get('location', 'N/A')}\n"
        f"Attendees: {attendees or 'None'}"
    )


def _create_event(
    service, calendar_id: str, summary: str, description: str, start: str, end: str, attendees: list[str]
) -> str:
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
        "attendees": [{"email": a} for a in attendees],
    }
    created = service.events().insert(calendarId=calendar_id, body=body).execute()
    return f"Event created: {created.get('summary')} (ID: {created['id']})"


def _delete_event(service, calendar_id: str, event_id: str) -> str:
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    return f"Event {event_id} deleted."


def _list_calendars(service) -> str:
    result = service.calendarList().list().execute()
    calendars = result.get("items", [])
    return "\n".join(
        f"- {c.get('summary', '?')} (id: {c['id']})" for c in calendars
    ) or "No calendars."


def make_calendar_tool(user_id: str, db) -> BaseTool:
    """Factory that creates a per-user Google Calendar tool."""

    @tool(args_schema=CalendarInput)
    async def calendar(
        action: str,
        calendar_id: str = "primary",
        event_id: str = "",
        summary: str = "",
        description: str = "",
        start: str = "",
        end: str = "",
        attendees: list[str] = [],
        days_ahead: int = 7,
        max_results: int = 10,
    ) -> str:
        """
        Interact with the user's Google Calendar.
        Actions: list_events, get_event, create_event, delete_event, list_calendars.
        Requires the user to have connected their Google account via OAuth.
        """
        from sqlalchemy import select

        from app.core.google_auth import encrypted_to_credentials
        from app.models.oauth_token import OAuthToken

        result = await db.execute(
            select(OAuthToken).where(
                OAuthToken.user_id == user_id, OAuthToken.provider == "google"
            )
        )
        token_row = result.scalar_one_or_none()
        if not token_row:
            return "Google Calendar is not connected. Ask the user to connect their Google account first."

        credentials = encrypted_to_credentials(token_row.encrypted_token)

        def _run() -> str:
            service = _build_calendar_service(credentials)
            if action == "list_events":
                return _list_events(service, calendar_id, days_ahead, max_results)
            if action == "get_event":
                return _get_event(service, calendar_id, event_id)
            if action == "create_event":
                return _create_event(service, calendar_id, summary, description, start, end, attendees)
            if action == "delete_event":
                return _delete_event(service, calendar_id, event_id)
            if action == "list_calendars":
                return _list_calendars(service)
            return f"Unknown action: {action}"

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            logger.error("Calendar tool error", action=action, error=str(exc))
            return f"Calendar error: {exc}"

    return calendar
