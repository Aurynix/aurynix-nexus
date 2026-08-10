# Observability

Aurynix exports metrics, distributed traces, and error events so you can monitor production without reading raw log files.

---

## Stack

| Concern | Tool | Notes |
|---|---|---|
| Structured logs | `structlog` (Phase 1) | JSON in production, colored console in dev |
| Distributed traces | OpenTelemetry → any OTLP collector | Jaeger, Grafana Tempo, etc. |
| Metrics | Prometheus (`/metrics`) | Scraped by Prometheus, visualized in Grafana |
| Error tracking | Sentry | Automatic FastAPI + SQLAlchemy integration |

---

## OpenTelemetry — Distributed Tracing

### Configuration

```bash
OTLP_ENDPOINT=http://localhost:4317   # gRPC endpoint of your OTLP collector
```

If `OTLP_ENDPOINT` is empty, tracing is disabled (no-op).

### What is instrumented

`setup_tracing(app)` is called in `create_app()` and instruments:
- **FastAPI** — every HTTP request becomes a root span
- **SQLAlchemy** — every query becomes a child span

```python
# app/core/telemetry.py
def setup_tracing(app) -> None:
    if not settings.otlp_endpoint:
        return
    resource = Resource.create({"service.name": "aurynix-nexus", "environment": settings.environment})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
```

### What a trace looks like

```
POST /api/v1/chat/stream                          [450ms]
  ├─ auth: verify JWT                             [2ms]
  ├─ db: load conversation                        [5ms]
  ├─ LangGraph: supervisor_node                   [180ms]
  │    └─ llm: ChatGroq (routing decision)        [170ms]
  ├─ LangGraph: research_agent                    [240ms]
  │    ├─ llm: ChatGroq (tool selection)          [150ms]
  │    ├─ tool: knowledge_base_search             [55ms]
  │    │    ├─ embed: FastEmbed                   [8ms]
  │    │    └─ qdrant: search                     [45ms]
  │    └─ llm: ChatGroq (synthesis)              [80ms]
  └─ db: INSERT message                           [4ms]
```

---

## Prometheus — Metrics

Metrics are exposed at `GET /metrics` (excluded from OpenAPI docs). Prometheus scrapes this endpoint; Grafana visualizes it.

### Metrics defined in `app/core/metrics.py`

| Metric | Type | Labels | Description |
|---|---|---|---|
| `aurynix_chat_requests_total` | Counter | `status` | Total chat stream requests |
| `aurynix_auth_requests_total` | Counter | `endpoint`, `status` | Total auth requests |
| `aurynix_document_ingestions_total` | Counter | `status` | Document ingest jobs |
| `aurynix_tool_calls_total` | Counter | `tool_name` | Tool invocations by name |
| `aurynix_rate_limit_rejections_total` | Counter | `group` | Requests rejected by rate limiting |
| `aurynix_chat_latency_seconds` | Histogram | — | Time to first token in a chat stream |
| `aurynix_ingest_duration_seconds` | Histogram | — | Document ingestion wall-clock time |
| `aurynix_active_sse_connections` | Gauge | — | Open SSE streaming connections |

### Where metrics are recorded

- **Chat service** — `active_sse_connections` gauge increments on stream open, decrements on close. `chat_latency_seconds` records time-to-first-token. `chat_requests_total` increments on success or error.
- **Rate limit middleware** — `rate_limit_rejections_total` increments on every 429 response.

### Prometheus scrape config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: aurynix
    static_configs:
      - targets: ["app:8000"]
    metrics_path: /metrics
    scrape_interval: 15s
```

---

## Sentry — Error Tracking

### Configuration

```bash
SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/789
SENTRY_TRACES_SAMPLE_RATE=0.1   # 10% of transactions sent as traces
```

If `SENTRY_DSN` is empty, Sentry is disabled. Initialization runs at module import time in `app/main.py`:

```python
# app/core/telemetry.py
def setup_sentry() -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,
    )
```

Sentry captures:
- Unhandled exceptions in FastAPI route handlers
- SQLAlchemy query errors
- Any exception re-raised after logging in service layer

---

## Structured Logs (Phase 1, still active)

All logs are emitted via `structlog`. In development, they render as colored console output. In production (`ENVIRONMENT=production`), they render as JSON:

```json
{"event": "Ingest job enqueued", "doc_id": "550e8400-...", "job_id": "abc123", "level": "info", "timestamp": "2026-08-11 09:00:00"}
```

Context variables (`request_id`, `user_id`) are automatically bound per-request by `RequestIDMiddleware`.

---

## Local Development Setup

```bash
# Jaeger all-in-one (traces)
docker run -d --name jaeger \
  -p 16686:16686 -p 4317:4317 \
  jaegertracing/all-in-one:1.60

# Prometheus
docker run -d --name prometheus \
  -p 9090:9090 \
  -v $(pwd)/docker/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:v2.53.0

# Grafana
docker run -d --name grafana -p 3001:3000 grafana/grafana:11.1.0
```

Then set in `.env`:
```bash
OTLP_ENDPOINT=http://localhost:4317
```
