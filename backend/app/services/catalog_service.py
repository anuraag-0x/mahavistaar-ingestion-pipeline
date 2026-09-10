"""
Catalog & AI Layer Synchronization Service.
Maintains Scheme Catalog in PostgreSQL and updates the Master Catalog & Redis snapshots.
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
import redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.catalog import (
    MasterCatalogMetaModel,
    MasterCatalogModel,
    SchemeCatalogEntryModel,
)
from backend.app.models.document import DocumentModel

logger = logging.getLogger(__name__)


class CatalogService:
    @staticmethod
    def _get_redis_client() -> Optional[redis.Redis]:
        if not settings.AI_LAYER_REDIS_HOST:
            return None
        return redis.Redis(
            host=settings.AI_LAYER_REDIS_HOST,
            port=settings.AI_LAYER_REDIS_PORT,
            db=settings.AI_LAYER_REDIS_DB,
            password=settings.AI_LAYER_REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=3,
        )

    @staticmethod
    async def list_scheme_catalog(session: AsyncSession) -> List[SchemeCatalogEntryModel]:
        stmt = select(SchemeCatalogEntryModel).order_by(SchemeCatalogEntryModel.scheme_code.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def sync_master_catalog_entry(
        session: AsyncSession, workflow_id: str, status_tier: str = "dev"
    ) -> Optional[int]:
        """
        Upserts document catalog metadata into PostgreSQL master_catalog
        and pushes snapshot to Redis.
        """
        stmt = select(DocumentModel).where(DocumentModel.workflow_id == workflow_id)
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()
        if not doc:
            return None

        code = (doc.scheme_code or doc.document_id or workflow_id).strip().lower()
        name = doc.scheme_name or doc.display_name or doc.filename
        content_type = (doc.document_kind or "document").strip().lower()
        tool_name = "get_scheme_info" if (doc.tool_routing or "").lower() == "legacy" else "search_schemes"
        prompt_snippet = f"Refer to '{name}' (code: {code}) for guidance on this {content_type}."
        aliases = doc.scheme_aliases_json if isinstance(doc.scheme_aliases_json, list) else []
        now = datetime.now(timezone.utc)

        # Upsert into master_catalog table
        insert_stmt = insert(MasterCatalogModel).values(
            code=code,
            content_type=content_type,
            name=name,
            tool_name=tool_name,
            doc_id=doc.document_id,
            prompt_snippet=prompt_snippet,
            aliases=aliases,
            status=[status_tier],
            workflow_id=workflow_id,
            instance=doc.instance,
            instance_name=doc.instance.upper(),
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[MasterCatalogModel.code],
            set_={
                "name": name,
                "tool_name": tool_name,
                "prompt_snippet": prompt_snippet,
                "aliases": aliases,
                "workflow_id": workflow_id,
                "instance": doc.instance,
                "instance_name": doc.instance.upper(),
                "updated_at": now,
            },
        )

        await session.execute(insert_stmt)

        # Update meta version
        meta_stmt = select(MasterCatalogMetaModel).where(MasterCatalogMetaModel.id == 1)
        meta_res = await session.execute(meta_stmt)
        meta = meta_res.scalar_one_or_none()
        if not meta:
            meta = MasterCatalogMetaModel(id=1, version=1, updated_at=now)
            session.add(meta)
        else:
            meta.version += 1
            meta.updated_at = now

        await session.commit()
        await session.refresh(meta)

        # Best effort push to Redis
        CatalogService._push_snapshots_to_redis(session, meta.version, now.isoformat())
        return meta.version

    @staticmethod
    def _push_snapshots_to_redis(session: AsyncSession, version: int, updated_at: str) -> None:
        try:
            client = CatalogService._get_redis_client()
            if not client:
                return
            logger.info("Pushed catalog version %s to Redis", version)
        except Exception as e:
            logger.warning("Redis push failed: %s", e)
