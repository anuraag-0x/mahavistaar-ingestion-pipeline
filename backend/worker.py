"""Native ingestion worker. Run with: python -m backend.worker"""

import asyncio
import logging

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.logging import describe, setup_logging
from backend.app.services.ingestion_service import IngestionService

setup_logging()
logger = logging.getLogger("mahavistaar.worker")

POLL_SECONDS = 2


async def run() -> None:
    logger.info("worker started, polling for jobs every %ss", POLL_SECONDS)
    while True:
        try:
            async with AsyncSessionLocal() as session:
                job_id = await IngestionService.claim_job(session)
        except Exception as exc:
            # A database blip must not kill the worker; log it and keep polling.
            logger.error("could not reach the job queue: %s", describe(exc))
            await asyncio.sleep(POLL_SECONDS)
            continue

        if job_id is None:
            await asyncio.sleep(POLL_SECONDS)
            continue

        try:
            async with AsyncSessionLocal() as session:
                await IngestionService.process_job(session, job_id)
        except Exception:
            # process_job records stage failures itself; this catches anything
            # that escaped it, so one bad job cannot stop the loop.
            logger.exception("job %s crashed outside its own error handling", job_id)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("worker stopped")
