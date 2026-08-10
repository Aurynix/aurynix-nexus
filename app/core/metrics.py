"""Prometheus metrics definitions and /metrics endpoint."""
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import Response

# ── Counters ──────────────────────────────────────────────────────────────────

chat_requests_total = Counter(
    "aurynix_chat_requests_total",
    "Total number of chat stream requests",
    ["status"],
)

auth_requests_total = Counter(
    "aurynix_auth_requests_total",
    "Total number of auth requests",
    ["endpoint", "status"],
)

document_ingestions_total = Counter(
    "aurynix_document_ingestions_total",
    "Total document ingest jobs",
    ["status"],
)

tool_calls_total = Counter(
    "aurynix_tool_calls_total",
    "Total tool invocations by name",
    ["tool_name"],
)

rate_limit_rejections_total = Counter(
    "aurynix_rate_limit_rejections_total",
    "Requests rejected by rate limiting",
    ["group"],
)

# ── Histograms ────────────────────────────────────────────────────────────────

chat_latency_seconds = Histogram(
    "aurynix_chat_latency_seconds",
    "Time to first token in a chat stream",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

ingest_duration_seconds = Histogram(
    "aurynix_ingest_duration_seconds",
    "Document ingestion wall-clock time",
    buckets=[1.0, 5.0, 15.0, 30.0, 60.0, 120.0],
)

# ── Gauges ────────────────────────────────────────────────────────────────────

active_connections = Gauge(
    "aurynix_active_sse_connections",
    "Number of currently open SSE streaming connections",
)


async def metrics_endpoint(request: Request) -> Response:
    """FastAPI route handler that exposes Prometheus metrics."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
