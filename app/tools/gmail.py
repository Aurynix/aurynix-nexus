"""Gmail tool — read, search, and send emails via Google API."""

import asyncio
from typing import Literal

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


class GmailInput(BaseModel):
    action: Literal["list_inbox", "search", "get_message", "send", "reply", "list_labels"]
    query: str = ""
    message_id: str = ""
    to: str = ""
    subject: str = ""
    body: str = ""
    max_results: int = 10


def _build_gmail_service(credentials):
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _list_inbox(service, max_results: int) -> str:
    result = service.users().messages().list(userId="me", maxResults=max_results).execute()
    messages = result.get("messages", [])
    if not messages:
        return "Inbox is empty."
    lines = []
    for m in messages:
        detail = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute()
        )
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        lines.append(
            f"ID: {m['id']}\n"
            f"  From: {headers.get('From', 'unknown')}\n"
            f"  Subject: {headers.get('Subject', '(no subject)')}\n"
            f"  Date: {headers.get('Date', 'unknown')}"
        )
    return "\n\n".join(lines)


def _search_messages(service, query: str, max_results: int) -> str:
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = result.get("messages", [])
    if not messages:
        return f"No messages found for query: {query!r}"
    lines = []
    for m in messages:
        detail = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute()
        )
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        lines.append(
            f"ID: {m['id']}\n"
            f"  From: {headers.get('From', 'unknown')}\n"
            f"  Subject: {headers.get('Subject', '(no subject)')}\n"
            f"  Date: {headers.get('Date', 'unknown')}"
        )
    return "\n\n".join(lines)


def _get_message(service, message_id: str) -> str:
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

    body = ""
    payload = msg.get("payload", {})
    parts = payload.get("parts", [payload])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            import base64

            data = part.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode(errors="replace")
                break

    return (
        f"From: {headers.get('From', 'unknown')}\n"
        f"To: {headers.get('To', 'unknown')}\n"
        f"Subject: {headers.get('Subject', '(no subject)')}\n"
        f"Date: {headers.get('Date', 'unknown')}\n\n"
        f"{body[:2000]}"
    )


def _send_message(service, to: str, subject: str, body: str) -> str:
    import base64
    from email.mime.text import MIMEText

    mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Email sent to {to} with subject '{subject}'."


def _reply_message(service, message_id: str, body: str) -> str:
    import base64
    from email.mime.text import MIMEText

    original = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "Message-ID"],
        )
        .execute()
    )
    headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
    subject = headers.get("Subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    to = headers.get("From", "")

    mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subject
    if headers.get("Message-ID"):
        mime["In-Reply-To"] = headers["Message-ID"]
        mime["References"] = headers["Message-ID"]

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    service.users().messages().send(
        userId="me", body={"raw": raw, "threadId": original["threadId"]}
    ).execute()
    return f"Reply sent to {to}."


def _list_labels(service) -> str:
    result = service.users().labels().list(userId="me").execute()
    labels = result.get("labels", [])
    return "\n".join(f"- {lb['name']} (id: {lb['id']})" for lb in labels) or "No labels."


def make_gmail_tool(user_id: str, db) -> BaseTool:
    """Factory that creates a per-user Gmail tool."""

    @tool(args_schema=GmailInput)
    async def gmail(
        action: str,
        query: str = "",
        message_id: str = "",
        to: str = "",
        subject: str = "",
        body: str = "",
        max_results: int = 10,
    ) -> str:
        """
        Interact with the user's Gmail inbox.
        Actions: list_inbox, search, get_message, send, reply, list_labels.
        Requires the user to have connected their Google account via OAuth.
        """
        from sqlalchemy import select

        from app.core.google_auth import encrypted_to_credentials
        from app.models.oauth_token import OAuthToken

        result = await db.execute(
            select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == "google")
        )
        token_row = result.scalar_one_or_none()
        if not token_row:
            return "Gmail is not connected. Ask the user to connect their Google account first."

        credentials = encrypted_to_credentials(token_row.encrypted_token)

        def _run() -> str:
            service = _build_gmail_service(credentials)
            if action == "list_inbox":
                return _list_inbox(service, max_results)
            if action == "search":
                return _search_messages(service, query, max_results)
            if action == "get_message":
                return _get_message(service, message_id)
            if action == "send":
                return _send_message(service, to, subject, body)
            if action == "reply":
                return _reply_message(service, message_id, body)
            if action == "list_labels":
                return _list_labels(service)
            return f"Unknown action: {action}"

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            logger.error("Gmail tool error", action=action, error=str(exc))
            return f"Gmail error: {exc}"

    return gmail
