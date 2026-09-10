"""PostgreSQL-backed document lifecycle notifications."""

import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DocumentEventService:
    CHANNEL = "document_events"

    @classmethod
    async def publish(
        cls,
        session: AsyncSession,
        *,
        workflow_id: str,
        stage: str,
        job_status: str,
        progress: Optional[dict[str, Any]] = None,
    ) -> None:
        """Announce a stage change, or movement within a stage.

        ``progress`` carries the sub-stage detail: how many pages or chunks are
        done out of how many. It is absent on a plain stage transition, which is
        how a listener tells the two apart.
        """
        body: dict[str, Any] = {"workflow_id": workflow_id, "stage": stage, "job_status": job_status}
        if progress:
            body["progress"] = progress
        payload = json.dumps(body)
        # Postgres refuses a NOTIFY payload over 8000 bytes and would abort the
        # transaction, so a pathological payload is dropped rather than raised.
        if len(payload.encode("utf-8")) > 7000:
            payload = json.dumps({"workflow_id": workflow_id, "stage": stage, "job_status": job_status})
        await session.execute(text("SELECT pg_notify('document_events', :payload)"), {"payload": payload})
        await session.commit()
