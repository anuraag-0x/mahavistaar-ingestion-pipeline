"""Initialize the application schema before Compose starts API and worker."""

import asyncio

from sqlalchemy import text

from backend.app.core.database import async_engine, init_db_schema
from backend.app.core.config import settings
import backend.app.models  # noqa: F401 -- register all tables with metadata


async def main() -> None:
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "cerebras":
        if not settings.CEREBRAS_API_KEY:
            raise RuntimeError("Set CEREBRAS_API_KEY for the translation service")
    elif provider == "vllm":
        if not settings.VLLM_AGRINET_MODEL_URL.startswith(("http://", "https://")):
            raise RuntimeError("Set VLLM_AGRINET_MODEL_URL for the translation service")
    else:
        raise RuntimeError("LLM_PROVIDER must be vllm or cerebras")
    # Retry connectivity only. Schema/permission errors must fail visibly.
    for attempt in range(30):
        try:
            async with async_engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            break
        except Exception:
            if attempt == 29:
                raise RuntimeError("PostgreSQL unavailable; check host, credentials and network access") from None
            print("Waiting for PostgreSQL...", flush=True)
            await asyncio.sleep(2)
    await init_db_schema()
    await async_engine.dispose()
    print("Application database schema ready", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
