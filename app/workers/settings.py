"""ARQ WorkerSettings — entry point for the worker process."""
from app.core.config import settings
from app.workers.tasks import ingest_document


async def startup(ctx: dict) -> None:
    from app.core.logging import configure_logging

    configure_logging()


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [ingest_document]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 300  # 5 minutes per job

    @property
    def redis_settings(self):
        from arq.connections import RedisSettings as ArqRedisSettings

        return ArqRedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
        )
