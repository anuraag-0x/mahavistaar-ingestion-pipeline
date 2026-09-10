"""Server-sent events for document lifecycle updates.

The worker announces every stage change and every step inside a stage on the
``document_events`` Postgres channel. Each request below opens its own listener
on that channel and relays what it hears to one browser, so the console reflects
the pipeline as it runs instead of asking what happened a few seconds ago.
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import asyncpg
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.app.core.config import settings

logger = logging.getLogger("mahavistaar.events")

router = APIRouter(prefix="/events", tags=["Events"])

# Long enough to stay out of the way, short enough that a proxy holding an idle
# connection open does not decide the stream is dead.
KEEPALIVE_SECONDS = 25

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Without this nginx buffers the stream and delivers it in one lump at the
    # end, which looks exactly like realtime not working at all.
    "X-Accel-Buffering": "no",
}


async def _relay(workflow_id: Optional[str]) -> AsyncIterator[str]:
    """Yield lifecycle events, for one document or for every document.

    ``workflow_id`` of None is the workspace-wide feed used by the document
    list; anything else is filtered down to that single run.
    """
    dsn = settings.async_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn)
    updates: asyncio.Queue[str] = asyncio.Queue()

    def receive_update(_connection, _pid, _channel, payload):
        updates.put_nowait(payload)

    await connection.add_listener("document_events", receive_update)
    try:
        yield ": connected\n\n"
        while True:
            try:
                payload = await asyncio.wait_for(updates.get(), timeout=KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            try:
                data = json.loads(payload)
            except ValueError:
                # A payload we cannot read is one we cannot filter, so it is
                # dropped rather than sent to every listening browser.
                logger.warning("ignored an unreadable document event payload")
                continue
            if workflow_id is None or data.get("workflow_id") == workflow_id:
                yield f"event: document.updated\ndata: {payload}\n\n"
    finally:
        await connection.remove_listener("document_events", receive_update)
        await connection.close()


@router.get("/documents")
async def all_document_events() -> StreamingResponse:
    """Every document's lifecycle events, for the workspace-wide views."""
    return StreamingResponse(_relay(None), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/documents/{workflow_id}")
async def document_events(workflow_id: str) -> StreamingResponse:
    """One document's lifecycle events."""
    return StreamingResponse(_relay(workflow_id), media_type="text/event-stream", headers=SSE_HEADERS)
