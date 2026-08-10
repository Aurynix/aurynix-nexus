"""OpenTelemetry + Prometheus + Sentry setup."""

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def setup_tracing(app) -> None:
    """Instrument the FastAPI app with OpenTelemetry traces."""
    if not settings.otlp_endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {"service.name": "aurynix-nexus", "environment": settings.environment}
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
        )
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()

        logger.info("OpenTelemetry tracing enabled", endpoint=settings.otlp_endpoint)
    except Exception as exc:
        logger.warning("Failed to setup OpenTelemetry tracing", error=str(exc))


def setup_sentry() -> None:
    """Initialize Sentry error tracking."""
    if not settings.sentry_dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            send_default_pii=False,
        )
        logger.info("Sentry initialized")
    except Exception as exc:
        logger.warning("Failed to initialize Sentry", error=str(exc))
