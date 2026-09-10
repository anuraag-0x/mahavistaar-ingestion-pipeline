"""Sub-stage progress for a running job.

A stage change is a single event. What happens *inside* a stage — 49 pages
extracted, 84 chunks embedded — used to be invisible until the stage finished.
This records that movement in two places at once:

* on the job row, so a page opened halfway through still shows where it got to
* on the ``document_events`` channel, so an open page moves without polling

Both go through :meth:`ProgressReporter.report`, which throttles writes so a
thousand-page document does not produce a thousand database round trips.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.document import DocumentJobModel
from backend.app.services.document_event_service import DocumentEventService

logger = logging.getLogger("mahavistaar.pipeline")

# Never write more often than this, however fast the work is going.
MIN_WRITE_INTERVAL_SECONDS = 0.75


def _percent(processed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, processed / total * 100.0))


@dataclass
class Progress:
    """One snapshot of how far a stage has got."""

    stage: str
    label: str
    processed: int
    total: int
    unit: str = "items"
    status: str = "running"

    def as_payload(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "label": self.label,
            "processed": self.processed,
            "total": self.total,
            "unit": self.unit,
            "percent": round(_percent(self.processed, self.total), 1),
            "status": self.status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


class ProgressReporter:
    """Reports progress for one job, throttled and safe to call in a tight loop.

    A failure to report is never allowed to fail the work being reported on, so
    every write is guarded. Progress is best-effort telemetry, not pipeline state.
    """

    def __init__(self, session: AsyncSession, *, workflow_id: str, job: DocumentJobModel):
        self._session = session
        self._workflow_id = workflow_id
        self._job = job
        self._last_write = 0.0

    async def report(self, progress: Progress, *, force: bool = False) -> None:
        """Persist and publish a snapshot.

        Pass ``force`` for the first and last call of a stage, which must always
        land: the first so the bar appears immediately, the last so it reaches
        100 rather than stopping at whatever the throttle let through.
        """
        now = time.monotonic()
        if not force and now - self._last_write < MIN_WRITE_INTERVAL_SECONDS:
            return
        self._last_write = now

        payload = progress.as_payload()
        try:
            # config_json is replaced rather than mutated: SQLAlchemy does not
            # track in-place edits of a JSONB dict, so a mutation would not save.
            self._job.config_json = {**(self._job.config_json or {}), "progress": payload}
            await self._session.commit()
            await DocumentEventService.publish(
                self._session,
                workflow_id=self._workflow_id,
                stage=progress.stage,
                job_status=self._job.status or "running",
                progress=payload,
            )
        except Exception:
            logger.debug("could not record progress | workflow=%s", self._workflow_id, exc_info=True)

    async def finish(self, progress: Progress) -> None:
        """Mark a stage's progress complete."""
        progress.status = "completed"
        progress.processed = progress.total or progress.processed
        await self.report(progress, force=True)


def read_progress(job: Optional[DocumentJobModel]) -> Optional[dict[str, Any]]:
    """The progress snapshot stored on a job, if it has one."""
    config = (job.config_json or {}) if job else {}
    progress = config.get("progress")
    return progress if isinstance(progress, dict) else None
