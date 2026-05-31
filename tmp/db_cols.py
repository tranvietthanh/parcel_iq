#!/usr/bin/env python3
import asyncio
import json
import os

import asyncpg

async def main():
    # Use provided connection string (without +asyncpg)
    url = os.getenv("DB_URL", "postgresql://parceliq:devpassword@localhost:5432/parceliq")
    conn = await asyncpg.connect(url)
    rows = await conn.fetch(
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('properties','property_school_catchments','spatial_zones')
        ORDER BY table_name, ordinal_position;
        """
    )
    print(json.dumps([dict(r) for r in rows], indent=2))
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
