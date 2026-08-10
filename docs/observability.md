# Observability

Aurynix exports metrics, distributed traces, and error events so you can monitor the system in production without reading log files.

---

## Stack

| Concern | Tool | Where |
|---|---|---|
| Structured logs | `structlog` (Phase 1) | stdout → log aggregator |
| Distributed traces | OpenTelemetry → Jaeger | `http://localhost:16686` |
| Metrics | Prometheus + Grafana | `http://localhost:3000` |
| Error tracking | Sentry | `https://sentry.io` |

---

## OpenTelemetry — Distributed Tracing

Every HTTP request, LangGraph node, tool call, and database query is captured as a span. This lets you see exactly where time is spent for any chat request.

### Setup

```bash
OTEL_SERVICE_NAME=aurynix-nexus
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317   # Jaeger / Grafana Tempo
OTEL_TRACES_SAMPLER=parentbased_traceid_ratio
OTEL_TRACES_SAMPLER_ARG=0.1                         # sample 10% in production
```

### Instrumentation

```python
# app/core/telemetry.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

def setup_telemetry() -> None:
    provider = TracerProvider(resource=Resource({"service.name": settings.otel_service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
    )
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI, SQLAlchemy, httpx, Redis
    FastAPIInstrumentor.instrument()
    SQLAlchemyInstrumentor.instrument()
    HTTPXClientInstrumentor.instrument()
    RedisInstrumentor.instrument()
```

### What a trace looks like

```
POST /api/v1/chat/stream                          [450ms]
  ├─ auth: verify JWT                             [2ms]
  ├─ db: load conversation                        [5ms]
  ├─ LangGraph: run graph                         [440ms]
  │    ├─ node: memory_load                       [12ms]
  │    │    └─ db: SELECT memory_facts            [11ms]
  │    ├─ node: agent                             [380ms]
  │    │    ├─ llm: ChatGroq.invoke               [320ms]
  │    │    └─ tool: knowledge_base_search        [55ms]
  │    │         ├─ embed: FastEmbed              [8ms]
  │    │         └─ qdrant: search                [45ms]
  │    └─ node: memory_save                       [35ms]
  │         └─ db: UPSERT memory_facts            [33ms]
  └─ db: INSERT message                           [4ms]
```

### Custom spans

```python
tracer = trace.get_tracer(__name__)

async def agent_node(state, config):
    with tracer.start_as_current_span("agent_node") as span:
        span.set_attribute("user_id", state["user_id"])
        span.set_attribute("iteration", state["iteration_count"])
        ...
```

---

## Prometheus — Metrics

Metrics are exposed at `GET /metrics` (Prometheus scrape endpoint). A Grafana dashboard displays them.

### Docker Compose addition

```yaml
prometheus:
  image: prom/prometheus:v2.53.0
  volumes:
    - ./docker/prometheus.yml:/etc/prometheus/prometheus.yml
  ports: ["9090:9090"]

grafana:
  image: grafana/grafana:11.1.0
  ports: ["3000:3000"]
  volumes:
    - grafana-data:/var/lib/grafana
```

### Key metrics

| Metric | Type | Description |
|---|---|---|
| `aurynix_http_requests_total` | Counter | Total requests by method, path, status |
| `aurynix_http_request_duration_seconds` | Histogram | Request latency |
| `aurynix_llm_calls_total` | Counter | LLM API calls by model |
| `aurynix_llm_tokens_total` | Counter | Tokens used (prompt + completion) |
| `aurynix_llm_latency_seconds` | Histogram | LLM call latency |
| `aurynix_tool_calls_total` | Counter | Tool calls by tool name, success/failure |
| `aurynix_cache_hits_total` | Counter | Cache hits by cache type |
| `aurynix_cache_misses_total` | Counter | Cache misses by cache type |
| `aurynix_worker_jobs_total` | Counter | ARQ jobs by type, status |
| `aurynix_worker_job_duration_seconds` | Histogram | Worker job duration |
| `aurynix_qdrant_search_latency_seconds` | Histogram | Vector search latency |
| `aurynix_active_connections` | Gauge | Active SSE connections |

### Recording metrics

```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

llm_calls = Counter("aurynix_llm_calls_total", "LLM API calls", ["model"])
llm_latency = Histogram("aurynix_llm_latency_seconds", "LLM latency", ["model"])
llm_tokens = Counter("aurynix_llm_tokens_total", "Tokens used", ["model", "type"])

def record_llm_call(model: str, duration: float, prompt_tokens: int, completion_tokens: int):
    llm_calls.labels(model=model).inc()
    llm_latency.labels(model=model).observe(duration)
    llm_tokens.labels(model=model, type="prompt").inc(prompt_tokens)
    llm_tokens.labels(model=model, type="completion").inc(completion_tokens)
```

---

## Sentry — Error Tracking

```bash
SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/789
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

```python
# app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn=settings.sentry_dsn,
    environment=settings.environment,
    traces_sample_rate=settings.sentry_traces_sample_rate,
    integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    before_send=_scrub_tokens,   # strip OAuth tokens from event payloads
)
```

### Alerts configured by default

| Alert | Condition |
|---|---|
| High error rate | > 1% of requests return 5xx in a 5-minute window |
| LLM timeout | Any `asyncio.TimeoutError` from Groq call |
| Worker job exhausted | ARQ job exceeds `max_tries` |
| OAuth token refresh failed | `google.auth.exceptions.RefreshError` |

---

## Health Check Endpoint (enhanced)

`GET /api/v1/health/ready` is extended to include worker and telemetry status:

```json
{
  "status": "ready",
  "checks": {
    "postgres": "ok",
    "redis": "ok",
    "qdrant": "ok",
    "worker": "ok",
    "otel_exporter": "ok"
  },
  "version": "0.2.0"
}
```
