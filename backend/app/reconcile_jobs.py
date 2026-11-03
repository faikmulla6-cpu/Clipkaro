import asyncio
import json

from app.core.database import close_database, init_db
from app.services.jobs import requeue_stale_jobs


async def main() -> int:
    await init_db()
    try:
        recovered = await requeue_stale_jobs()
        print(json.dumps({"recovered_jobs": recovered}))
        return 0
    finally:
        await close_database()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
