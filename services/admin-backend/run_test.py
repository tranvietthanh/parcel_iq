import asyncio
import sys
import traceback
from app.dependencies import get_db
from app.routers.stats import get_dashboard_stats
from app.config import settings
from asyncpg import connect

async def run_test():
    try:
        conn = await connect(settings.asyncpg_dsn)
        try:
            stats = await get_dashboard_stats(db=conn)
            print("SUCCESS:", stats.model_dump())
        except Exception as e:
            with open("test_stats_error.txt", "w") as f:
                traceback.print_exc(file=f)
            print("ERROR written to test_stats_error.txt")
        finally:
            await conn.close()
    except Exception as e:
        with open("test_stats_error.txt", "w") as f:
            traceback.print_exc(file=f)
        print("ERROR CONNECTING written to test_stats_error.txt")

if __name__ == "__main__":
    asyncio.run(run_test())
